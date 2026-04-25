import json
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

# ruff: noqa: E402
from pathlib import Path

_executor = ThreadPoolExecutor(max_workers=4)

# Create logger
logger = logging.getLogger("plesk_unified")

from typing import Annotated, Any, Dict, Optional

from fastmcp import Context, FastMCP
from pydantic import Field

from plesk_unified.settings import settings
from plesk_unified import chunking, io_utils
from plesk_unified.ai_client import AIClient
from plesk_unified.error_handling import tool_error_boundary
from plesk_unified.indexing import JobRegistry
from plesk_unified.model_config import get_active_profile, list_profiles
from plesk_unified.tq_index import TurboQuantIndex
from plesk_unified.types import CategoryEnum, CategoryOrAll


async def _report_progress(
    ctx: Optional[Context], current: int, total: int = 4
) -> None:
    """
    Resiliently report progress to MCP client,
    handling sync/async and missing methods.
    """
    if not ctx or not hasattr(ctx, "report_progress"):
        return

    try:
        import inspect

        # Check if the method is an async coroutine or a sync function
        if inspect.iscoroutinefunction(ctx.report_progress):
            await ctx.report_progress(current, total)
        else:
            ctx.report_progress(current, total)
    except Exception as e:
        # Progress reporting should never crash the main operation
        logger.debug("Failed to report progress: %s", e)


# Initialize MCP — fast, no heavy work here
mcp = FastMCP("mcp-plesk-unified")

# Job Registry for background tasks
job_registry = JobRegistry()

# --- Configuration ---
BASE_DIR = Path(__file__).parent.parent
KB_DIR = BASE_DIR / "knowledge_base"

# Note: CHUNK_VERSION has moved to chunking.py to ensure it stays in sync
# with the hashing logic.

VALID_CATEGORIES: frozenset[str] = frozenset(c.value for c in CategoryEnum)


def _validate_category(
    category: str | CategoryEnum | None,
    *,
    allow_all: bool = False,
    parameter_name: str = "category",
) -> None:
    if category is None:
        return
    if allow_all and category == "all":
        return
    if category not in VALID_CATEGORIES:
        allowed = sorted(VALID_CATEGORIES)
        if allow_all:
            raise ValueError(
                f"Invalid {parameter_name}: {category!r}. "
                f"Must be one of {allowed} or 'all'."
            )
        raise ValueError(
            f"Invalid {parameter_name}: {category!r}. Must be one of {allowed}."
        )


from plesk_unified.config.sources import DEFAULT_SOURCES

SOURCES = [
    {
        "path": s.path,
        "cat": s.category.value,
        "type": s.source_type,
        "repo_url": s.repo_url,
        "zip_url": s.zip_url,
    }
    for s in DEFAULT_SOURCES.all()
]

# Map each category that has a known Plesk Docs zip URL to its documentation
# base URL.  Derived automatically from SOURCES so changes to zip_url propagate.
# Pattern: https://.../zip/<name>.zip  →  https://.../<name>/
# GitHub-only sources (php-stubs, js-sdk) are absent from this mapping.
CATEGORY_DOC_BASE_URLS: dict[str, str] = {
    src["cat"]: src["zip_url"].replace("/zip/", "/").removesuffix(".zip") + "/"
    for src in SOURCES
    if src.get("zip_url")
}


def _build_doc_url(category: str, filename: str) -> str | None:
    """Return a fully-qualified documentation URL for *filename* in *category*.

    Returns ``None`` for categories without a known documentation base URL
    (``php-stubs``, ``js-sdk``) or when *filename* is empty.
    """
    base = CATEGORY_DOC_BASE_URLS.get(category)
    if base and filename:
        return base + filename
    return None


# --- Lazy Initialization ---
# The embedding model (~1.5 GB) is loaded on first tool call, NOT at import time.
# This lets the MCP server respond to `initialize` in <2 seconds.


from plesk_unified.infrastructure.runtime.model_runtime import ModelRuntime

_model_runtime = ModelRuntime()


def _get_profile():
    return _model_runtime.get_profile()


def _db_profile_name() -> str:
    profile = _get_profile()
    # full-tq shares embeddings/dimension with full, so reuse full's LanceDB corpus.
    return "full" if getattr(profile, "use_turboquant", False) else profile.name


SOURCE_STATE_PATH = BASE_DIR / "storage" / "source_state.json"


def _detect_device() -> str:
    return _model_runtime.detect_device()


def get_embedding_model() -> Any:
    return _model_runtime.get_embedding_model()


def get_schema() -> Any:
    return _model_runtime.get_schema()


def get_reranker() -> Any:
    return _model_runtime.get_reranker()


from plesk_unified.infrastructure.runtime.storage_runtime import StorageRuntime

_storage_runtime = StorageRuntime(BASE_DIR, _model_runtime)


def get_table(create_new: bool = False) -> Any:
    return _storage_runtime.get_table(create_new=create_new)


def _get_tq_index_path() -> Path:
    return _storage_runtime.get_tq_index_path()


def _save_tq_index(tq_index: TurboQuantIndex) -> None:
    return _storage_runtime.save_tq_index(tq_index)


def _load_tq_index() -> TurboQuantIndex | None:
    return _storage_runtime.load_tq_index()


def _build_tq_index_from_table() -> TurboQuantIndex:
    return _storage_runtime.build_tq_index_from_table()


def get_tq_index() -> TurboQuantIndex:
    return _storage_runtime.get_tq_index()


def _table_health() -> tuple[bool, str | None]:
    return _storage_runtime.table_health()


from plesk_unified.infrastructure.repositories.source_state_repository import (
    SourceStateRepository,
)
from plesk_unified.infrastructure.repositories.lancedb_repository import (
    LanceDbRepository,
)
from plesk_unified.infrastructure.repositories.turboquant_repository import (
    TurboQuantRepository,
)

_source_state_repo = SourceStateRepository(BASE_DIR / "storage" / "source_state.json")
_lancedb_repo = LanceDbRepository(_storage_runtime)
_turboquant_repo = TurboQuantRepository(_storage_runtime)


def _load_source_state() -> dict[str, Any]:
    return _source_state_repo.load()


def _save_source_state(state: dict[str, Any]) -> None:
    return _source_state_repo.save(state)


def _existing_filenames_for_category(table: Any, category: str) -> set[str]:
    return _lancedb_repo.get_existing_filenames(category)


def _infer_html_doctype(cat: str, trail: str) -> str:
    if cat == "cli" or "command line" in trail:
        return "cli-command"
    if cat == "api" or "reference" in trail:
        return "api-reference"
    if cat == "guide" or "guide" in trail:
        return "guide-topic"
    return f"{cat}-html"


def _infer_php_doctype(name: str) -> str:
    if "interface" in name:
        return "php-stub-interface"
    if "trait" in name:
        return "php-stub-trait"
    return "php-stub-class"


def _infer_js_doctype(filename: str) -> str:
    if filename.lower().endswith(".md"):
        return "js-sdk-guide"
    if filename.lower().endswith(".test.js"):
        return "js-sdk-test"
    return "js-sdk-source"


def _infer_doctype(
    source: Dict[str, Any], filename: str, title: str | None, breadcrumb: str | None
) -> str:
    """Infer the document type based on source category, title, and file pattern."""
    stype = source.get("type", "")
    if stype == "html":
        return _infer_html_doctype(source.get("cat", ""), (breadcrumb or "").lower())
    if stype == "php":
        return _infer_php_doctype((title or filename or "").lower())
    if stype == "js":
        return _infer_js_doctype(filename)
    return "unknown"


def _chunk_by_doctype(source: Dict[str, Any], doctype: str, text: str) -> list[str]:
    if source["type"] == "html":
        chunks = chunking.chunk_by_sentence_window(text, window_size=3)
        return chunks or chunking.chunk_by_chars(text, 1500, 200)

    if source["type"] == "php":
        chunks = chunking.chunk_php_hierarchical(
            text, section_max_lines=150, overlap=20
        )
        return chunks or chunking.chunk_by_lines(text, 150, 20)

    if doctype == "js-sdk-guide":
        chunks = chunking.chunk_by_sentence_window(text, window_size=3)
        return chunks or chunking.chunk_by_lines(text, 60, 10)

    chunks = chunking.chunk_js_hierarchical(text, section_max_lines=60, overlap=10)
    return chunks or chunking.chunk_by_lines(text, 60, 10)


from plesk_unified.application.services.warmup_service import WarmupService

_warmup_service = WarmupService(settings, _model_runtime, _storage_runtime)


def _begin_warmup() -> bool:
    return _warmup_service.begin_warmup()


def _finish_warmup(error: Exception | None = None) -> None:
    return _warmup_service.finish_warmup(error)


def _run_warmup_sequence() -> list[str]:
    return _warmup_service.run_warmup_sequence()


def _background_warmup_worker() -> None:
    return _warmup_service._background_warmup_worker()


def _maybe_start_background_warmup() -> None:
    return _warmup_service.maybe_start_background_warmup()


@mcp.tool
@tool_error_boundary
async def warmup_server(ctx: Optional[Context] = None) -> str:
    """Preload the active profile models and table without running indexing."""
    await _report_progress(ctx, 1, 4)  # load start

    if not _begin_warmup():
        return "Warmup already running."

    try:
        loop = asyncio.get_running_loop()
        parts = await loop.run_in_executor(_executor, _run_warmup_sequence)
        await _report_progress(ctx, 2, 4)  # load complete

        # Report progress for index check
        await _report_progress(ctx, 3, 4)  # index check

        _finish_warmup()
        await _report_progress(ctx, 4, 4)  # done
    except Exception as exc:
        _finish_warmup(exc)
        logger.exception("Manual warmup failed.")
        raise

    return "\n".join(parts)


from plesk_unified.application.services.health_service import HealthService

_health_service = HealthService(
    settings, _model_runtime, _storage_runtime, _warmup_service
)


@mcp.tool
@tool_error_boundary
async def daemon_health() -> str:
    """Return daemon-centric readiness status for warmup and indexed search paths."""
    report = _health_service.get_health_report()
    return json.dumps(report, indent=2)


@mcp.tool
@tool_error_boundary
async def list_model_profiles() -> str:
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


# --- Tools ---
def get_toc_map_for_source(source: Dict[str, Any]) -> Dict[str, Any]:
    """Returns the TOC map for HTML sources, or empty dict for others."""
    if source["type"] == "html":
        return io_utils.load_toc_map(source["path"])
    return {}


from plesk_unified.summary_cache import SummaryCache


async def _get_summary(
    f: Path,
    text: str,
    ai_client: Optional[AIClient],
    semaphore: asyncio.Semaphore,
    cache: Optional[SummaryCache],
) -> Optional[str]:
    """Retrieves summary from cache or AI API."""
    if not settings.plesk_index_summaries or not text:
        return None

    summary = cache.get(f) if cache else None
    if summary:
        logger.info("Using cached summary for %s", f.name)
        return summary

    if ai_client:
        async with semaphore:
            summary = await ai_client.generate_description_async(text)
            if summary == "Description unavailable.":
                logger.warning("Summary unavailable for %s", f.name)
                return None
            if cache:
                cache.set(f, summary)
            return summary
    return None


@mcp.tool
@tool_error_boundary
async def trigger_index_sync(
    ctx: Optional[Context] = None,
    category: Annotated[CategoryOrAll, Field(description="Category to index.")] = "all",
    reset_db: Annotated[
        bool, Field(description="Force a full re-index by wiping the database first.")
    ] = False,
) -> dict:
    """Trigger async re-indexing of Plesk documentation. Returns job_id immediately."""

    def job_wrapper(cat: CategoryOrAll, reset: bool) -> str:
        # Since refresh_knowledge is now async, we run it in a new event loop
        # inside this background thread. Pass None as the context.
        res = asyncio.run(refresh_knowledge(None, cat, reset))
        if isinstance(res, str) and res.startswith("[ERROR]"):
            raise RuntimeError(res)
        return res

    job_id = job_registry.submit_job(job_wrapper, category, reset_db)
    return {"job_id": job_id, "status": "queued"}


@mcp.tool
@tool_error_boundary
async def check_sync_status(
    job_id: Annotated[
        str, Field(description="The job_id returned by trigger_index_sync.")
    ],
) -> dict:
    """Check the status of a background indexing job by job_id."""
    return job_registry.get_status(job_id)


@mcp.tool
@tool_error_boundary
async def requantize_knowledge() -> str:
    """
    Rebuild the TurboQuant index from already-stored LanceDB vectors.

    This is useful if you change TurboQuant quantization settings or bits
    in a model profile, or if the TQ index is missing but LanceDB is populated.
    It performs NO new embedding work and NO document chunking.
    """
    profile = _get_profile()
    if not getattr(profile, "use_turboquant", False):
        return f"TurboQuant is disabled for the active profile '{profile.name}'."

    logger.info("Starting requantize_knowledge for profile %s", profile.name)
    global _tq_index
    loop = asyncio.get_running_loop()
    try:
        _tq_index = await loop.run_in_executor(_executor, _build_tq_index_from_table)
        return f"TurboQuant index rebuilt successfully for profile '{profile.name}'."
    except Exception as e:
        logger.exception("Manual requantization failed.")
        return f"Error rebuilding TurboQuant index: {e}"


from plesk_unified.formatting.search_formatter import SearchFormatter
from plesk_unified.application.services.search_service import SearchService

_search_formatter = SearchFormatter(DEFAULT_SOURCES)

_search_service = SearchService(
    settings,
    _model_runtime,
    _storage_runtime,
    _lancedb_repo,
    _turboquant_repo,
    _search_formatter,
)

from plesk_unified.application.services.indexing_service import IndexingService
from plesk_unified.infrastructure.parsers.processor_registry import ProcessorRegistry
from plesk_unified.infrastructure.repositories.summary_cache_repository import (
    SummaryCacheRepository,
)

_summary_cache_repo = SummaryCacheRepository(
    BASE_DIR / "storage" / "summaries_cache.json"
)
_processor_registry = ProcessorRegistry()

_indexing_service = IndexingService(
    settings,
    _model_runtime,
    _storage_runtime,
    _lancedb_repo,
    _turboquant_repo,
    _source_state_repo,
    _summary_cache_repo,
    _processor_registry,
    DEFAULT_SOURCES,
    _executor,
)


async def refresh_knowledge(
    ctx: Optional[Context] = None,
    target_category: Annotated[
        CategoryOrAll, Field(description="Category to index.")
    ] = "all",
    reset_db: Annotated[
        bool,
        Field(
            description=(
                "Set to True ONLY for the first run to wipe the database. "
                "Default is False (resume)."
            )
        ),
    ] = False,
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
    return await _indexing_service.refresh_knowledge(ctx, target_category, reset_db)


@mcp.tool
@tool_error_boundary
async def search_plesk_unified(
    ctx: Optional[Context] = None,
    query: Annotated[Optional[str], Field(description="Search query")] = None,
    category: Annotated[
        Optional[CategoryEnum], Field(description="Category to filter by")
    ] = None,
) -> str:
    """
    Search the unified knowledge base and return up to 5 formatted results.

    IMPORTANT: When using these results to answer a user's question, you MUST
    rely ONLY on the facts provided in the text. Cite the source using the filename.
    If the provided context does not contain enough information to answer the
    query, clearly state that you do not have enough information rather than
    guessing or hallucinating facts.

    `category` may be used to filter results to one of the indexed
    source categories (e.g. 'api', 'cli', 'guide', 'php-stubs', 'js-sdk').
    Results are returned as readable text blocks including title, path,
    filename and a relevance score between 0 and 1.
    """
    return await _search_service.search(
        ctx, query, category.value if category else None
    )


# --- Prompts ---


@mcp.prompt(name="plesk-extension-dev-guide")
def plesk_extension_dev_guide(extension_name: str, target_language: str) -> str:
    """
    Generate a starter guide for developing a new Plesk extension.
    """
    return f"""You are an expert Plesk Extension developer.
Help me design and implement a new Plesk extension called "{extension_name}"
using {target_language}.

Please follow these steps:
1. Use `search_plesk_unified(query="{extension_name} development guide",
   category="guide")` to find relevant architectural patterns.
2. Use `search_plesk_unified(query="{target_language} sdk hooks",
   category="js-sdk" if "{target_language}".lower() == "javascript" else "php-stubs")`
   to find specific implementation details.
3. Provide a step-by-step roadmap including directory structure,
   `meta.xml` configuration, and a basic code example.

Goal: Create a robust, secure, and idiomatic Plesk extension."""


@mcp.prompt(name="plesk-api-integration")
def plesk_api_integration(api_operation: str) -> str:
    """
    Instructions and examples for integrating with a Plesk API operation.
    """
    return f"""You are a technical expert in Plesk API integrations.
I need to implement the "{api_operation}" operation in my application.

Please:
1. Search for the "{api_operation}" specification using
   `search_plesk_unified(query="{api_operation}", category="api")`.
2. Explain whether this should use the XML-RPC API or the REST API.
3. Provide a complete request example (XML or JSON) and describe the
   expected response.
4. Detail any specific permissions or security considerations for this
   operation.

Focus on accuracy and compliance with the Plesk Obsidian API standards."""


@mcp.prompt(name="plesk-cli-reference")
def plesk_cli_reference(command_name: str) -> str:
    """
    Get detailed reference information for a Plesk CLI command.
    """
    return f"""You are a Plesk Linux administrator and CLI expert.
I need a comprehensive reference for the `{command_name}` command.

Please:
1. Retrieve the command details using
   `search_plesk_unified(query="{command_name}", category="cli")`.
2. Summarize the command's primary purpose.
3. List the most important subcommands and options with brief explanations.
4. Provide 2-3 practical examples of how to use this command in daily
   administration or automation.

Ensure the information is clear, concise, and technically accurate."""


# --- Resources ---

from plesk_unified.formatting.toc_formatter import TocFormatter

_toc_formatter = TocFormatter(DEFAULT_SOURCES)


def _handle_toc_resource(category: str) -> str:
    from plesk_unified.io_utils import get_toc_map_for_source

    source_def = DEFAULT_SOURCES.by_category(category)
    if not source_def:
        return f"Category '{category}' not found."
    legacy_source = {
        "path": source_def.path,
        "cat": source_def.category.value,
        "type": source_def.source_type,
    }
    toc_map = get_toc_map_for_source(legacy_source)
    return _toc_formatter.format_markdown(category, toc_map)


@mcp.resource("plesk://toc/api")
def plesk_toc_api() -> str:
    """Table of Contents for Plesk API documentation."""
    return _handle_toc_resource("api")
