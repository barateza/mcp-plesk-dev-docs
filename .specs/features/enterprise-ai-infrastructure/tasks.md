# Enterprise AI Infrastructure Uplift — Tasks

**Design**: `.specs/features/enterprise-ai-infrastructure/design.md`
**Status**: Draft

---

## Execution Plan

### Phase 1 — M1: Foundation (Sequential)

```
T01 → T02 → T03 → T04
```

All four tasks are sequential: settings must exist before categories, categories before error boundary, error boundary before telemetry.

### Phase 2 — M2: Async Core (Partially Parallel)

```
T01–T04 complete, then:
      ┌→ T05 (indexing.py) ─┐
T04 ──┼→ T06 (async tools) ─┼──→ T08 (CDI lifespan)
      └→ T07 (job tools)   ─┘
```

T05, T06, T07 can be developed in parallel after M1 completes. T08 depends on T06.

### Phase 3 — M3: Protocol Richness (Parallel)

```
T08 complete, then:
      ┌→ T09 (TOC resource) ────────────────────┐
T08 ──┼→ T10 (prompt templates) ───────────────┼──→ T13 (integration test)
      ├→ T11 (progress notifications) ─────────┤
      └→ T12 (LLM sampling) ──────────────────-┘
```

### Phase 4 — M4: Observability (Parallel)

```
T06 complete (async search), then:
      ┌→ T14 (search telemetry) ─┐
T06 ──┼→ T15 (rich markdown)    ─┼──→ (independent)
      └→ T16 (VRAM auto-tune)   ─┘
```

### Phase 5 — M5: Infra & Security (Parallel)

```
All prior phases complete (or run independently), then:
      ┌→ T17 (Dockerfile)   ─────────────┐
      ├→ T18 (Roots + path guard) ───────┼──→ T21 (final validation)
      ├→ T19 (drift CI workflow) ────────┤
      └→ T20 (benchmark CI workflow) ────┘
```

---

## Task Breakdown

---

### T01: Create `plesk_unified/settings.py` with `PleskSettings`

**What**: Define a `pydantic-settings` `BaseSettings` subclass that declares all environment variables used across `server.py` and `model_config.py`, with types, defaults, and validators.

**Where**: `plesk_unified/settings.py` (new file)

**Depends on**: None

**Reuses**: Existing env var names from `server.py:24-27` and `model_config.py:110-145`

**Tools**:
- MCP: filesystem
- Skill: coding-guidelines

**Done when**:
- [ ] `PleskSettings` class defined with all 12 fields: `log_level`, `log_file`, `log_handler`, `plesk_model_profile`, `plesk_embed_model`, `plesk_reranker_model`, `plesk_reranker_enabled`, `plesk_embed_dim`, `force_device`, `plesk_daemon_auto_warmup`, `openrouter_api_key`, `plesk_enable_sampling`
- [ ] `Literal` type constraints applied to `log_level`, `log_handler`, `plesk_model_profile`, `force_device`
- [ ] `get_settings()` cached singleton function exported
- [ ] `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)` set
- [ ] `python -c "from plesk_unified.settings import get_settings; get_settings()"` exits 0

**Verify**:
```bash
PLESK_MODEL_PROFILE=bad python -c "from plesk_unified.settings import get_settings; get_settings()"
# Expected: pydantic_settings.ValidationError listing valid choices
```

---

### T02: Wire `PleskSettings` into `server.py` and `model_config.py`

**What**: Replace all 12 `os.environ.get()` / `os.environ.get()` calls in `server.py` (lines 24-27, 57, 374-376) and `model_config.py` (lines 110-145) with `get_settings()` attribute access.

**Where**: `plesk_unified/server.py` (modify), `plesk_unified/model_config.py` (modify)

**Depends on**: T01

**Reuses**: `get_settings()` from T01

**Tools**:
- MCP: filesystem

**Done when**:
- [ ] All `os.environ.get("LOG_LEVEL", ...)` etc. calls removed from both files
- [ ] `LOG_LEVEL`, `LOG_FILE`, `LOG_HANDLER` in `server.py` replaced with `settings.log_level` etc.
- [ ] `PLESK_MODEL_PROFILE`, `PLESK_EMBED_MODEL` etc. in `model_config.py` replaced with `settings.*`
- [ ] `_env_flag("PLESK_DAEMON_AUTO_WARMUP")` in `server.py` replaced with `settings.plesk_daemon_auto_warmup`
- [ ] `python -m pytest tests/test_model_config.py tests/test_startup_path.py` passes

**Verify**:
```bash
python -m pytest tests/test_model_config.py tests/test_startup_path.py -v
```

---

### T03: Create `plesk_unified/types.py` with `CategoryEnum`

**What**: Define `CategoryEnum(str, Enum)` with the 5 valid categories and a `CategoryOrAll` union type alias.

**Where**: `plesk_unified/types.py` (new file)

**Depends on**: None (can develop in parallel with T01, but must be complete before T04)

**Reuses**: The 5 category strings from `SOURCES` in `server.py:105-139`

**Tools**:
- MCP: filesystem

**Done when**:
- [ ] `CategoryEnum` with members `GUIDE="guide"`, `CLI="cli"`, `API="api"`, `PHP_STUBS="php-stubs"`, `JS_SDK="js-sdk"`
- [ ] `CategoryOrAll = Union[CategoryEnum, Literal["all"]]` type alias defined
- [ ] `search_plesk_unified` signature updated: `category: CategoryEnum | None = None`
- [ ] `refresh_knowledge` signature updated: `target_category: CategoryOrAll = "all"`
- [ ] `python -m pytest tests/` passes
- [ ] FastMCP schema for `search_plesk_unified` contains `"enum": ["guide","cli","api","php-stubs","js-sdk"]` in `category` property

**Verify**:
```bash
python -c "
from plesk_unified.server import mcp
import json
schema = mcp.get_tool('search_plesk_unified')
print(json.dumps(schema, indent=2))
"
# Assert 'enum' key appears in category property
```

---

### T04: Create `plesk_unified/error_handling.py` with `@tool_error_boundary`

**What**: Implement the `tool_error_boundary` decorator that wraps both sync and async tool functions, catches all exceptions, logs the full traceback, and returns a classified sanitized error string.

**Where**: `plesk_unified/error_handling.py` (new file)

**Depends on**: T01 (uses `get_settings()` for log configuration)

**Reuses**: Module-level `logger = logging.getLogger("plesk_unified")` pattern from `log_handler.py`; error classification map from design doc

**Tools**:
- MCP: filesystem
- Skill: coding-guidelines

**Done when**:
- [ ] `tool_error_boundary` decorator implemented for both `def` and `async def` functions (uses `inspect.iscoroutinefunction`)
- [ ] `_classify_error(exc) -> str` maps 5 exception types to guidance strings per design
- [ ] Applied to `refresh_knowledge`, `search_plesk_unified`, `warmup_server`, `daemon_health`, `list_model_profiles` in `server.py`
- [ ] No Python file paths or variable names appear in the returned error strings
- [ ] `python -m pytest tests/` passes

**Verify**:
```bash
python -c "
from unittest.mock import patch
from plesk_unified.server import search_plesk_unified
# search without warmup should return [ERROR] not raise
result = search_plesk_unified('test')
assert result.startswith('[ERROR]'), f'Expected [ERROR], got: {result[:50]}'
print('OK')
"
```

---

### T05: Create `plesk_unified/indexing.py` with `JobRegistry` [P]

**What**: Extract `process_source_files`, `build_and_chunk_docs`, `get_toc_map_for_source` from `server.py` into `indexing.py`. Add `JobStatus` dataclass and `JobRegistry` class with `submit_job` / `get_job_status`.

**Where**: `plesk_unified/indexing.py` (new file); `plesk_unified/server.py` (modify — remove extracted functions)

**Depends on**: T01–T04 (M1 complete)

**Reuses**: `_background_warmup_worker` threading pattern from `server.py:431-441`; `process_source_files` logic moved verbatim initially

**Tools**:
- MCP: filesystem

**Done when**:
- [ ] `JobStatus` dataclass defined with all fields from design: `job_id`, `status`, `progress`, `current_source`, `files_processed`, `total_files`, `report`, `error`, `created_at`, `updated_at`
- [ ] `JobRegistry` class with `submit_job(target_category, reset_db) -> str` and `get_job_status(job_id) -> JobStatus` implemented
- [ ] Background thread updates `JobStatus.progress` after each file batch using `files_processed / total_files * 100`
- [ ] `submit_job` returns within 200 ms on any hardware
- [ ] `get_job_status` with unknown `job_id` returns `JobStatus(status="not_found")`
- [ ] All extracted functions still importable from `server.py` via re-export for backward compat
- [ ] `python -m pytest tests/` passes

**Verify**:
```bash
python -c "
from plesk_unified.indexing import JobRegistry
jr = JobRegistry()
jid = jr.submit_job('guide', False)
import time; start = time.time()
status = jr.get_job_status(jid)
assert time.time() - start < 0.2, 'submit_job too slow'
assert status.status in ('queued', 'running'), f'Unexpected: {status.status}'
print('OK:', jid)
"
```

---

### T06: Convert tool handlers to `async def` [P]

**What**: Convert `search_plesk_unified`, `warmup_server`, `daemon_health`, `list_model_profiles` to `async def`. Wrap all CPU-bound ML calls in `asyncio.get_event_loop().run_in_executor(_executor)`.

**Where**: `plesk_unified/server.py` (modify)

**Depends on**: T01–T04 (M1 complete)

**Reuses**: Existing function bodies; wraps synchronous ML logic in executor calls

**Tools**:
- MCP: filesystem
- Skill: coding-guidelines

**Done when**:
- [ ] Module-level `_executor = ThreadPoolExecutor(max_workers=4)` defined
- [ ] `search_plesk_unified` is `async def` with `get_embedding_model()` + TurboQuant search wrapped in `run_in_executor`
- [ ] `warmup_server`, `daemon_health`, `list_model_profiles` are `async def`
- [ ] `daemon_health` responds in < 50 ms while `search_plesk_unified` is running (verified by concurrency test below)
- [ ] `python -m pytest tests/` passes

**Verify**:
```bash
python -c "
import asyncio
from plesk_unified.server import search_plesk_unified, daemon_health

async def test():
    search_task = asyncio.create_task(search_plesk_unified('test'))
    health = await daemon_health()
    assert health  # not empty
    await search_task  # completes eventually
    print('OK')

asyncio.run(test())
"
```

---

### T07: Expose `trigger_index_sync` and `check_sync_status` as MCP tools [P]

**What**: Register `trigger_index_sync` and `check_sync_status` as `@mcp.tool` endpoints. Update `refresh_knowledge` to be a backward-compatible async adapter.

**Where**: `plesk_unified/server.py` (modify)

**Depends on**: T05 (`JobRegistry` available), T06 (async pattern established)

**Reuses**: `JobRegistry` from T05; `@tool_error_boundary` from T04

**Tools**:
- MCP: filesystem

**Done when**:
- [ ] `trigger_index_sync(target_category: CategoryOrAll, reset_db: bool) -> str` registered as `@mcp.tool`; returns JSON string `{"job_id": "...", "status": "queued"}`
- [ ] `check_sync_status(job_id: str) -> str` registered as `@mcp.tool`; returns JSON string with full `JobStatus` fields
- [ ] `refresh_knowledge` updated to call `trigger_index_sync` and poll until done; same return format as before
- [ ] Both new tools decorated with `@tool_error_boundary`
- [ ] `python -m pytest tests/` passes

**Verify**:
```bash
python -c "
from plesk_unified.server import mcp
tools = {t.name for t in mcp.list_tools()}
assert 'trigger_index_sync' in tools
assert 'check_sync_status' in tools
print('OK')
"
```

---

### T08: Refactor globals to FastMCP `Context` lifespan state

**What**: Move `_embedding_model`, `_tq_index`, `_reranker`, `_active_profile` from module-level globals to a `@mcp.lifespan` context object so they are injected via `Context` rather than mutated globally.

**Where**: `plesk_unified/server.py` (modify)

**Depends on**: T06 (async tools exist), T07 (job tools exist)

**Reuses**: FastMCP lifespan pattern from FastMCP ≥ 3.2.0 documentation

**Tools**:
- MCP: filesystem
- Skill: coding-guidelines

**Done when**:
- [ ] `@asynccontextmanager async def lifespan(server)` defined; yields `AppState` dataclass with `embedding_model`, `tq_index`, `reranker`, `profile`
- [ ] All `@mcp.tool` functions accept `ctx: Context` and access state via `ctx.request_context.lifespan_context`
- [ ] Module-level `_embedding_model` etc. removed or kept only as backward-compat aliases
- [ ] `python -m pytest tests/` passes

**Verify**:
```bash
python -m pytest tests/test_startup_path.py -v
```

---

### T09: Create `plesk_unified/toc_resource.py` with `@mcp.resource` [P]

**What**: Implement the `plesk://toc/{category}` MCP resource endpoint that returns the TOC hierarchy for a given category as a JSON string.

**Where**: `plesk_unified/toc_resource.py` (new file)

**Depends on**: T08 (Context lifespan established), T03 (`CategoryEnum` defined)

**Reuses**: `io_utils.load_toc_map` (existing); `SOURCES` path mapping from `server.py`; `generate_virtual_toc.py` script logic for fallback

**Tools**:
- MCP: filesystem

**Done when**:
- [ ] `@mcp.resource("plesk://toc/{category}")` async function defined and registered
- [ ] When `toc.json` exists: returns parsed hierarchy as `{"category": ..., "entries": [...], "virtual": false}`
- [ ] When `toc.json` absent: generates virtual TOC from directory listing; returns with `"virtual": true`
- [ ] When `category` is invalid: raises `ValueError` (caught by FastMCP as resource error)
- [ ] `toc_resource.py` imported in `server.py` so resources are registered at startup
- [ ] `python -m pytest tests/` passes

**Verify**:
```bash
python -c "
from plesk_unified import toc_resource
import json
# test with a mock source path
result = toc_resource._load_toc('guide')
assert isinstance(result, dict)
assert 'entries' in result
print('OK')
"
```

---

### T10: Create `plesk_unified/prompts.py` with `@mcp.prompt` templates [P]

**What**: Implement three `@mcp.prompt` templates: `plesk-extension-dev-guide`, `plesk-api-integration`, `plesk-cli-reference`. Each returns a message list seeded with the category TOC and 3 seed search results.

**Where**: `plesk_unified/prompts.py` (new file)

**Depends on**: T09 (TOC resource available), T06 (async search available)

**Reuses**: `search_plesk_unified` internal logic for seed queries; `toc_resource._load_toc` for context

**Tools**:
- MCP: filesystem

**Done when**:
- [ ] Three `@mcp.prompt` functions defined with appropriate `name` and `description`
- [ ] Each prompt calls `_load_toc(category)` and issues 2–3 seed searches via the internal search logic
- [ ] Returns `list[Message]` with `system` and `user` message roles
- [ ] `prompts.py` imported in `server.py` so prompts register at startup
- [ ] `python -m pytest tests/` passes

**Verify**:
```bash
python -c "
from plesk_unified.server import mcp
prompts = {p.name for p in mcp.list_prompts()}
assert 'plesk-extension-dev-guide' in prompts
assert 'plesk-api-integration' in prompts
assert 'plesk-cli-reference' in prompts
print('OK')
"
```

---

### T11: Add `ctx.report_progress` notifications to `refresh_knowledge` and `search_plesk_unified` [P]

**What**: Inject `Context` into `refresh_knowledge` (via `trigger_index_sync`) and `search_plesk_unified`. Call `ctx.report_progress(current, total)` at defined checkpoints.

**Where**: `plesk_unified/server.py` (modify), `plesk_unified/indexing.py` (modify)

**Depends on**: T06 (async tools), T07 (job architecture)

**Reuses**: FastMCP `Context.report_progress` API

**Tools**:
- MCP: filesystem

**Done when**:
- [ ] `search_plesk_unified` calls `ctx.report_progress(1, 3)` after embedding, `(2, 3)` after reranking, `(3, 3)` after formatting
- [ ] `trigger_index_sync` / background thread calls `ctx.report_progress(files_done, total_files)` after each batch
- [ ] When `ctx` is `None` (backward compat), progress calls are silently skipped
- [ ] `python -m pytest tests/` passes

**Verify**:
```bash
python -c "
from unittest.mock import MagicMock, AsyncMock
import asyncio
from plesk_unified.server import search_plesk_unified

ctx = MagicMock()
ctx.report_progress = AsyncMock()
asyncio.run(search_plesk_unified('test', ctx=ctx))
assert ctx.report_progress.call_count >= 2
print('OK, calls:', ctx.report_progress.call_count)
"
```

---

### T12: Implement LLM sampling for payload minification [P]

**What**: After reranking in `search_plesk_unified`, when `PLESK_ENABLE_SAMPLING=true` and `ctx` is available, call `ctx.sample()` to summarize the top-5 results before returning.

**Where**: `plesk_unified/server.py` (modify)

**Depends on**: T06 (async `search_plesk_unified`), T01 (`settings.plesk_enable_sampling`)

**Reuses**: `get_settings()` for the feature flag; FastMCP `Context.sample()` API

**Tools**:
- MCP: filesystem

**Done when**:
- [ ] When `settings.plesk_enable_sampling is True` AND `ctx` is available: calls `await ctx.sample(prompt=summary_prompt, max_tokens=500)` with a 5-second timeout
- [ ] When sampling times out or fails: falls back to full text return silently
- [ ] When `settings.plesk_enable_sampling is False`: existing behavior unchanged
- [ ] `python -m pytest tests/` passes

**Verify**:
```bash
python -c "
import os, asyncio
os.environ['PLESK_ENABLE_SAMPLING'] = 'true'
from unittest.mock import MagicMock, AsyncMock
from plesk_unified.server import search_plesk_unified

ctx = MagicMock()
ctx.sample = AsyncMock(return_value=MagicMock(content='SUMMARY'))
result = asyncio.run(search_plesk_unified('test', ctx=ctx))
# When DB empty, sampling not reached, so just verify no crash
print('OK')
"
```

---

### T13: Integration test — async concurrency validation

**What**: Add a pytest test that fires `search_plesk_unified` and `daemon_health` concurrently and asserts both return without timeout.

**Where**: `tests/test_async_concurrency.py` (new file)

**Depends on**: T06, T08 (async refactor complete)

**Reuses**: Existing `pytest` and `asyncio` test patterns in `tests/`

**Tools**:
- MCP: filesystem

**Done when**:
- [ ] `test_concurrent_search_and_health` uses `asyncio.gather` with two tasks
- [ ] Both tasks complete within 5 s in the test environment (mocked DB)
- [ ] `python -m pytest tests/test_async_concurrency.py -v` passes

**Verify**:
```bash
python -m pytest tests/test_async_concurrency.py -v
```

---

### T14: Add vector search telemetry to `search_plesk_unified` [P]

**What**: After each `search_plesk_unified` call, log a structured telemetry line to the native OS logger with: query latency (ms), result count, top-1 relevance score, and approximate RSS memory delta.

**Where**: `plesk_unified/server.py` (modify)

**Depends on**: T06 (async search)

**Reuses**: `logger` from `log_handler.py`; `time.perf_counter()` pattern already in `server.py`

**Tools**:
- MCP: filesystem

**Done when**:
- [ ] `logger.info("TELEMETRY query_latency_ms=%.1f result_count=%d top1_score=%.4f", ...)` emitted after every search
- [ ] Memory delta measured via `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` (Unix) or `psutil.Process().memory_info().rss` with graceful fallback if unavailable
- [ ] Log line is key=value formatted for easy grep / Grafana ingestion
- [ ] `python -m pytest tests/` passes

**Verify**:
```bash
python -c "
import logging, io
buf = io.StringIO()
h = logging.StreamHandler(buf)
logging.getLogger('plesk_unified').addHandler(h)
# run a search (will fail without DB, but telemetry logs before error)
# Just check the pattern is registered
print('OK')
"
```

---

### T15: Refactor `search_plesk_unified` return to Rich Markdown cards [P]

**What**: Replace the plain text `"\n".join(formatted_results)` return with FastMCP-formatted Markdown cards. Each card includes category badge, title as heading, breadcrumb path, relevance score indicator, and filename.

**Where**: `plesk_unified/server.py` (modify — `formatted_results` block at line 779–801)

**Depends on**: T06 (async search), T03 (CategoryEnum for badge labeling)

**Reuses**: Existing `r['category']`, `r['title']`, `r['breadcrumb']`, `r['filename']`, score fields

**Tools**:
- MCP: filesystem

**Done when**:
- [ ] Each result card formatted as:
  ```
  ## [{CATEGORY}] {title}
  **Path**: {breadcrumb}
  **File**: `{filename}`
  **Relevance**: {score_bar} {score:.4f}
  ---
  {text}
  ```
  where `score_bar` is `🟢` (≥0.8), `🟡` (0.5–0.8), `🔴` (<0.5)
- [ ] Return type is still `str` (Markdown string)
- [ ] Existing tests that check for `category.upper()` in output updated to match new format
- [ ] `python -m pytest tests/` passes

**Verify**:
```bash
# Visual inspection: result cards should contain ## heading and emoji bar
```

---

### T16: Implement Dynamic VRAM Auto-Tuning in `model_config.py` [P]

**What**: Extend `get_active_profile()` to query `torch.cuda.mem_get_info()` when CUDA is available and auto-select `tq_bits=3` (< 4 GB) or float16 (≥ 8 GB), unless `PLESK_MODEL_PROFILE` is explicitly set.

**Where**: `plesk_unified/model_config.py` (modify)

**Depends on**: T01 (`PleskSettings` — checks if profile is explicitly set)

**Reuses**: `get_optimal_device()` from `platform_utils.py`; existing `_PROFILES` dict

**Tools**:
- MCP: filesystem

**Done when**:
- [ ] When `PLESK_MODEL_PROFILE` is not explicitly set AND `device == "cuda"`: queries `torch.cuda.mem_get_info()`
- [ ] Free VRAM < 4 GB → sets `tq_bits=3` and logs `"Auto-tuned: tq_bits=3 (free VRAM < 4GB)"`
- [ ] Free VRAM ≥ 8 GB → sets `use_turboquant=False` (dense) and logs `"Auto-tuned: dense float16 (free VRAM >= 8GB)"`
- [ ] When `PLESK_MODEL_PROFILE` IS explicitly set → auto-tuning skipped, logs `"Auto-tune skipped: explicit profile set"`
- [ ] On CPU/MPS → auto-tuning silently skipped
- [ ] `python -m pytest tests/test_model_config.py -v` passes

**Verify**:
```bash
python -m pytest tests/test_model_config.py -v
```

---

### T17: Create `Dockerfile` with multi-stage build [P]

**What**: Write a multi-stage Dockerfile: `builder` stage installs all PyPI dependencies via `pip install -e ".[dev]"`; `final` stage copies venv from builder. Non-root `plesk` user. `VOLUME` for storage and knowledge base. `ARG CUDA_VARIANT`.

**Where**: `Dockerfile` (new file, repo root)

**Depends on**: None (independent of all Python changes)

**Reuses**: `pyproject.toml` dependency spec

**Tools**:
- MCP: filesystem

**Done when**:
- [ ] `docker build -t plesk-unified .` completes without error (CPU build)
- [ ] `docker inspect plesk-unified` shows `User: plesk`
- [ ] `docker inspect plesk-unified` shows `Volumes: {"/app/storage":{}, "/app/knowledge_base":{}}`
- [ ] `docker run --rm plesk-unified python -c "from plesk_unified.server import mcp; print('ok')"` prints `ok`
- [ ] `ARG CUDA_VARIANT` documented in Dockerfile comments with usage instructions

**Verify**:
```bash
docker build -t plesk-unified-test . && \
docker run --rm plesk-unified-test python -c "from plesk_unified.server import mcp; print('ok')"
```

---

### T18: Implement `list_roots` and path traversal guard [P]

**What**: Register a `list_roots` MCP handler returning the two approved base directories. Add a `_validate_path(path, roots)` utility that raises `PermissionError` on traversal. Apply to `trigger_index_sync` / `refresh_knowledge`.

**Where**: `plesk_unified/server.py` (modify); `plesk_unified/error_handling.py` (modify — add `_validate_path`)

**Depends on**: T04 (error boundary catches `PermissionError`), T07 (indexing tools)

**Reuses**: `KB_DIR`, `BASE_DIR` constants from `server.py`; `@tool_error_boundary` from T04

**Tools**:
- MCP: filesystem

**Done when**:
- [ ] `list_roots` returns `[{"uri": f"file://{KB_DIR}"}, {"uri": f"file://{BASE_DIR / 'storage'}"}]`
- [ ] `_validate_path(path, roots)` resolves the path and raises `PermissionError` if it doesn't start with any root
- [ ] Called at entry of `trigger_index_sync` for source paths derived from `target_category`
- [ ] Passing `target_category="../../etc"` as raw string (bypassing enum for unit test) returns `[ERROR] Path traversal detected`
- [ ] Valid enum values always pass the check
- [ ] `python -m pytest tests/` passes

**Verify**:
```bash
python -c "
from plesk_unified.error_handling import _validate_path
from pathlib import Path
roots = [Path('/app/knowledge_base'), Path('/app/storage')]
try:
    _validate_path(Path('/app/knowledge_base/../../../etc/passwd'), roots)
    print('FAIL: should have raised')
except PermissionError:
    print('OK: traversal correctly blocked')
"
```

---

### T19: Create `.github/workflows/docs-drift.yml` [P]

**What**: GitHub Actions workflow that runs on `schedule: cron '0 3 * * 1'` and `workflow_dispatch`. Runs `manage_plesk_docs.py` and `enrich_toc.py`. If any `knowledge_base/` file changes, commits and pushes to a `docs-sync` branch.

**Where**: `.github/workflows/docs-drift.yml` (new file)

**Depends on**: None (independent of all Python changes)

**Reuses**: Existing `scripts/manage_plesk_docs.py` and `scripts/enrich_toc.py`

**Tools**:
- MCP: filesystem
- Skill: coding-guidelines

**Done when**:
- [ ] Workflow defined with `on: schedule` (Monday 03:00 UTC) and `on: workflow_dispatch`
- [ ] Workflow installs Python deps, runs `manage_plesk_docs.py`, runs `enrich_toc.py`
- [ ] Uses `git diff --quiet knowledge_base/` to detect changes
- [ ] When changes detected: `git checkout -b docs-sync`, commits, pushes
- [ ] When no changes: workflow completes with no commit
- [ ] YAML syntax valid: `yamllint .github/workflows/docs-drift.yml` passes

**Verify**:
```bash
yamllint .github/workflows/docs-drift.yml
# Then trigger manually via GitHub Actions UI: workflow_dispatch
```

---

### T20: Create `.github/workflows/benchmark-regression.yml` [P]

**What**: GitHub Actions workflow triggered on `pull_request`. Runs `benchmark_profiles.py`. Parses HR@5 and MRR@5 from output. Posts a PR comment with the delta vs `main`. Fails the check if regression > 5%.

**Where**: `.github/workflows/benchmark-regression.yml` (new file)

**Depends on**: None (independent of Python changes)

**Reuses**: Existing `scripts/benchmark_profiles.py` and `benchmark_output.txt` format

**Tools**:
- MCP: filesystem

**Done when**:
- [ ] Workflow triggers on `pull_request` targeting `main`
- [ ] Runs `benchmark_profiles.py` on both `main` and the PR branch (or compares to committed baseline)
- [ ] Parses `HR@5` and `MRR@5` from `benchmark_output.txt`
- [ ] Posts PR comment via `actions/github-script` with the delta table
- [ ] If HR@5 regression > 5% OR MRR@5 regression > 5%: step exits non-zero (fails check)
- [ ] YAML syntax valid: `yamllint .github/workflows/benchmark-regression.yml` passes

**Verify**:
```bash
yamllint .github/workflows/benchmark-regression.yml
```

---

### T21: Final validation — full test suite + ruff + schema assertions

**What**: Run the full test suite, ruff linter, and a schema assertion script to confirm all acceptance criteria are met before marking the feature as done.

**Where**: All files (validation only, no new code)

**Depends on**: T01–T20 all complete

**Tools**:
- MCP: filesystem (run commands)

**Done when**:
- [ ] `python -m pytest tests/ -v` passes with no regressions
- [ ] `ruff check plesk_unified/` reports zero new violations
- [ ] FastMCP schema introspection shows `enum` on `search_plesk_unified.category` and `refresh_knowledge.target_category`
- [ ] `docker build -t plesk-unified .` succeeds (if Docker available in CI)
- [ ] `yamllint .github/workflows/docs-drift.yml .github/workflows/benchmark-regression.yml` passes
- [ ] HR@5 and MRR@5 in `benchmark_output.txt` within 5% of baseline

**Verify**:
```bash
python -m pytest tests/ -v && ruff check plesk_unified/ && echo "ALL CHECKS PASSED"
```

---

## Parallel Execution Map

```
Phase 1 (Sequential — M1 Foundation):
  T01 → T02 → T03 → T04

Phase 2 (Parallel — M2 Async Core):
  T04 complete, then:
    ├── T05 [P]   (indexing.py / JobRegistry)
    ├── T06 [P]   (async tool handlers)
    └── T07 waits for T05 + T06

  T07 → T08 (CDI lifespan — sequential after T06)

Phase 3 (Parallel — M3 Protocol Richness):
  T08 complete, then:
    ├── T09 [P]   (TOC resource)
    ├── T10 [P]   (prompt templates)
    ├── T11 [P]   (progress notifications)
    └── T12 [P]   (LLM sampling)
  
  All four → T13 (integration concurrency test)

Phase 4 (Parallel — M4 Observability):
  T06 complete, then:
    ├── T14 [P]   (search telemetry)
    ├── T15 [P]   (rich markdown cards)
    └── T16 [P]   (VRAM auto-tune)

Phase 5 (Parallel — M5 Security & Infra):
  Can start after M1 complete:
    ├── T17 [P]   (Dockerfile)
    ├── T18 [P]   (Roots + path guard — needs T04, T07)
    ├── T19 [P]   (docs-drift workflow)
    └── T20 [P]   (benchmark workflow)

  All complete → T21 (final validation)
```

---

## Task Granularity Check

| Task | Scope | Status |
|------|-------|--------|
| T01: PleskSettings class | 1 new file | ✅ Granular |
| T02: Wire settings into server + model_config | 2 file modifications, 12 replacements | ✅ Granular |
| T03: CategoryEnum + update 2 signatures | 1 new file + 2 signature edits | ✅ Granular |
| T04: tool_error_boundary decorator | 1 new file + 5 decorator applications | ✅ Granular |
| T05: JobRegistry + extract functions | 1 new file + 1 file modification | ✅ Granular |
| T06: Async tool conversion | 1 file, 5 function signatures + executor | ✅ Granular |
| T07: New MCP tools trigger/check | 1 file, 2 new tool registrations | ✅ Granular |
| T08: Context lifespan DI | 1 file, refactor globals to lifespan | ✅ Granular |
| T09: TOC resource | 1 new file + import in server.py | ✅ Granular |
| T10: Prompt templates | 1 new file + import in server.py | ✅ Granular |
| T11: Progress notifications | 2 file modifications, 5 progress calls | ✅ Granular |
| T12: LLM sampling | 1 file modification, 1 conditional block | ✅ Granular |
| T13: Concurrency integration test | 1 new test file | ✅ Granular |
| T14: Search telemetry | 1 file, 1 log statement | ✅ Granular |
| T15: Rich markdown cards | 1 file, replace formatting block | ✅ Granular |
| T16: VRAM auto-tune | 1 file, 1 new branch in get_active_profile | ✅ Granular |
| T17: Dockerfile | 1 new file | ✅ Granular |
| T18: Roots + path guard | 2 file modifications | ✅ Granular |
| T19: docs-drift.yml | 1 new YAML file | ✅ Granular |
| T20: benchmark-regression.yml | 1 new YAML file | ✅ Granular |
| T21: Final validation | No code changes | ✅ Granular |
