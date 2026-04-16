# Enterprise AI Infrastructure Uplift — Design

**Spec**: `.specs/features/enterprise-ai-infrastructure/spec.md`
**Status**: Draft

---

## Architecture Overview

The uplift is organized as five additive layers applied to the existing codebase. No existing public interfaces are removed; each layer is independently deployable as a milestone.

```mermaid
graph TD
    subgraph M1["M1 · Foundation"]
        PS[PleskSettings<br/>pydantic-settings] --> SRV[server.py]
        CE[CategoryEnum<br/>types.py] --> SRV
        EB[tool_error_boundary<br/>decorator] --> SRV
        HDT[HW Degradation<br/>Telemetry] --> PU[platform_utils.py]
    end

    subgraph M2["M2 · Async Core"]
        AEL[async def tools<br/>run_in_executor] --> SRV
        JR[JobRegistry<br/>indexing.py] --> SRV
        CDI[Context DI<br/>lifespan state] --> SRV
    end

    subgraph M3["M3 · Protocol Richness"]
        TOC[plesk://toc/{cat}<br/>@mcp.resource] --> SRV
        PT[@mcp.prompt<br/>templates] --> SRV
        PN[ctx.report_progress<br/>notifications] --> SRV
        SAM[ctx.sample<br/>sampling] --> SRV
    end

    subgraph M4["M4 · Observability"]
        VST[Vector Search<br/>Telemetry] --> SRV
        RMD[Rich Markdown<br/>Cards] --> SRV
        VRAM[VRAM Auto-Tune] --> MC[model_config.py]
    end

    subgraph M5["M5 · Infra & Security"]
        DOCK[Dockerfile] --> CI[GitHub Actions]
        ROOTS[list_roots<br/>path validation] --> SRV
        DRIFT[docs-drift.yml] --> CI
        BENCH[benchmark-regression.yml] --> CI
    end

    SRV --> LANCE[LanceDB]
    SRV --> TQ[TurboQuantIndex]
    SRV --> LOG[log_handler.py]
```

---

## Code Reuse Analysis

### Existing Components to Leverage

| Component | Location | How to Use |
|-----------|----------|------------|
| `create_os_handlers` | `plesk_unified/log_handler.py` | Error boundary decorator reuses this for guaranteed traceback logging |
| `get_active_profile` | `plesk_unified/model_config.py` | `PleskSettings` wraps the same env var names; `get_active_profile()` updated to call `PleskSettings()` |
| `_background_warmup_worker` pattern | `plesk_unified/server.py:431` | Background indexing job pattern mirrors this daemon thread approach exactly |
| `_warmup_state` / `_warmup_lock` pattern | `plesk_unified/server.py:151-153` | `JobRegistry` reuses the same `threading.Lock` + state machine pattern |
| `io_utils.load_toc_map` | `plesk_unified/io_utils.py` | TOC Resource directly calls this existing loader |
| `generate_virtual_toc.py` | `scripts/generate_virtual_toc.py` | TOC Resource falls back to this script's logic when `toc.json` absent |
| `process_source_files` | `plesk_unified/server.py:605` | Background indexing job calls this unchanged; only the dispatch mechanism changes |
| `benchmark_profiles.py` | `scripts/benchmark_profiles.py` | CI benchmark workflow invokes this existing script directly |
| `manage_plesk_docs.py` + `enrich_toc.py` | `scripts/` | Drift detection workflow invokes these existing scripts directly |

### Integration Points

| System | Integration Method |
|--------|-------------------|
| FastMCP Context | Injected via `@mcp.tool` async function signature: `async def tool(ctx: Context)` |
| FastMCP Resource | `@mcp.resource("plesk://toc/{category}")` decorator on new `toc_resource.py` |
| FastMCP Prompt | `@mcp.prompt("plesk-extension-dev-guide")` decorator on new `prompts.py` |
| LanceDB | No change to schema; async wrapper via `run_in_executor` |
| pydantic-settings | `PleskSettings` in new `plesk_unified/settings.py`; imported at top of `server.py` and `model_config.py` |
| GitHub Actions | Two new `.github/workflows/` YAML files; no changes to Python code |

---

## Components

### `PleskSettings` (new)

- **Purpose**: Single source of truth for all environment variable configuration with type validation
- **Location**: `plesk_unified/settings.py`
- **Interfaces**:
  - `PleskSettings()` — reads from env + `.env` file, raises `ValidationError` on bad values
  - `get_settings() -> PleskSettings` — cached singleton getter
- **Dependencies**: `pydantic-settings >= 2.0`, `python-dotenv`
- **Reuses**: `load_dotenv()` call already in `server.py`; replaces the 12 raw `os.environ.get()` calls in `server.py` and `model_config.py`

**Fields:**

```python
class PleskSettings(BaseSettings):
    log_level: Literal["DEBUG","INFO","WARNING","ERROR","CRITICAL"] = "INFO"
    log_file: str = "storage/logs/plesk_unified.log"
    log_handler: Literal["os","file","both"] = "os"
    plesk_model_profile: Literal["light","medium","full","full-tq"] = "full-tq"
    plesk_embed_model: str = ""
    plesk_reranker_model: str = ""
    plesk_reranker_enabled: str = ""   # tri-state: "true"/"false"/""
    plesk_embed_dim: int = 0           # 0 = use profile default
    force_device: Literal["cuda","mps","cpu",""] = ""
    plesk_daemon_auto_warmup: bool = False
    openrouter_api_key: str = ""
    plesk_enable_sampling: bool = False
```

---

### `CategoryEnum` (new)

- **Purpose**: Strict enumeration of valid documentation categories for tool parameter validation
- **Location**: `plesk_unified/types.py`
- **Interfaces**:
  - `CategoryEnum` — `str, Enum` with members `GUIDE`, `CLI`, `API`, `PHP_STUBS`, `JS_SDK`
  - `CategoryOrAll` — `Union[CategoryEnum, Literal["all"]]` for `refresh_knowledge`
- **Dependencies**: stdlib `enum`
- **Reuses**: Nothing; purely additive

---

### `tool_error_boundary` decorator (new)

- **Purpose**: Wraps any `@mcp.tool` function, catches all exceptions, logs to OS logger, returns sanitized retry guidance
- **Location**: `plesk_unified/error_handling.py`
- **Interfaces**:
  - `@tool_error_boundary` — decorator applicable to both `def` and `async def` functions
  - `_classify_error(exc) -> str` — internal function that maps known exception types to guidance strings
- **Dependencies**: `log_handler.py` (existing), `logging`
- **Reuses**: `create_os_handlers` indirectly via the module-level `logger`

**Error classification map:**

| Exception type | Returned guidance |
|---------------|-------------------|
| LanceDB `TableNotFoundError` | `"[ERROR] Knowledge base not indexed. Call refresh_knowledge(reset_db=True) first."` |
| LanceDB connection error | `"[ERROR] Database unavailable. Check storage/lancedb/ path. Call daemon_health for details."` |
| `RuntimeError` containing "model" | `"[ERROR] Embedding model not loaded. Call warmup_server first."` |
| `PermissionError` | `"[ERROR] Path traversal detected. Operation rejected."` |
| Any other | `"[ERROR] Unexpected server error. Call daemon_health to check server state, then retry."` |

---

### `JobRegistry` (new)

- **Purpose**: Thread-safe in-memory store for background indexing job state
- **Location**: `plesk_unified/indexing.py`
- **Interfaces**:
  - `submit_job(target_category, reset_db) -> str` — starts background thread, returns `job_id`
  - `get_job_status(job_id) -> JobStatus` — returns current state
  - `JobStatus` dataclass: `job_id, status, progress, current_source, files_processed, report, error`
- **Dependencies**: `threading`, `uuid`, existing `process_source_files` (moved here from `server.py`)
- **Reuses**: `_background_warmup_worker` pattern from `server.py`

---

### Async tool refactor (modify existing)

- **Purpose**: Convert all `@mcp.tool` handlers to `async def` with ML calls offloaded to thread pool
- **Location**: `plesk_unified/server.py` (modify)
- **Interfaces**: Unchanged public signatures; `async def` prefix added
- **Dependencies**: `asyncio`, `concurrent.futures.ThreadPoolExecutor`
- **Reuses**: All existing logic; only dispatch mechanism changes

**Pattern:**

```python
async def search_plesk_unified(query: str, category: CategoryEnum | None = None, ctx: Context = None) -> str:
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(_executor, _sync_search, query, category)
    ...
```

---

### `toc_resource` (new)

- **Purpose**: Expose TOC hierarchy for each category as an MCP Resource
- **Location**: `plesk_unified/toc_resource.py`
- **Interfaces**:
  - `@mcp.resource("plesk://toc/{category}")` async function
  - `_load_toc(category: CategoryEnum) -> dict` — internal loader
- **Dependencies**: `io_utils.load_toc_map` (existing), `generate_virtual_toc` script logic
- **Reuses**: `SOURCES` dict from `server.py` for path resolution; `io_utils.load_toc_map` directly

---

### `prompts` (new)

- **Purpose**: Pre-built prompt templates for common Plesk development workflows
- **Location**: `plesk_unified/prompts.py`
- **Interfaces**:
  - `@mcp.prompt("plesk-extension-dev-guide")` — returns message list with Extensions Guide context
  - `@mcp.prompt("plesk-api-integration")` — returns API RPC context
  - `@mcp.prompt("plesk-cli-reference")` — returns CLI Linux context
- **Dependencies**: `search_plesk_unified` (called internally to seed context)
- **Reuses**: Existing search infrastructure for the seed results

---

### `Dockerfile` (new)

- **Purpose**: Zero-trust multi-stage container image
- **Location**: `Dockerfile` (repo root)
- **Interfaces**:
  - `ARG CUDA_VARIANT` — empty (CPU) or `cu124` for CUDA PyTorch
  - `VOLUME ["/app/storage", "/app/knowledge_base"]`
  - `USER plesk` (UID 1000)
- **Dependencies**: `python:3.12-slim` base
- **Reuses**: `pyproject.toml` dependency spec directly

---

### GitHub Actions Workflows (new)

- **Purpose**: Automate drift detection and benchmark regression gating
- **Location**: `.github/workflows/docs-drift.yml`, `.github/workflows/benchmark-regression.yml`
- **Interfaces**:
  - `docs-drift.yml`: `schedule: cron '0 3 * * 1'` + `workflow_dispatch`
  - `benchmark-regression.yml`: `pull_request` trigger
- **Dependencies**: Existing `scripts/manage_plesk_docs.py`, `scripts/enrich_toc.py`, `scripts/benchmark_profiles.py`
- **Reuses**: Existing scripts unchanged

---

## Data Models

### `JobStatus`

```python
@dataclass
class JobStatus:
    job_id: str
    status: Literal["queued", "running", "done", "failed"]
    progress: int           # 0–100
    current_source: str     # category being processed
    files_processed: int
    total_files: int
    report: str             # final per-source report (populated when done)
    error: str              # sanitized error message (populated when failed)
    created_at: float       # time.time()
    updated_at: float
```

---

## Error Handling Strategy

| Error Scenario | Handling | User Impact |
|----------------|----------|-------------|
| `ValidationError` on startup | Raise immediately; `sys.exit(1)` | Clear error message listing valid values |
| Tool raises unhandled exception | `tool_error_boundary` catches; logs traceback; returns `[ERROR]` string | LLM receives retry guidance |
| Background job thread crash | `JobRegistry` marks job `failed`; stores sanitized error | `check_sync_status` returns `{"status": "failed"}` |
| `ctx.sample()` timeout | 5 s timeout; fall back to full text | No change visible to user |
| `plesk://toc/<invalid>` | Return MCP `ResourceError` | LLM receives 404-equivalent |
| Path traversal in file arg | `PermissionError`; caught by boundary | `[ERROR] Path traversal detected` returned |
| CUDA/MPS silent fallback | `WARNING` log emitted | No user-visible change; operator sees log |

---

## Tech Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Settings library | `pydantic-settings` | Already a transitive dependency via `pydantic`; zero new deps |
| Async ML dispatch | `run_in_executor` | sentence-transformers is not async-native; thread pool is the correct pattern |
| Job storage | In-memory dict | Jobs are ephemeral (survive only for the server session); persistence not required |
| Container base | `python:3.12-slim` (not distroless) | Distroless lacks pip for multi-stage; slim is the practical minimum |
| Enum strategy | `str, Enum` | FastMCP serializes `str`-based enums to JSON Schema `enum` correctly |
| Sampling gate | `PLESK_ENABLE_SAMPLING` env var | Not all host clients support sampling; opt-in prevents regression |
