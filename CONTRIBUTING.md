# Contributing to Plesk Unified

We welcome community contributions. Follow these guidelines to get started.

## Setup & Workflow

1. **Fork & Clone**: `git clone https://github.com/barateza/mcp-plesk-unified.git && cd mcp-plesk-unified`
2. **Environment**: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
3. **Pre-commit**: `pre-commit install` (Runs `ruff` formatting/linting automatically).
4. **Feature Branch**: `git checkout -b feature/name`
5. **Conventional Commits**: Use `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.

## Style Guide

- **Python**: PEP 8, meaningful names, type hints, and docstrings for all functions.
- **Ruff**: Run `ruff check . --fix && ruff format .` before committing.
- **Complexity**: Keep functions focused; refactor if they exceed Ruff C901 thresholds.
- **Docs**: Update `README.md` and `docs/mcp-components.md` for any interface changes.

## Quality Assurance (Mandatory)

Before PR submission, you **MUST** verify retrieval integrity:

```bash
BP="python scripts/benchmark_profiles.py"
$BP --profile medium --fail-on-gate # Verify gates pass
$BP --profile medium --ragas         # (Optional) Run RAGAS evaluation
```

- **FTS Check**: Verify Full-Text Search index rebuilds correctly after indexing.
- **Regressions**: Never assume improvement; verify via `control` suite benchmarks.

## Pull Request Checklist

- [ ] Code follows style guide and passes `ruff` / `pyright`.
- [ ] Benchmarks pass quality gates (`--fail-on-gate`).
- [ ] No new dependencies without justification.
- [ ] Vector DB regenerated if content parsing logic changed.
- [ ] PR title/description clearly explain "why".

## Reporting Issues

- **Bugs**: Include steps to reproduce, expected vs actual behavior, and full tracebacks.
- **Security**: **DO NOT** open public issues. See [SECURITY.md](SECURITY.md).

Thank you for helping make Plesk Unified better! 🙏
