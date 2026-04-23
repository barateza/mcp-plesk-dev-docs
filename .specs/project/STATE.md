# Project State — Enterprise AI Infrastructure Uplift

**Last Updated:** 2026-04-21
**Session:** Linting compliance and structural decomposition
**Status:** In-progress; Phase 6 complete; linting & pre-commit active.

---

## Current Focus

Milestone M6 — Retrieval Quality Optimization (Tasks A-F)

---

## Decisions

| ID | Decision | Rationale | Date |
|----|----------|-----------|------|
| D1 | Use `pydantic-settings` not raw `pydantic.BaseModel` | `pydantic-settings` has native `.env` file and `os.environ` parsing built in; already compatible with existing `python-dotenv` usage | 2026-04-16 |
| D2 | `CategoryEnum` defined in new `plesk_unified/types.py` module | Keeps `server.py` from growing further; `types.py` is importable by tests and other modules without circular dependency | 2026-04-16 |
| D3 | `refresh_knowledge` preserved as backward-compatible adapter in M2 | Existing MCP clients reference it by name; breaking the tool name would require all downstream clients to update their configs | 2026-04-16 |
| D4 | Async refactor uses `run_in_executor` for ML calls, not native async | sentence-transformers and TurboQuant are not async-native; thread pool offload is the correct pattern | 2026-04-16 |
| D5 | Docker base is `python:3.12-slim` not fully distroless | Distroless Python images lack `pip`; multi-stage build installs in `python:3.12-slim` builder, copies to slim final. True distroless deferred to post-MVP | 2026-04-16 |
| D6 | Sampling (Feature 5.2) gated by `PLESK_ENABLE_SAMPLING` env var | Not all MCP host clients support the sampling capability; opt-in prevents silent degradation | 2026-04-16 |
| D7 | Decouple benchmark data from code into JSON suites | Hardcoded dictionaries in `benchmark_suites.py` were becoming unmaintainable and violating line length rules. | 2026-04-21 |
| D8 | Decompose `server.py` god functions to helpers | Reducing cyclomatic complexity in `_infer_doctype`, `refresh_knowledge`, and `search_plesk_unified` to satisfy engineering standards. | 2026-04-21 |
| D9 | Enforce Ruff C901 (Complexity) and activate pre-commit | Ensures long-term maintainability by preventing "god functions" from re-emerging; pre-commit prevents CI regressions. | 2026-04-21 |

---

## Blockers

_None currently._

---

## Preferences

_No model guidance tips have been shown yet._

---

## Completed

- **Phase 6:** RAGAS evaluation plumbing (Faithfulness, Recall, Precision metrics).
- **P2:** LLM-assisted complex table normalization.
- **Structural Refactor:** Decoupled benchmark suites to JSON; decomposed search/indexing logic in `server.py`.
- **Golden Alignment:** Aligned ground-truth labels with actual retrieved chunks for 20 queries.
- **Task A & B:** Implemented Hybrid Search (Vector + FTS) and Parent-Header Context Injection. HR@5 improved to 80%.
- **Task C & D:** Implemented Sentinel Window Expansion (5 sentences) and Neighborhood Retrieval (adjacent chunks). Context Precision improved to 0.88.
- **Task E & F:** Refined API Endpoint Extraction and implemented Hierarchical Code Chunking for PHP/JS. Faithfulness improved to 0.49.
- **Code Quality:** Resolved all Ruff E501, W293, and C901 failures.
- **Refactoring:** Decomposed quality gate evaluation logic in `benchmark_gates.py`.
- **Tooling:** Installed and activated Git pre-commit hooks; added `verify_refresh.py` utility.

---

## Notes

- The `.specs/features/enterprise-ai-infrastructure/` feature folder covers all 20 features across 10 pillars as a single coordinated uplift
- Individual milestones (M1–M5) map to natural implementation phases; each milestone is independently shippable
- M6 has been added as a high-priority optimization path based on RAGAS results.
