import json
import logging

# ruff: noqa: E402
import os
import pickle
import sys
import threading
import time
from pathlib import Path

from plesk_unified.log_handler import create_os_handlers

# --- LOGGING SETUP ---
# Must be done before importing heavy libraries.
# This ensures we capture their initialization warnings if needed.
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / "storage" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; env vars can be set directly

LOG_FILE = os.environ.get("LOG_FILE", str(LOG_DIR / "plesk_unified.log"))
# Convert string level (e.g. "INFO") to integer
LOG_LEVEL_NAME = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.INFO)

# Create logger
logger = logging.getLogger("plesk_unified")
logger.setLevel(LOG_LEVEL)

# Formatter
formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

# 1. OS-native / file handler(s) — chosen by LOG_HANDLER env var
# Possible values: "os" (default), "file", "both"
os_handlers = create_os_handlers(LOG_LEVEL, formatter, LOG_FILE)

# 2. Stream Handler (stderr) - CRITICAL for MCP protocol
stream_handler = logging.StreamHandler(sys.stderr)
stream_handler.setFormatter(formatter)
stream_handler.setLevel(LOG_LEVEL)

# Avoid adding duplicate handlers if reloaded
if not logger.handlers:
    for _h in os_handlers:
        logger.addHandler(_h)
    logger.addHandler(stream_handler)

# Silence noisy third-party libraries unless they error
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("git").setLevel(logging.WARNING)

_log_handler_mode = os.environ.get("LOG_HANDLER", "os").lower().strip()
logger.info(
    "Logging initialized. Level: %s, Handler mode: %s, File: %s",
    LOG_LEVEL_NAME,
    _log_handler_mode,
    LOG_FILE,
)

STARTUP_AT = time.perf_counter()


# --- SILENCE THE NOISE ---
os.environ["TQDM_DISABLE"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

from typing import Any, Dict, Optional, Tuple

import lancedb  # type: ignore
import numpy as np
from fastmcp import FastMCP
from pydantic import Field

try:
    from plesk_unified import chunking, html_utils, io_utils, platform_utils
    from plesk_unified.model_config import get_active_profile, list_profiles
    from plesk_unified.tq_index import TurboQuantIndex
except ImportError:
    import chunking
    import html_utils
    import io_utils
    import platform_utils

    try:
        from model_config import get_active_profile, list_profiles  # type: ignore
    except Exception:
        get_active_profile = None  # type: ignore
        list_profiles = None  # type: ignore
    from tq_index import TurboQuantIndex  # type: ignore

# Initialize MCP — fast, no heavy work here
mcp = FastMCP("mcp-plesk-unified")

# --- Configuration ---
KB_DIR = BASE_DIR / "knowledge_base"

KB_DIR.mkdir(exist_ok=True)
(BASE_DIR / "storage").mkdir(exist_ok=True)

SOURCES = [
    {
        "path": KB_DIR / "stubs",
        "cat": "php-stubs",
        "type": "php",
        "repo_url": "https://github.com/plesk/pm-api-stubs.git",
    },
    {
        "path": KB_DIR / "sdk",
        "cat": "js-sdk",
        "type": "js",
        "repo_url": "https://github.com/plesk/plesk-ext-sdk.git",
    },
    {
        "path": KB_DIR / "api-rpc",
        "cat": "api",
        "type": "html",
        "repo_url": None,
        "zip_url": "https://docs.plesk.com/en-US/obsidian/zip/api-rpc.zip",
    },
    {
        "path": KB_DIR / "cli-linux",
        "cat": "cli",
        "type": "html",
        "repo_url": None,
        "zip_url": "https://docs.plesk.com/en-US/obsidian/zip/cli-linux.zip",
    },
    {
        "path": KB_DIR / "extensions-guide",
        "cat": "guide",
        "type": "html",
        "repo_url": None,
        "zip_url": "https://docs.plesk.com/en-US/obsidian/zip/extensions-guide.zip",
    },
]

# --- Lazy Initialization ---
# The embedding model (~1.5 GB) is loaded on first tool call, NOT at import time.
# This lets the MCP server respond to `initialize` in <2 seconds.

_embedding_model: Any = None
_schema_class: Any = None
_reranker: Any = None
_active_profile: Any = None
_tq_index: Any = None
_detected_device: str | None = None
_warmup_state = "idle"
_warmup_error: str | None = None
_warmup_lock = threading.Lock()
_warmup_thread: threading.Thread | None = None


def _get_profile():
    global _active_profile
    if _active_profile is None:
        if get_active_profile is None:
            raise RuntimeError("model_config.get_active_profile not available")
        _active_profile = get_active_profile()
    return _active_profile


def _db_profile_name() -> str:
    profile = _get_profile()
    # full-tq shares embeddings/dimension with full, so reuse full's LanceDB corpus.
    return "full" if getattr(profile, "use_turboquant", False) else profile.name


DB_PATH = BASE_DIR / "storage" / f"lancedb_{_db_profile_name()}"
TQ_DIR = BASE_DIR / "storage" / "turboquant"


def _detect_device() -> str:
    """Detect the best available compute device (CUDA > MPS > CPU)."""
    global _detected_device
    if _detected_device is not None:
        return _detected_device

    _detected_device = platform_utils.get_optimal_device()
    logger.info("Selected compute device: %s", _detected_device.upper())
    return _detected_device


def get_embedding_model() -> Any:
    """Return the embedding model, initializing it on first call."""
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    from lancedb.embeddings import get_registry  # type: ignore

    profile = _get_profile()
    device = _detect_device()
    logger.info("Initializing embedding model %s on %s...", profile.embed_model, device)
    init_started = time.perf_counter()
    try:
        reg = get_registry().get("huggingface")
        try:
            _embedding_model = reg.create(name=profile.embed_model, device=device)
        except TypeError:
            logger.debug("Device argument rejected, retrying without device kwarg.")
            _embedding_model = reg.create(name=profile.embed_model)
        logger.info(
            "Embedding model initialized successfully in %.2fs.",
            time.perf_counter() - init_started,
        )
    except Exception:
        logger.critical("Embedding model could not be initialized.", exc_info=True)
        raise

    return _embedding_model


def get_schema() -> Any:
    """Return the LanceDB schema class, creating it on first call."""
    global _schema_class
    if _schema_class is not None:
        return _schema_class

    from lancedb.pydantic import LanceModel, Vector  # type: ignore

    profile = _get_profile()
    em = get_embedding_model()
    dim = profile.embed_dim

    class UnifiedSchema(LanceModel):
        vector: Vector(dim) = em.VectorField()  # type: ignore
        text: str = em.SourceField()
        title: str
        filename: str
        category: str
        breadcrumb: str

    _schema_class = UnifiedSchema
    return _schema_class


def get_reranker() -> Any:
    """Return the cross-encoder reranker, initializing it on first call.

    Returns None if the active profile has reranking disabled.
    """
    global _reranker
    if _reranker is not None:
        return _reranker

    profile = _get_profile()

    if not profile.reranker_enabled or not profile.reranker_model:
        logger.info("Reranker disabled by profile '%s'.", profile.name)
        return None

    logger.info("Initializing reranker %s...", profile.reranker_model)
    init_started = time.perf_counter()
    try:
        from sentence_transformers import CrossEncoder  # type: ignore

        device = _detect_device()
        _reranker = CrossEncoder(profile.reranker_model, device=device)
        logger.info(
            "Reranker initialized on %s in %.2fs.",
            device,
            time.perf_counter() - init_started,
        )
    except Exception:
        logger.warning(
            "Reranker initialization failed. Proceeding without reranking.",
            exc_info=True,
        )
        return None

    return _reranker


def get_table(create_new: bool = False) -> Any:
    """Connect to or create the LanceDB table."""
    logger.debug("Connecting to LanceDB at %s", DB_PATH)
    db = lancedb.connect(str(DB_PATH))
    try:
        if create_new:
            logger.info("Creating/overwriting table 'plesk_knowledge'")
            return db.create_table(
                "plesk_knowledge", schema=get_schema(), mode="overwrite"
            )
        return db.open_table("plesk_knowledge")
    except Exception:
        logger.info(
            "Table not found or error opening. Creating new 'plesk_knowledge' table."
        )
        return db.create_table("plesk_knowledge", schema=get_schema(), mode="create")


def _get_tq_index_path() -> Path:
    profile = _get_profile()
    TQ_DIR.mkdir(parents=True, exist_ok=True)
    return TQ_DIR / f"{profile.name}.pkl"


def _save_tq_index(tq_index: TurboQuantIndex) -> None:
    data = {
        "compressed_db": tq_index.compressed_db,
        "meta": tq_index._meta,
        "category_to_indices": tq_index._category_to_indices,
        "bits": tq_index.bits,
        "dim": tq_index.dim,
    }
    with _get_tq_index_path().open("wb") as fh:
        pickle.dump(data, fh)


def _load_tq_index() -> TurboQuantIndex | None:
    path = _get_tq_index_path()
    if not path.exists():
        return None

    profile = _get_profile()
    tq_index = TurboQuantIndex(
        dim=profile.embed_dim,
        bits=profile.tq_bits,
        device=_detect_device(),
    )
    with path.open("rb") as fh:
        data = pickle.load(fh)
    tq_index.compressed_db = data.get("compressed_db")
    tq_index._meta = data.get("meta", [])
    tq_index._category_to_indices = data.get("category_to_indices", {})
    return tq_index


def _build_tq_index_from_table() -> TurboQuantIndex:
    profile = _get_profile()
    table = get_table(create_new=False)
    all_docs = table.search().limit(100000).to_list()

    tq_index = TurboQuantIndex(
        dim=profile.embed_dim,
        bits=profile.tq_bits,
        device=_detect_device(),
    )

    if all_docs:
        corpus_vecs = np.asarray([doc["vector"] for doc in all_docs], dtype=np.float32)
        tq_index.add(corpus_vecs, all_docs)

    _save_tq_index(tq_index)
    logger.info("TurboQuant index built with %d documents.", len(all_docs))
    return tq_index


def get_tq_index() -> TurboQuantIndex:
    global _tq_index
    if _tq_index is not None:
        return _tq_index

    loaded = _load_tq_index()
    if loaded is not None:
        _tq_index = loaded
        logger.info("Loaded TurboQuant index from %s", _get_tq_index_path())
        return _tq_index

    logger.info("TurboQuant index not found on disk. Building from LanceDB...")
    _tq_index = _build_tq_index_from_table()
    return _tq_index


def _log_server_ready(message: str) -> None:
    logger.info(message)
    logger.info("Server module initialized in %.2fs.", time.perf_counter() - STARTUP_AT)


def _env_flag(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _begin_warmup() -> bool:
    global _warmup_state, _warmup_error
    with _warmup_lock:
        if _warmup_state == "running":
            return False
        _warmup_state = "running"
        _warmup_error = None
        return True


def _finish_warmup(error: Exception | None = None) -> None:
    global _warmup_state, _warmup_error
    with _warmup_lock:
        if error is None:
            _warmup_state = "ready"
            _warmup_error = None
            return
        _warmup_state = "failed"
        _warmup_error = str(error)


def _run_warmup_sequence() -> list[str]:
    profile = _get_profile()
    logger.info("Starting warmup for profile %s.", profile.name)

    parts = [f"Warmup started for profile '{profile.name}'."]

    get_embedding_model()
    parts.append(f"Embedding model ready: {profile.embed_model}.")

    reranker = get_reranker()
    if reranker is None:
        parts.append("Reranker not loaded.")
    else:
        parts.append(f"Reranker ready: {profile.reranker_model}.")

    get_table(create_new=False)
    parts.append("LanceDB table ready.")

    if getattr(profile, "use_turboquant", False):
        tq_path = _get_tq_index_path()
        if tq_path.exists():
            global _tq_index
            _tq_index = _load_tq_index()
            parts.append(f"TurboQuant index loaded from {tq_path.name}.")
        else:
            parts.append("TurboQuant index not present; skipped build during warmup.")

    logger.info("Warmup complete for profile %s.", profile.name)
    return parts


def _background_warmup_worker() -> None:
    if not _begin_warmup():
        logger.info("Background warmup skipped because warmup is already running.")
        return

    try:
        _run_warmup_sequence()
        _finish_warmup()
    except Exception as exc:
        _finish_warmup(exc)
        logger.exception("Background warmup failed.")


def _maybe_start_background_warmup() -> None:
    if not _env_flag("PLESK_DAEMON_AUTO_WARMUP"):
        return

    global _warmup_thread
    with _warmup_lock:
        if _warmup_thread is not None and _warmup_thread.is_alive():
            return
        _warmup_thread = threading.Thread(
            target=_background_warmup_worker,
            name="plesk-daemon-warmup",
            daemon=True,
        )
        _warmup_thread.start()

    logger.info("Background daemon warmup started.")


def _table_health() -> tuple[bool, str | None]:
    try:
        db = lancedb.connect(str(DB_PATH))
        db.open_table("plesk_knowledge")
        return True, None
    except Exception as exc:
        return False, str(exc)


@mcp.tool
def warmup_server() -> str:
    """Preload the active profile models and table without running indexing."""
    if not _begin_warmup():
        return "Warmup already running."

    try:
        parts = _run_warmup_sequence()
        _finish_warmup()
    except Exception as exc:
        _finish_warmup(exc)
        logger.exception("Manual warmup failed.")
        return f"Warmup failed: {exc}"

    return "\n".join(parts)


@mcp.tool
def daemon_health() -> str:
    """Return daemon-centric readiness status for warmup and indexed search paths."""
    profile = _get_profile()
    table_ready, table_error = _table_health()
    tq_path = (
        _get_tq_index_path() if getattr(profile, "use_turboquant", False) else None
    )

    with _warmup_lock:
        status = {
            "profile": profile.name,
            "device": _detect_device(),
            "auto_warmup_enabled": _env_flag("PLESK_DAEMON_AUTO_WARMUP"),
            "warmup_state": _warmup_state,
            "warmup_error": _warmup_error,
            "warmup_thread_alive": (
                _warmup_thread.is_alive() if _warmup_thread is not None else False
            ),
            "table_ready": table_ready,
            "table_error": table_error,
            "turboquant_expected": bool(getattr(profile, "use_turboquant", False)),
            "turboquant_loaded": _tq_index is not None,
            "turboquant_artifact_exists": (tq_path.exists() if tq_path else None),
            "refresh_mode": "synchronous-only",
        }

    return json.dumps(status, indent=2)


@mcp.tool
def list_model_profiles() -> str:
    """
    List built-in model profiles and show the active profile.

    Displays the available profiles (`light`, `medium`, `full`) and a
    short summary per profile: `embed_model`, `embed_dim`, `reranker_model`,
    and `approx_ram_mb`. The active profile is marked with `*`.
    """
    if list_profiles is None or get_active_profile is None:
        return "Model profiles not available in this environment."

    profile = _get_profile()
    profiles = list_profiles()

    lines = ["=== Available Model Profiles ===\n"]
    for name, info in profiles.items():
        active_mark = "*" if name == profile.name else " "
        line = (
            f"{active_mark} {name}: embed_model={info['embed_model']}, "
            f"dim={info['embed_dim']}, reranker={info['reranker_model']} "
            f"(~{info['approx_ram_mb']} MB)"
        )
        lines.append(line)

    lines.append(
        "To change profile: set PLESK_MODEL_PROFILE=<name> and restart the server."
    )
    lines.append(
        "If embed_dim changes between profiles, delete storage/lancedb "
        "and run refresh_knowledge."
    )
    return "\n".join(lines)


# --- Source Handling are now in plesk_unified.io_utils ---


# --- Content Parsers ---
def parse_code(file_path: Path) -> Tuple[Optional[str], str, Optional[str]]:
    """Parse a code file and return filename, empty string, and content."""
    try:
        return (
            file_path.name,
            "",
            file_path.read_text(encoding="utf-8", errors="ignore"),
        )
    except Exception:
        logger.warning("Error parsing code file: %s", file_path.name, exc_info=True)
        return None, "", None


# --- Tools ---
def get_toc_map_for_source(source: Dict[str, Any]) -> Dict[str, Any]:
    """Returns the TOC map for HTML sources, or empty dict for others."""
    if source["type"] == "html":
        return io_utils.load_toc_map(source["path"])
    return {}


def build_and_chunk_docs(source, file_path, title, breadcrumb, text):
    """Chunks text and builds document records."""
    if not text or len(text) <= 10:
        return []

    if source["type"] == "html":
        chunks = chunking.chunk_by_chars(text, 1500, 200)
    elif source["type"] == "php":
        chunks = chunking.chunk_by_lines(text, 150, 20)
    else:
        chunks = chunking.chunk_by_lines(text, 60, 10)

    if not chunks:
        return []

    records = chunking.build_doc_records(
        file_path.name,
        chunks,
        {"title": title, "category": source["cat"], "breadcrumb": breadcrumb},
    )

    for r in records:
        r["text"] = f"[{source['cat'].upper()}] {title}\n---\n{r['text']}"

    return records


def process_source_files(source, table, existing_files):
    """Processes all files for a given source and indexes them."""
    toc_map = get_toc_map_for_source(source)
    files = io_utils.collect_files_for_source(source)
    logger.info("Found %d files for source %s", len(files), source["cat"])

    cat_docs = []
    files_processed_count = 0
    BATCH_SIZE_FILES = 50

    for f in files:
        if f.name.startswith("_") or f.name == "toc.json" or f.name in existing_files:
            continue

        meta = toc_map.get(f.name) if toc_map else None

        if source["type"] == "html":
            title, breadcrumb, text = html_utils.parse_html_file(f, meta)
        else:
            title, breadcrumb, text = parse_code(f)

        records = build_and_chunk_docs(source, f, title, breadcrumb, text)
        cat_docs.extend(records)

        files_processed_count += 1
        if files_processed_count >= BATCH_SIZE_FILES:
            if cat_docs:
                logger.info(
                    "Saving batch of %d chunks for %s...", len(cat_docs), source["cat"]
                )
                chunking.persist_batch(table, cat_docs)
                cat_docs = []
            files_processed_count = 0

    if cat_docs:
        logger.info(
            "Saving final batch of %d chunks for %s...", len(cat_docs), source["cat"]
        )
        chunking.persist_batch(table, cat_docs)


@mcp.tool
def refresh_knowledge(
    target_category: str = Field(
        "all",
        description=(
            "Category to index. Choose one: 'guide', 'cli', 'api', 'php-stubs', "
            "'js-sdk' or 'all'."
        ),
    ),
    reset_db: bool = Field(
        False,
        description=(
            "Set to True ONLY for the first run to wipe the database. "
            "Default is False (resume)."
        ),
    ),
):
    """
    Index Plesk documentation into LanceDB.

    Parameters
    - `target_category`: one of 'guide', 'cli', 'api', 'php-stubs', 'js-sdk',
      or 'all'. When not 'all' this indexes only that category.
    - `reset_db`: when True, wipe the DB and perform a full reindex.

    Behavior: incremental by filename when `reset_db` is False; skips files
    already present in the DB. Returns a short per-source report.
    """
    logger.info(
        "Starting refresh_knowledge: target=%s, reset_db=%s", target_category, reset_db
    )
    global _tq_index
    _tq_index = None

    if reset_db:
        table = get_table(create_new=True)
        logger.warning("Database wiped by request.")
        existing_files = set()
    else:
        table = get_table(create_new=False)
        existing_files = set()
        if target_category != "all":
            try:
                results = (
                    table.search()
                    .where(f"category='{target_category}'")
                    .select(["filename"])
                    .limit(10000)
                    .to_list()
                )
                existing_files.update(r["filename"] for r in results)
                logger.info(
                    "Found %d existing files/chunks in DB.", len(existing_files)
                )
            except Exception as e:
                logger.warning("Could not fetch existing files: %s", e)

    report = []

    for source in SOURCES:
        if target_category != "all" and source["cat"] != target_category:
            continue

        logger.info("Processing source: %s", source["cat"])
        if not io_utils.ensure_source_exists(source):
            msg = f"SKIPPED {source['cat']} (Source check failed)"
            logger.error(msg)
            report.append(msg)
            continue

        try:
            process_source_files(source, table, existing_files)
        except Exception:
            logger.exception("Error processing source %s", source["cat"])

        msg = f"Finished pass for {source['cat']}."
        report.append(msg)

    profile = _get_profile()
    if getattr(profile, "use_turboquant", False):
        try:
            _tq_index = _build_tq_index_from_table()
            report.append("TurboQuant index rebuilt and persisted.")
        except Exception:
            logger.exception("Failed to rebuild TurboQuant index after refresh.")
            report.append("ERROR rebuilding TurboQuant index.")

    return "\n".join(report)


@mcp.tool
def search_plesk_unified(query: str, category: str | None = None) -> str:
    """
    Search the unified knowledge base and return up to 5 formatted results.

    `category` may be used to filter results to one of the indexed
    source categories (e.g. 'api', 'cli', 'guide', 'php-stubs', 'js-sdk').
    Results are returned as readable text blocks including title, path,
    filename and a numeric score/distance.
    """
    # Truncate query for logging to avoid leaking sensitive data
    safe_query = (query[:100] + "...") if len(query) > 100 else query
    logger.info("Search request: q='%s' category='%s'", safe_query, category)

    profile = _get_profile()

    if getattr(profile, "use_turboquant", False):
        query_vec = np.asarray(
            get_embedding_model().compute_query_embeddings(query)[0],
            dtype=np.float32,
        )
        tq_results = get_tq_index().search(
            query_vec,
            top_k=profile.tq_top_k,
            category=category,
        )
        results = []
        for meta, score in tq_results[:5]:
            r = dict(meta)
            r["_score_tq"] = score
            results.append(r)
    else:
        table = get_table()

        # Perform the search (no hard-coded pre-limit to allow provider to optimize)
        search_op = table.search(query)
        if category:
            search_op = search_op.where(f"category = '{category}'")

        results = search_op.limit(5).to_list()

    logger.info("Search returned %d results.", len(results))

    formatted_results = []
    for r in results:
        # LanceDB returns `_distance` for vector search and `_score` for FTS.
        # Use .get() to avoid KeyError if the backend changes.
        score = r.get("_score_tq")
        if score is None:
            score = (
                r.get("_distance")
                if r.get("_distance") is not None
                else r.get("_score", 0.0)
            )

        formatted_results.append(
            (
                f"=== {r['category'].upper()} | {r['title']} ===\n"
                f"Path: {r.get('breadcrumb', '')}\n"
                f"File: {r.get('filename', '')}\n"
                f"Score/Distance: {score:.4f}\n\n"
                f"{r.get('text', '')}\n"
            )
        )

    return "\n".join(formatted_results)


if __name__ == "__main__":
    _log_server_ready("Starting Plesk Unified MCP Server...")
    _maybe_start_background_warmup()
    try:
        mcp.run()
    except Exception:
        logger.critical("Server crashed", exc_info=True)
        raise


def main() -> None:
    """Console entrypoint for the MCP server (used by package scripts/devtools)."""
    _log_server_ready("Starting Plesk Unified MCP Server (entrypoint)...")
    _maybe_start_background_warmup()
    try:
        mcp.run()
    except Exception:
        logger.critical("Server crashed (entrypoint)", exc_info=True)
        raise
