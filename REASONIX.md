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
- **Issues**: tracked via GitHub Issues — use `gh issue list/create/close`
- **Import style**: absolute imports (`from mcp_plesk_dev_docs.X import Y`)
- **Shell safety**: Never use `bash -c` with inline code strings. Use single-quoted heredocs (`cat << 'EOF' > file`) to prevent shell expansion. Always use non-interactive flags (`cp -f`, `rm -rf`, `ssh -o BatchMode=yes`).

## Quick Reference
```bash
git pull --rebase                                            # Session start
gh issue list --state open                                   # Find work
gh issue view <number> --comments                            # Issue details
gh issue comment <number> --body "..."                       # Add comment
gh issue edit <number> --add-label "..."                     # Apply labels
gh issue close <number> --comment "..."                      # Complete work
```

## Agent Workflow

### 1. Session Start (Dual-Sync Rule)
MUST run on session initialization: `git pull --rebase`. Use `git status` and `gh issue list` to confirm latest state.

### 2. Long-Running Tasks (Heartbeat Rule)
NO silent sleeps. Polling background tasks (indexing, benchmarks) MUST:
1. Poll status: `while kill -0 $PID 2>/dev/null; do ... done`
2. Print heartbeat + timestamp every 60s.
3. `tail -n 5` relevant logs in each loop for verifiable progress.

```bash
while kill -0 $PID 2>/dev/null; do
  echo "[$(date +%T)] Still running..."
  tail -n 5 output.log
  sleep 60
done
```

### 3. Quality & Benchmarking (Hard Restriction)
- **No Speculative Pushing**: Execution of `git push` is FORBIDDEN until `python scripts/benchmark_profiles.py --fail-on-gate` passes.
- **Evidence-Based**: Include `MRR@5` and `Hit Rate` in final session summary.
- **Retrieval Integrity**: Verify FTS keyword-exact results after any indexing.
- **Verification over Inference**: Never assume a logic change improved metrics. Always rerun the `control` suite and inspect the database directly.
- **Regression Recovery**: If a gate fails, revert the logic change or tune parameters until metrics match or exceed the baseline.
- **Golden Baseline** (`benchmarks/baselines/control.json`):
  - **Light:** 100% Hit Rate, 0.917 MRR (Avg Latency: ~1.007s)
  - **Medium:** 100% Hit Rate, 0.95 MRR (Avg Latency: ~2.6s)

### 4. Session Completion
Work is NOT complete until pushed. Steps:
1. **File Issues**: Create GitHub issues for remaining/follow-up work.
2. **Quality Check**: Verify `context_recall` and `faithfulness` meet minimums.
3. **Update issues**: Close finished, update in-progress.
4. **Push All**: `git pull --rebase && git push`
5. **Verify**: `git status` MUST show "up to date with origin"
6. **Clean up**: Clear stashes, prune remote branches.

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing — that leaves work stranded locally
- NEVER say "ready to push when you are" — YOU must push
- If push fails, resolve and retry until it succeeds

## Development Guidelines

### RAG Indexing & Development
- **Apple Silicon (MPS)**: Indexing automatically detects `mps` and reduces `BATCH_SIZE_CHUNKS=256` for stability.
- **Prefer the `medium` profile** during development (`PLESK_MODEL_PROFILE=medium`). ~3x faster to index than `full`.
- **Use `reset_db=False` (Incremental Refresh) by default.** Chunk-Level Fingerprinting skips re-embedding identical content. Bump `CHUNK_VERSION` only when modifying structural HTML normalization, chunking boundaries, or embedding enrichment.
- **Chunk Batching**: Indexing batches by chunk count (default: 1000), not file count.
- **Parallel Indexing**: Sources are indexed in parallel via `ThreadPoolExecutor`. LanceDB handles concurrent appends safely.
- **Hybrid Search** (Vector + FTS) is the default; schema changes must preserve the Tantivy FTS index.
- Maintain low cyclomatic complexity — decompose functions exceeding Ruff C901 thresholds.

### Retrieval Integrity
- **FTS Validation**: After any indexing, verify the FTS index is rebuilt and returning keyword-exact results.
- **AST-Aware Chunking**: For PHP and JS/TS sources, prefer AST-aware chunking (`plesk_enable_ast_chunking`) — preserves class/method boundaries.
- **Deterministic Tools**: Use `get_file_content` for full document retrieval and `resolve_references` for symbol cross-referencing when vector snippets are insufficient.
- Use `verify_refresh.py` to confirm incremental indexing correctly skips unchanged sources.

## Agent skills

### Issue tracker
GitHub Issues on github.com/barateza/mcp-plesk-dev-docs. Use the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels
Default canonical labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs
Single-context: `CONTEXT.md` at root + `docs/adr/`. See `docs/agents/domain.md`.

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
