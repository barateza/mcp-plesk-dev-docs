# Enterprise AI Infrastructure Uplift — Specification

## Problem Statement

`mcp-plesk-unified` is a functional RAG-over-documentation MCP server, but it falls short of enterprise production standards across three dimensions: **protocol completeness** (no Resources, Prompts, Sampling, Roots, or progress notifications), **operational maturity** (synchronous blocking tools, no container distribution, no CI/CD automation), and **contract strictness** (raw `os.environ.get()` calls, untyped string category parameters, opaque error messages that cause LLM hallucinations). The 10-pillar high-level plan identifies 20 concrete features to close these gaps.

## Goals

- [ ] Full MCP protocol surface: Resources, Prompts, Sampling, Roots, and progress notifications all implemented
- [ ] All tool handlers converted to `async def` with zero blocking event-loop operations
- [ ] Configuration validated at startup via `pydantic-settings` with descriptive errors on bad values
- [ ] Category parameters enforced by `enum.Enum` generating strict JSON Schema — LLM cannot hallucinate invalid values
- [ ] Zero-trust Dockerfile published; server runs as non-root with isolated storage volumes
- [ ] GitHub Actions workflows automate documentation drift detection and benchmark regression gating
- [ ] Every tool endpoint wrapped in a sanitized error boundary that guides the LLM on retry strategy
- [ ] Vector search telemetry (latency, HR@5 proxy, memory) emitted to native OS log on every query

## Out of Scope

- Multi-tenant authentication or per-user data isolation
- Replacing LanceDB with another vector store
- Adding documentation sources beyond the 5 Plesk categories
- Building a Grafana dashboard (telemetry emission only; dashboard is consumer's responsibility)
- Changing the public tool names `search_plesk_unified` and `refresh_knowledge`

---

## User Stories

### P1: Startup Validation ⭐ MVP

**User Story**: As a DevOps engineer, I want the server to fail fast with a clear validation error when a required environment variable is missing or malformed so that I don't waste 30 minutes debugging silent wrong-value behavior.

**Why P1**: Every downstream milestone depends on reliable configuration. A `LOG_LEVEL=DEBUF` typo currently silently falls back; with `pydantic-settings` it fails at import time with a descriptive message.

**Acceptance Criteria**:

1. WHEN `PLESK_MODEL_PROFILE=invalid_name` THEN system SHALL raise `pydantic_settings.ValidationError` at import time with the valid choices listed
2. WHEN `LOG_LEVEL=DEBUF` (typo) THEN system SHALL raise `ValidationError` listing valid choices (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)
3. WHEN all env vars are valid THEN system SHALL initialize identically to the current behavior
4. WHEN a required env var is absent but has a default THEN system SHALL apply the default without error

**Independent Test**: Set `PLESK_MODEL_PROFILE=garbage` and run `python -c "from plesk_unified.server import mcp"` — it should print a `ValidationError` and exit non-zero.

---

### P1: Strict Category Contracts ⭐ MVP

**User Story**: As an LLM agent, I want the `category` parameter on `search_plesk_unified` to be restricted to an explicit enum so that I cannot accidentally pass an invalid value and receive a confusing empty-results response.

**Why P1**: Invalid category strings silently return zero results today, causing the LLM to hallucinate an explanation. A JSON Schema `enum` constraint gives the LLM the valid values before it even makes the call.

**Acceptance Criteria**:

1. WHEN the MCP tool schema is introspected THEN `category` SHALL appear as `{"enum": ["guide", "cli", "api", "php-stubs", "js-sdk"]}` in the JSON Schema
2. WHEN `target_category` on `refresh_knowledge` is introspected THEN it SHALL appear as `{"enum": ["guide", "cli", "api", "php-stubs", "js-sdk", "all"]}`
3. WHEN an invalid string is passed at runtime THEN FastMCP SHALL reject it with a schema validation error before the function body executes

**Independent Test**: Call `mcp.get_tool("search_plesk_unified")` and assert `inputSchema.properties.category.enum` equals the 5-element list.

---

### P1: Sanitized Error Boundary ⭐ MVP

**User Story**: As an LLM agent, I want tool errors to return a structured retry-guidance message rather than a raw Python traceback so that I know exactly what to try next.

**Why P1**: Without error boundaries, any `RuntimeError` or `lancedb.exceptions.*` propagates as a raw exception string. The LLM then either retries blindly or hallucinates a fix based on internal Python stack details.

**Acceptance Criteria**:

1. WHEN any MCP tool raises an unhandled exception THEN system SHALL log the full traceback to the OS log
2. WHEN any MCP tool raises an unhandled exception THEN system SHALL return a string beginning `"[ERROR]"` followed by a human-readable description and a suggested next action (e.g., `"Try calling warmup_server first."`)
3. WHEN a `lancedb` table-not-found error occurs THEN the returned message SHALL instruct the LLM to call `refresh_knowledge` first
4. WHEN the error boundary catches an exception THEN it SHALL NOT include Python file paths or internal variable names in the returned string

**Independent Test**: Monkeypatch `get_table()` to raise `RuntimeError("test")` and call `search_plesk_unified("test")` — assert the return value starts with `"[ERROR]"` and contains no stack trace.

---

### P1: Hardware Degradation Warning ⭐ MVP

**User Story**: As a server operator, I want a clear warning log entry when the compute device silently falls back to CPU so that I can diagnose unexpected latency spikes without manual inspection.

**Why P1**: Silent CPU fallback is the #1 cause of unexplained 10× latency regression reports. Visibility costs nothing but saves hours of debugging.

**Acceptance Criteria**:

1. WHEN CUDA is available but fails to initialize for any model THEN system SHALL emit `WARNING: CUDA requested but fell back to CPU: <reason>`
2. WHEN MPS is available but fails to initialize THEN system SHALL emit `WARNING: MPS requested but fell back to CPU: <reason>`
3. WHEN `FORCE_DEVICE=cuda` is set but CUDA is unavailable THEN system SHALL emit `WARNING: FORCE_DEVICE=cuda but CUDA unavailable, falling back to CPU`

**Independent Test**: Mock `torch.cuda.is_available()` to return `True` then mock the model to raise on device `"cuda"`; assert a `WARNING`-level log with `"fell back to CPU"` is emitted.

---

### P2: Async Tool Handlers

**User Story**: As an MCP host client, I want to poll `daemon_health` while `search_plesk_unified` is processing a query so that I can show a live status indicator without the server locking up.

**Why P2**: The current synchronous handlers lock the thread during vector inference (~200 ms). With multiple concurrent MCP requests, this causes queueing. `async def` + `run_in_executor` eliminates the bottleneck.

**Acceptance Criteria**:

1. WHEN `search_plesk_unified` is executing THEN `daemon_health` SHALL respond within 50 ms
2. WHEN two `search_plesk_unified` calls arrive concurrently THEN both SHALL complete without deadlock
3. WHEN the event loop is running THEN no tool handler SHALL call a blocking I/O function directly (verified by `asyncio.get_event_loop().run_until_complete` test)

**Independent Test**: Use `asyncio.gather` to fire two `search_plesk_unified` tasks simultaneously and assert both return results (no timeout after 5s).

---

### P2: Background Indexing with Job Polling

**User Story**: As an LLM agent, I want `trigger_index_sync` to return immediately with a job ID so that I can continue helping the user while indexing runs in the background.

**Why P2**: `refresh_knowledge` on 500+ files takes 10–15 minutes. The current synchronous approach causes MCP client timeouts and prevents any other tool from being called during indexing.

**Acceptance Criteria**:

1. WHEN `trigger_index_sync` is called THEN system SHALL return `{"job_id": "<uuid>", "status": "queued"}` within 200 ms
2. WHEN `check_sync_status(job_id)` is called during indexing THEN system SHALL return `{"status": "running", "progress": <0-100>, "current_source": "<cat>", "files_processed": <n>}`
3. WHEN indexing completes THEN `check_sync_status(job_id)` SHALL return `{"status": "done", "report": "<per-source summary>"}`
4. WHEN `check_sync_status` is called with an unknown `job_id` THEN system SHALL return `{"status": "not_found"}`
5. WHEN `refresh_knowledge` is called THEN it SHALL delegate to `trigger_index_sync` and block until `status == "done"` for backward compatibility

**Independent Test**: Call `trigger_index_sync("all", False)` and assert the return JSON has `job_id` key and `status == "queued"` before 200 ms; then poll `check_sync_status(job_id)` until done.

---

### P2: TOC as MCP Resource

**User Story**: As an LLM agent, I want to browse the Plesk documentation table of contents by category without spending tokens on a full vector search so that I can orient myself before asking precise questions.

**Why P2**: LLMs often start with broad orientation queries ("What's in the Extensions Guide?") that don't need semantic retrieval. A Resource endpoint lets them passively read the hierarchy for zero marginal cost.

**Acceptance Criteria**:

1. WHEN `plesk://toc/guide` is resolved THEN system SHALL return the parsed `toc.json` for the extensions guide as a JSON document with `{title, filename, children[]}` hierarchy
2. WHEN `plesk://toc/api` is resolved THEN system SHALL return the api-rpc TOC similarly
3. WHEN a category has no `toc.json` THEN system SHALL generate a virtual TOC from the directory file list
4. WHEN an invalid category is passed THEN system SHALL return a 404-equivalent MCP error

**Independent Test**: Resolve `plesk://toc/guide` and assert the response is valid JSON with a non-empty top-level `children` array.

---

### P2: Standardized Prompt Templates

**User Story**: As an LLM agent, I want to invoke a named prompt template that pre-loads the relevant Plesk context so that I don't have to issue multiple search queries to establish baseline knowledge.

**Why P2**: Prompt templates encode expert knowledge about which context to pre-load and in what order. They save the user from having to specify context every session.

**Acceptance Criteria**:

1. WHEN `plesk-extension-dev-guide` prompt is invoked THEN system SHALL return a message sequence that includes the Extensions Guide TOC and 3 seed search results for "extension structure"
2. WHEN `plesk-api-integration` prompt is invoked THEN system SHALL include the API RPC TOC and sample `client.request()` patterns
3. WHEN `plesk-cli-reference` prompt is invoked THEN system SHALL include the CLI Linux TOC and common command examples

**Independent Test**: Invoke each prompt and assert the returned message list is non-empty and contains the category-appropriate content.

---

### P2: JSON-RPC Progress Notifications

**User Story**: As an MCP host client (e.g., Claude Desktop), I want to see a visual progress indicator while the server is indexing or running vector inference so that I don't think the server has hung.

**Why P2**: Long-running operations without feedback cause users to cancel and retry, often corrupting the indexing state.

**Acceptance Criteria**:

1. WHEN `refresh_knowledge` processes files THEN system SHALL call `ctx.report_progress(files_done, total_files)` after each file batch
2. WHEN `search_plesk_unified` runs embedding + reranking THEN system SHALL call `ctx.report_progress(1, 3)` after embedding and `ctx.report_progress(2, 3)` after reranking
3. WHEN no `Context` is available (backward compat call) THEN system SHALL proceed silently without error

**Independent Test**: Monkeypatch `ctx.report_progress` to append to a list; run `refresh_knowledge` and assert the list has at least 2 entries.

---

### P3: LLM Sampling for Payload Minification

**User Story**: As a token-budget-conscious LLM user, I want the server to summarize the top-5 retrieved documents before transmitting them so that my context window isn't flooded with raw documentation text.

**Why P3**: Useful for long documentation chunks but introduces latency and requires host client sampling support. Opt-in via `PLESK_ENABLE_SAMPLING`.

**Acceptance Criteria**:

1. WHEN `PLESK_ENABLE_SAMPLING=true` AND host client supports sampling THEN system SHALL use `ctx.sample()` to summarize the top-5 results before returning
2. WHEN `PLESK_ENABLE_SAMPLING=false` OR host client does not support sampling THEN system SHALL return the full text as currently
3. WHEN sampling call fails THEN system SHALL fall back to full text return

**Independent Test**: Set `PLESK_ENABLE_SAMPLING=true`, monkeypatch `ctx.sample()` to return `"SUMMARY"`, call `search_plesk_unified` and assert the return contains `"SUMMARY"`.

---

### P3: Dynamic VRAM Auto-Tuning

**User Story**: As an operator running the server on shared GPU hardware, I want the server to automatically select the optimal quantization level based on available VRAM so that it doesn't OOM on constrained hardware.

**Why P3**: Useful but conservative: the existing profile system already supports manual selection. Auto-tuning adds convenience at the cost of non-determinism.

**Acceptance Criteria**:

1. WHEN free VRAM < 4 GB THEN system SHALL automatically use `tq_bits=3` and log the reason
2. WHEN free VRAM ≥ 8 GB THEN system SHALL use dense float16 and log the reason
3. WHEN running on CPU THEN auto-tuning logic SHALL be skipped silently
4. WHEN `PLESK_MODEL_PROFILE` is explicitly set THEN auto-tuning SHALL be disabled (explicit > auto)

**Independent Test**: Mock `torch.cuda.mem_get_info()` returning `(3_000_000_000, 8_000_000_000)` and assert `tq_bits == 3` in the active profile.

---

### P3: Zero-Trust Dockerfile

**User Story**: As a DevOps engineer, I want a Dockerfile that I can `docker build` and `docker run` without installing Python, CUDA drivers, or pip dependencies on the host so that I can deploy the server to any container runtime.

**Why P3**: High impact but orthogonal to functional correctness. Can be developed in parallel with other milestones.

**Acceptance Criteria**:

1. WHEN `docker build -t plesk-unified .` completes THEN the image SHALL build without error on an x86_64 host with Docker ≥ 24
2. WHEN `docker run plesk-unified` starts THEN the MCP server SHALL become ready within 120 s
3. WHEN the container runs THEN the process SHALL run as non-root user `plesk` (UID 1000)
4. WHEN the container runs THEN `/app/storage` and `/app/knowledge_base` SHALL be declared as `VOLUME` mount points
5. WHEN `docker build --build-arg CUDA_VARIANT=cu124` is used THEN the image SHALL install the CUDA PyTorch variant

**Independent Test**: `docker build .` exits 0; `docker inspect <image>` shows `User: plesk`; `docker run --rm plesk-unified python -c "from plesk_unified.server import mcp; print('ok')"` prints `ok`.

---

### P3: Cryptographic Roots Constraints

**User Story**: As a security engineer, I want the server to enforce that all file path arguments are constrained to approved base directories so that a prompt-injected path traversal attack cannot escape the sandbox.

**Why P3**: Critical for hardened deployments but not needed for single-user developer setups.

**Acceptance Criteria**:

1. WHEN `list_roots` is called THEN system SHALL return `[{uri: "file:///app/knowledge_base"}, {uri: "file:///app/storage"}]`
2. WHEN a tool argument contains `../` or resolves outside the approved roots THEN system SHALL reject the call with `"[ERROR] Path traversal detected. Operation rejected."`
3. WHEN `target_category` is a valid enum value THEN the path check SHALL always pass (categories map to known subdirs)

**Independent Test**: Call `refresh_knowledge` with `target_category="../../etc"` (or bypass enum for unit test) and assert the error boundary returns the traversal error message.

---

### P3: CI/CD Documentation Drift Detection

**User Story**: As a maintainer, I want a weekly GitHub Actions cron job that auto-detects when Plesk upstream documentation has changed and opens a PR so that the knowledge base never goes stale silently.

**Why P3**: High value for long-term maintenance but has no runtime effect on the server.

**Acceptance Criteria**:

1. WHEN the cron workflow runs THEN it SHALL execute `manage_plesk_docs.py` and `enrich_toc.py`
2. WHEN any file in `knowledge_base/` changes THEN the workflow SHALL commit the changes and open a PR or push to a `docs-sync` branch
3. WHEN no files change THEN the workflow SHALL complete without creating a PR

**Independent Test**: Trigger the workflow manually via `workflow_dispatch`; assert the workflow run completes successfully (even if no changes).

---

### P3: Automated Benchmark Regression

**User Story**: As a PR reviewer, I want a GitHub Actions check that automatically comments with the HR@5 / MRR@5 delta whenever a PR could affect retrieval quality so that regressions are caught before merge.

**Why P3**: Continuous quality gating; no runtime effect.

**Acceptance Criteria**:

1. WHEN a PR is opened or updated THEN the workflow SHALL run `benchmark_profiles.py`
2. WHEN HR@5 or MRR@5 regresses > 5% vs `main` THEN the workflow SHALL post a PR comment with the delta table and fail the check
3. WHEN metrics are stable or improved THEN the workflow SHALL post a passing comment and succeed

**Independent Test**: Run the workflow manually on a branch; assert a comment is posted to the PR.

---

## Edge Cases

- WHEN `pydantic-settings` raises `ValidationError` THEN the server SHALL exit with code 1 and print the full validation error to stderr
- WHEN a background indexing job's thread crashes THEN `check_sync_status` SHALL return `{"status": "failed", "error": "<sanitized message>"}`
- WHEN `ctx.sample()` times out THEN `search_plesk_unified` SHALL fall back to full text within 5 s
- WHEN `toc.json` is missing for a category THEN the resource endpoint SHALL generate a virtual TOC and annotate the response with `"virtual": true`
- WHEN Docker image is built on ARM64 THEN the CUDA build arg SHALL be silently ignored

---

## Success Criteria

How we know the full uplift is successful:

- [ ] `python -m pytest tests/` passes with no regressions after all changes
- [ ] `ruff check plesk_unified/` reports zero new violations
- [ ] MCP tool schema introspection shows `enum` constraint on all `category` parameters
- [ ] `docker build .` completes successfully on CI
- [ ] Both GitHub Actions workflows execute without error on `main`
- [ ] HR@5 and MRR@5 metrics in `benchmark_output.txt` remain within 5% of baseline
- [ ] `daemon_health` responds in < 50 ms while `search_plesk_unified` is executing (concurrency test)
