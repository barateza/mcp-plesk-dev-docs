# REASONIX.md — mcp-plesk-dev-docs

## Stack
- **Python 3.13+** (`requires-python >=3.13`, `.python-version: 3.13`)
- **FastMCP** (`fastmcp>=3.2.4`) — MCP server framework
- **LanceDB** (`lancedb>=0.29.1`) — vector database (hybrid search: vector + FTS via Tantivy)
- **sentence-transformers** — embeddings (`BAAI/bge-m3`) + cross-encoder reranking
- **tq-search** — local editable dep for TurboQuant 4-bit quantization (see Watch out for)
- **pydantic-settings** — env-var config (`PleskSettings`)

## Layout
- `mcp_plesk_dev_docs/` — the package (application, config, domain, formatting, infrastructure, server)
- `tests/` — 20 flat test files, pytest with `asyncio_mode=auto`
- `scripts/` — benchmark runner, TOC enrichment, summary-cache backfill
- `knowledge_base/` — raw docs (api-rpc, cli-linux, extensions-guide, sdk, stubs)
- `storage/` — LanceDB DBs, source_state.json, summaries_cache.json, turboquant pickles, logs
- `benchmarks/` — baseline JSONs, gate config, benchmark suites
- `.specs/features/` — feature specs with design.md, spec.md, tasks.md per feature

## Commands
```bash
uv sync                          # install all deps
uv run pytest tests/ -q          # 160 tests, ~3s
uv run ruff check mcp_plesk_dev_docs/ scripts/ tests/
uv run ruff format               # auto-format (also runs in pre-commit)
uv run mypy mcp_plesk_dev_docs/  # type-check (also runs in pre-commit)
```

Run the server: `uv run mcp-plesk-dev-docs` (entry point: `mcp_plesk_dev_docs.server:main`)

## Conventions
- **Commits**: Conventional Commits (`chore:`, `fix:`, `ci:`, `refactor:`, `security:`)
- **Line length**: 88 (ruff)
- **Pre-commit**: ruff, ruff-format, mypy, bandit, pytest (160 tests)
- **Pre-push**: quality-gate benchmark (light profile vs baseline)
- **Issues**: tracked via `bd` (beads), not markdown TODOs — run `bd prime`
- **Import style**: absolute imports (`from mcp_plesk_dev_docs.X import Y`)

## Watch out for
- **`tq-search` is a local editable dep** in `pyproject.toml`:
  `path = "/Users/gilsonsiqueira/tq-search"`. Won't resolve on other machines.
- **Concurrent LanceDB access** is prevented by a PID-file lock (`server/lock.py`).
  If the server won't start, check for a stale lock file in `storage/`.
- **`plesk_unified.egg-info/`** is stale from the pre-rename era. Only
  `mcp_plesk_dev_docs.egg-info/` is current. Delete the old one if it causes
  confusion.
- **`knowledge_base/` sources** are downloaded at runtime (git clone / zip fetch)
  by `infrastructure/sources/acquisition.py`. They are gitignored patterns in
  `.gitignore` under `storage/` but the `knowledge_base/` directory itself is
  committed empty.
- **`tree-sitter-language-pack`** replaced `tree-sitter-languages` (no cp313
  wheels). The code in `infrastructure/parsers/chunking.py` imports it inside
  a try/except — AST chunking degrades gracefully if unavailable.
