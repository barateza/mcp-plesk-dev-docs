# Project State — Enterprise AI Infrastructure Uplift

**Last Updated:** 2026-04-16
**Session:** Initial spec creation
**Status:** Planning phase complete; ready for M1 implementation

---

## Current Focus

Milestone M1 — Foundation & Protocol Contracts (4 features, all low-impact quick wins)

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

---

## Blockers

_None currently._

---

## Preferences

_No model guidance tips have been shown yet._

---

## Completed

_Nothing yet — spec phase only._

---

## Notes

- The `.specs/features/enterprise-ai-infrastructure/` feature folder covers all 20 features across 10 pillars as a single coordinated uplift
- Individual milestones (M1–M5) map to natural implementation phases; each milestone is independently shippable
- The `server.py` file is 800+ lines; the async refactor (M2) will likely require splitting it into `server.py` + `indexing.py` + `search.py` sub-modules
