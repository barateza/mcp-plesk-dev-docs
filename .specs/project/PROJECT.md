# Plesk Unified MCP Server — Enterprise AI Infrastructure Uplift

**Vision:** Evolve `mcp-plesk-dev-docs` from a functional RAG server into a production-grade enterprise AI infrastructure component that is async-first, protocol-complete, observable, containerized, and continuously verified.

**For:** AI developers, Plesk extension authors, and DevOps teams who embed this MCP server into their LLM workflows.

**Solves:** The server currently works well for single-user, synchronous use but lacks the protocol depth (Resources, Prompts, progress notifications), operational maturity (async execution, Docker, CI/CD), and strict contracts (enums, Pydantic settings, error boundaries) required for production fleet deployment.

---

## Goals

- Achieve full MCP protocol coverage: Tools ✓, Resources ✗, Prompts ✗, Sampling ✗, Roots ✗
- Replace all blocking synchronous tool handlers with `async def` to support concurrent MCP requests
- Provide a zero-trust Docker distribution that encapsulates all 2 GB of ML dependencies
- Instrument every query and index operation with structured telemetry surfaced to the native OS log
- Eliminate LLM-induced hallucination vectors (invalid categories, path traversal, opaque errors)
- Automate documentation drift detection and benchmark regression reporting in CI/CD

---

## Tech Stack

**Core:**

- Framework: FastMCP ≥ 3.2.0
- Language: Python 3.12 / 3.13
- Vector DB: LanceDB ≥ 0.29.1

**Key dependencies:** sentence-transformers, torch, pydantic ≥ 2.10, python-dotenv, gitpython

---

## Scope

**This uplift includes (20 features across 10 pillars):**

- Pydantic BaseSettings for all environment variable validation
- Context Dependency Injection replacing global singletons
- Strict `enum.Enum` category parameters on all tools
- Decoupled `trigger_index_sync` / `check_sync_status` tools
- `@mcp.resource("plesk://toc/{category}")` endpoint
- `@mcp.prompt` templates for extension development workflows
- Dynamic VRAM auto-tuning (3-bit ↔ 5-bit ↔ float16)
- Hardware degradation telemetry for silent CPU fallback
- JSON-RPC progress notifications via `ctx.report_progress`
- LLM Sampling primitive for payload minification
- Rich Markdown result cards with hyperlinked citations
- Interactive folder UI for TOC resource navigation
- Sanitized error boundary decorator for all tool endpoints
- Vector search telemetry (latency, HR@5, memory) to OS log
- Async `search_plesk_unified` and `refresh_knowledge` handlers
- Background polling architecture returning instant `job_id`
- Distroless Dockerfile with isolated storage volumes
- Protocol Roots enforcement against path traversal
- GitHub Actions cron drift detection workflow
- Automated benchmark regression PR commenting

**Explicitly out of scope:**

- Multi-tenant authentication / user isolation
- Replacing LanceDB with a different vector store
- Supporting documentation sources outside the 5 Plesk categories
- Frontend dashboard UI (Grafana dashboards are external consumers)
- Breaking changes to the existing `search_plesk_unified` / `refresh_knowledge` tool signatures

---

## Constraints

- **Technical:** All changes must remain backward-compatible with existing MCP clients that call the current tool names and signatures
- **Technical:** Async refactor must not break the `PLESK_DAEMON_AUTO_WARMUP` background thread mechanism
- **Technical:** Docker image must support both CPU and CUDA targets via build arguments
- **Resources:** No new ML models or vector stores may be introduced; existing model profiles are fixed
