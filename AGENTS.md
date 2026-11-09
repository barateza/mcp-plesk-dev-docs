# Agent Instructions — mcp-plesk-dev-docs

An MCP server providing semantic search over Plesk developer documentation
(hybrid vector + FTS retrieval, cross-encoder reranking, 4-bit TurboQuant).
`GLOSSARY.md` defines the vocabulary; use its terms exactly.

## Commands

```bash
uv sync                          # install all deps
uv run pytest tests/ -q          # 160 tests, ~3s
uv run ruff check mcp_plesk_dev_docs/ scripts/ tests/
uv run ruff format               # auto-format
uv run mypy mcp_plesk_dev_docs/  # type-check
uv run mcp-plesk-dev-docs        # run the server (entry: mcp_plesk_dev_docs.server:main)
```

## Hard rules

- **No speculative pushing.** `git push` is FORBIDDEN until the quality gate passes:
  `uv run python scripts/benchmark_profiles.py --profile medium --fail-on-gate`.
  Cite `MRR@5` and Hit Rate in your summary; never assume a change improved metrics.
- **Work is not complete until `git push` succeeds**, and `git status` shows
  "up to date with origin". Never stop short and hand the push back to the user.
- **No silent sleeps.** While polling indexing or benchmarks, print a heartbeat with a
  timestamp every 60s and `tail -n 5` the log. See `docs/agents/workflow.md`.
- **Commits** follow Conventional Commits (`chore:`, `fix:`, `ci:`, `refactor:`,
  `security:`). **Line length** 88 (ruff). **Imports** are absolute
  (`from mcp_plesk_dev_docs.X import Y`).
- **Shell safety.** Never `bash -c` with inline code strings — use single-quoted
  heredocs (`cat << 'EOF' > file`). Always use non-interactive flags (`cp -f`,
  `rm -rf`, `ssh -o BatchMode=yes`).

## Agent skills

### Issue tracker

Issues live in GitHub Issues at `barateza/mcp-plesk-dev-docs`, driven by the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles use their default label strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`); all five already exist in the tracker. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` at the repo root plus `docs/adr/`. See `docs/agents/domain.md`.

## Where to look

| Topic | File |
|---|---|
| Session start, long tasks, gate details, done checklist | `docs/agents/workflow.md` |
| Stack, layout, indexing profiles, retrieval integrity | `docs/agents/development.md` |
| Known traps — stale LanceDB lock, `tq-search` path, `.egg-info`, tree-sitter wheels | `docs/agents/hazards.md` |
| Setup, style guide, benchmarks, PR checklist | `CONTRIBUTING.md` |
| Architecture and features | `README.md` |
