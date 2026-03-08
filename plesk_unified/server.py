import logging

# ruff: noqa: E402
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# --- LOGGING SETUP ---
# Must be done before importing heavy libraries.
# This ensures we capture their initialization warnings if needed.
BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "storage" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
from dotenv import load_dotenv

load_dotenv()

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

# 1. File Handler (Rotating)
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10_485_760,
    backupCount=5,
    encoding="utf-8",  # 10MB
)
file_handler.setFormatter(formatter)
file_handler.setLevel(LOG_LEVEL)

# 2. Stream Handler (stderr) - CRITICAL for MCP protocol
stream_handler = logging.StreamHandler(sys.stderr)
stream_handler.setFormatter(formatter)
stream_handler.setLevel(LOG_LEVEL)

# Avoid adding duplicate handlers if reloaded
if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

# Silence noisy third-party libraries unless they error
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("git").setLevel(logging.WARNING)

logger.info(f"Logging initialized. Level: {LOG_LEVEL_NAME}, File: {LOG_FILE}")


# --- SILENCE THE NOISE ---
os.environ["TQDM_DISABLE"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

from typing import Any, Dict, Optional, Tuple

import lancedb  # type: ignore
from fastmcp import FastMCP
from pydantic import Field

try:
    from plesk_unified import chunking, html_utils, io_utils
    from plesk_unified.model_config import get_active_profile, list_profiles
except ImportError:
    import chunking
    import html_utils
    import io_utils

    try:
        from model_config import get_active_profile, list_profiles  # type: ignore
    except Exception:
        get_active_profile = None  # type: ignore
        list_profiles = None  # type: ignore

# Initialize MCP — fast, no heavy work here
mcp = FastMCP("mcp-plesk-unified")

# --- Configuration ---
KB_DIR = BASE_DIR / "knowledge_base"
DB_PATH = BASE_DIR / "storage" / "lancedb"

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
        "type": "md",
        "repo_url": None,
        "zip_url": "https://docs.plesk.com/en-US/obsidian/zip/api-rpc.zip",
    },
    {
        "path": KB_DIR / "cli-linux",
        "cat": "cli",
        "type": "md",
        "repo_url": None,
        "zip_url": "https://docs.plesk.com/en-US/obsidian/zip/cli-linux.zip",
    },
    {
        "path": KB_DIR / "extensions-guide",
        "cat": "guide",
        "type": "md",
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


def _get_profile():
    global _active_profile
    if _active_profile is None:
        if get_active_profile is None:
            raise RuntimeError("model_config.get_active_profile not available")
        _active_profile = get_active_profile()
    return _active_profile


def _detect_device() -> str:
    """Detect the best available compute device (CUDA > MPS > CPU)."""
    try:
        import torch

        if torch.cuda.is_available():
            logger.info("NVIDIA GPU (CUDA) detected. Using for acceleration.")
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            logger.info("Apple Silicon GPU (MPS) detected. Using for acceleration.")
            return "mps"
        logger.info("No GPU acceleration available. Using CPU.")
        return "cpu"
    except ImportError:
        logger.warning("Torch not available; using CPU.")
        return "cpu"
    except Exception:
        logger.warning("Error detecting device; using CPU.", exc_info=True)
        return "cpu"


def get_embedding_model() -> Any:
    """Return the embedding model, initializing it on first call."""
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    from lancedb.embeddings import get_registry  # type: ignore

    profile = _get_profile()
    device = _detect_device()
    logger.info("Initializing embedding model %s on %s...", profile.embed_model, device)
    try:
        reg = get_registry().get("huggingface")
        try:
            _embedding_model = reg.create(name=profile.embed_model, device=device)
        except TypeError:
            logger.debug("Device argument rejected, retrying without device kwarg.")
            _embedding_model = reg.create(name=profile.embed_model)
        logger.info("Embedding model initialized successfully.")
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
    try:
        from sentence_transformers import CrossEncoder  # type: ignore

        device = _detect_device()
        _reranker = CrossEncoder(profile.reranker_model, device=device)
        logger.info("Reranker initialized on %s.", device)
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
    logger.info("Starting Plesk Unified MCP Server...")
    try:
        mcp.run()
    except Exception:
        logger.critical("Server crashed", exc_info=True)
        raise


def main() -> None:
    """Console entrypoint for the MCP server (used by package scripts/devtools)."""
    logger.info("Starting Plesk Unified MCP Server (entrypoint)...")
    try:
        mcp.run()
    except Exception:
        logger.critical("Server crashed (entrypoint)", exc_info=True)
        raise
