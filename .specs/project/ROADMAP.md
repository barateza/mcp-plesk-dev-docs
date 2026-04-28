# Roadmap — Enterprise AI Infrastructure Uplift

**Current Milestone:** M7 — SOTA Retrieval Roadmap (Phase 1)
**Status:** Planning

---

## M1 — Foundation & Protocol Contracts

**Goal:** Harden the server's configuration surface, error handling, and tool schema contracts so that every subsequent milestone builds on a deterministic, type-safe base. All changes are additive with zero breaking changes.

**Target:** Completable in a single implementation session; no ML model loading required.

### Features

**Pydantic Settings Validation** — PLANNED

- Replace raw `os.environ.get()` calls in `server.py` and `model_config.py` with a `pydantic_settings.BaseSettings` subclass (`PleskSettings`)
- Validate `LOG_LEVEL`, `LOG_FILE`, `LOG_HANDLER`, `PLESK_MODEL_PROFILE`, `PLESK_EMBED_MODEL`, `PLESK_RERANKER_MODEL`, `PLESK_RERANKER_ENABLED`, `PLESK_EMBED_DIM`, `FORCE_DEVICE`, `PLESK_DAEMON_AUTO_WARMUP`, `OPENROUTER_API_KEY` at startup
- Raise a descriptive `ValidationError` on bad values before any heavy import

**Strict Enum Category Parameters** — PLANNED

- Define `CategoryEnum(str, Enum)` with values `guide`, `cli`, `api`, `php-stubs`, `js-sdk`
- Apply to `search_plesk_unified(category)` and `refresh_knowledge(target_category)` so FastMCP generates a strict JSON Schema enum
- `target_category` additionally accepts `"all"` via a separate union type

**Sanitized Error Boundary** — PLANNED

- Implement `@tool_error_boundary` decorator
- Catches all unhandled exceptions, logs full traceback via `log_handler.py`, and returns a deterministic retry-guidance string to the LLM
- Applied to `refresh_knowledge`, `search_plesk_unified`, `warmup_server`, `daemon_health`

**Hardware Degradation Telemetry** — PLANNED

- Extend `platform_utils.get_optimal_device()` to emit a `WARNING` log when MPS or CUDA was requested/expected but the system silently fell back to CPU
- Include the original exception reason in the warning message

---

## M2 — Async Core & Tool Decomposition

**Goal:** Convert all blocking tool handlers to `async def`, introduce a job-based polling model for long-running indexing, and decompose `refresh_knowledge` into atomic operations. This makes the server safe for concurrent MCP client requests.

**Target:** Requires asyncio-compatible LanceDB usage; core ML path remains synchronous in thread pool.

### Features

**Async Event Loop Refactor** — PLANNED

- Convert `search_plesk_unified`, `refresh_knowledge`, `warmup_server`, `daemon_health`, `list_model_profiles` to `async def`
- Wrap CPU-bound ML calls (`get_embedding_model()`, reranker, TurboQuant) in `asyncio.get_event_loop().run_in_executor()` to avoid blocking the event loop
- Validate that `daemon_health` polling continues to work during concurrent vector search

**Background Polling Architecture** — PLANNED

- Add in-memory `_job_registry: dict[str, JobStatus]` dataclass store
- `trigger_index_sync(target_category, reset_db)` starts indexing in a background thread, returns `{"job_id": "<uuid>", "status": "queued"}`
- `check_sync_status(job_id)` returns progress percentage, current source, and final report when done
- Deprecate (but preserve) existing `refresh_knowledge` behavior via adapter

**Decoupled Indexing Tools** — PLANNED

- Expose `trigger_index_sync` and `check_sync_status` as distinct `@mcp.tool` endpoints with proper descriptions
- `refresh_knowledge` becomes a thin wrapper calling `trigger_index_sync` + blocking wait, preserving backward compatibility

**Context Dependency Injection** — PLANNED

- Refactor `get_embedding_model()`, `get_tq_index()`, `get_table()` to be retrieved from FastMCP `Context` lifespan state rather than module-level globals
- Eliminates global state mutation; enables safer parallel request handling

---

## M3 — Protocol Richness: Resources, Prompts & Notifications

**Goal:** Implement the three MCP protocol primitives currently absent: Resources, Prompts, and Progress Notifications. This lifts the server from tool-only to protocol-complete.

**Target:** Requires FastMCP resource/prompt decorator support (≥ 3.2.0 ✓).

### Features

**TOC as MCP Resource** — PLANNED

- Expose `@mcp.resource("plesk://toc/{category}")` returning the Table of Contents hierarchy for any of the 5 categories as structured JSON
- Allows LLMs to passively read documentation architecture without invoking a search tool
- Falls back to `generate_virtual_toc.py` output when `toc.json` is absent

**Standardized Prompt Templates** — PLANNED

- Implement `@mcp.prompt("plesk-extension-dev-guide")` — scaffolds the context for new extension development
- Implement `@mcp.prompt("plesk-api-integration")` — pre-loads API RPC context
- Implement `@mcp.prompt("plesk-cli-reference")` — pre-loads CLI Linux context

**JSON-RPC Progress Notifications** — PLANNED

- Inject `Context` into `refresh_knowledge` (and `trigger_index_sync`) and call `ctx.report_progress(current, total)` per file batch
- Inject `Context` into `search_plesk_unified` and emit progress during embedding + reranking phases
- Allows MCP host clients (Claude Desktop, etc.) to render a native progress indicator

**LLM Sampling for Payload Minification** — PLANNED

- After reranking, use FastMCP `ctx.sample()` to request the LLM client to summarize the top-5 documents
- Return the sampling-compressed payload instead of the full raw text when `PLESK_ENABLE_SAMPLING=true`
- Fallback to full text return when sampling is unavailable

---

## M4 — Observability & Rich UI Output

**Goal:** Improve both the developer-facing observability story and the end-user result presentation.

### Features

**Vector Search Telemetry** — PLANNED

- Log query latency (ms), result count, top-1 relevance score, and approximate memory delta to the native OS log on every `search_plesk_unified` call
- Structured as key=value pairs for easy ingestion by Grafana / Splunk

**Rich Markdown Result Cards** — PLANNED

- Refactor `search_plesk_unified` to return FastMCP-formatted Markdown blocks
- Each result card includes: category badge, title as heading, breadcrumb path, relevance score bar (emoji-based), and filename with source link anchor
- Raw text body preserved but collapsible

**Interactive Folder UI for TOC Resource** — PLANNED

- The `plesk://toc/{category}` resource returns a navigable Markdown tree using nested list formatting
- Leaf nodes include the file reference anchor for direct lookup

**Dynamic VRAM Auto-Tuning** — PLANNED

- Query `torch.cuda.mem_get_info()` at initialization; if free VRAM < 4 GB downgrade to `tq_bits=3`; if free VRAM ≥ 8 GB upgrade to float16 dense mode
- Log the auto-selected quantization level with the VRAM reason

---

## M5 — Security, Containerization & CI/CD

**Goal:** Complete the operational maturity story: zero-trust container distribution, path traversal prevention via protocol Roots, automated documentation drift detection, and benchmark regression gating.

### Features

**Zero-Trust Dockerfile** — PLANNED

- Distroless Python base image (`gcr.io/distroless/python3`)
- Multi-stage build: builder installs all PyPI deps; final stage copies only the venv
- `ARG CUDA_VARIANT` toggles CUDA vs CPU PyTorch index
- `VOLUME ["/app/storage", "/app/knowledge_base"]` isolates mutable data
- Non-root user `plesk` with UID 1000

**Cryptographic Roots Constraints** — PLANNED

- Implement `list_roots` returning `[{uri: "file:///app/knowledge_base"}, {uri: "file:///app/storage"}]`
- Validate all file path arguments in `refresh_knowledge` / `trigger_index_sync` against these roots before any filesystem operation
- Reject with `PermissionError` (caught by error boundary) if path traversal detected

**CI/CD Drift Detection Workflow** — PLANNED

- GitHub Actions workflow `docs-drift.yml` on `schedule: cron: '0 3 * * 1'` (Monday 03:00 UTC)
- Runs `manage_plesk_docs.py` and `enrich_toc.py`; if any file changes detected, commits the updated KB and opens a PR or pushes to a `docs-sync` branch
- Sends a summary notification via workflow annotation

**Automated Benchmark Regression** — COMPLETED

- GitHub Actions workflow `benchmark-regression.yml` on `pull_request`
- Runs `benchmark_profiles.py` against the PR branch
- Parses HR@5 and MRR@5 from `benchmark_output.txt`; if either regresses > 5% vs `main`, posts a PR comment with the delta table and marks the check as failed

---

## M6 — Retrieval Quality Optimization

**Goal:** Improve retrieval precision and recall through hybrid search, structural context injection, and specialized chunking strategies.
**Status:** COMPLETED

### Features

**Hybrid Search (Vector + BM25)** — COMPLETED
- Integrate Full-Text Search (FTS) using LanceDB.
- Combine vector similarity with keyword matching using Reciprocal Rank Fusion (RRF).

**Parent-Header Context Injection** — COMPLETED
- Prepend document title and breadcrumb path to every chunk before embedding.

**Neighborhood Retrieval** — COMPLETED
- Automatically retrieve adjacent chunks (prev/next) for the top results to provide richer context.

**API Endpoint Extraction** — COMPLETED
- Specialized parser to detect and index REST API endpoints for exact path matching.

**Hierarchical Code Chunking** — COMPLETED
- Implement structural chunkers for PHP and JS that respect class and method boundaries.

---

## M7 — SOTA Retrieval Roadmap (Phase 1 and Phase 2)

**Goal:** Deliver Phase 1 retrieval upgrades and document Phase 2 SOTA work
without expanding default dependencies.

### Phase 1 features

- Re-enable FTS candidates with RRF hybrid merging.
- Add AST-based chunking for PHP and JS with fallbacks.
- Add MCP tools: get_file_content and resolve_references.
- Require inline citations for synthesized answers and enable streaming when
  supported.

### Phase 2 features (documented, deferred)

- Late interaction retrieval fused with vector and FTS results.
- Query rewriting and HyDE pre-retrieval synthesis.
- GraphRAG relation extraction and traversal fusion.
- Semantic HTML chunking based on embedding similarity.
- VLM-based diagram and image captioning.

---

## Future Considerations

- Multi-tenant session isolation with per-user LanceDB namespaces
- Streaming search results via MCP `stream` transport
- Federated indexing across multiple Plesk versions simultaneously
- WebAssembly-compiled TurboQuant for edge deployment
