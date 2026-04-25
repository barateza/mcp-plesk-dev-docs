# Contributing to Plesk Unified

Thank you for your interest in contributing to Plesk Unified! We welcome
contributions from the community. This document provides guidelines and
instructions for contributing.

## Code of conduct

Be respectful and constructive in all interactions. We maintain a welcoming and
harassment-free environment for everyone.

## Getting started

1. **Fork the repository** on GitHub.
2. **Clone your fork** locally:

   ```bash
   git clone https://github.com/barateza/mcp-plesk-unified.git
   cd mcp-plesk-unified
   ```

3. **Create a virtual environment**:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

4. **Install development dependencies**:

   ```bash
   pip install -e .
   ```

## Make changes

1. **Create a feature branch**:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** according to the style guide below.

3. **Test your changes**:

   ```bash
   python -m plesk_unified.server  # Verify the server starts correctly
   ```

4. **Commit with clear messages**:

   ```bash
   git commit -m "feat: add support for X" -m "Detailed explanation of changes"
   ```

   Use conventional commits:
   - `feat:` for new features
   - `fix:` for bug fixes
   - `docs:` for documentation changes
   - `refactor:` for code refactoring
   - `test:` for test additions
   - `chore:` for maintenance tasks

## Style guide

### Python code

- Follow [PEP 8](https://pep8.org/) style guidelines.
- Use meaningful variable and function names.
- Add docstrings to functions and classes:

  ```python
  def search_knowledge_base(query: str, max_results: int = 10) -> list[dict]:
      """
      Search the Plesk knowledge base for relevant documentation.

      Args:
          query: The search query string
          max_results: Maximum number of results to return

      Returns:
          List of documentation entries matching the query
      """
  ```

- Keep lines under 100 characters when reasonable.
- Use type hints for function arguments and return values.

### Comments and documentation

- Write clear, concise comments detailing the "why" instead of the "what".
- Update `README.md` with new features.
- Document configuration changes.
- Add examples for new functionality.

## Submit changes

1. **Push to your fork**:

   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create a Pull Request** on GitHub with:
   - A clear title describing the changes.
   - A description of what changed and why.
   - A reference to any related issues (e.g., "Fixes #123").
   - Screenshots or examples if applicable.

3. **Respond to review comments** promptly and professionally.

## Benchmarking and Quality Gates

Before submitting changes that affect retrieval logic, chunking, or embedding, you MUST run the retrieval quality benchmark to ensure no regressions.

### Running benchmarks

```bash
# Standard benchmark on the 'medium' profile
uv run python scripts/benchmark_profiles.py --profile medium

# Run with RAGAS evaluation (requires OPENROUTER_API_KEY)
uv run python scripts/benchmark_profiles.py --profile medium --ragas

# Verify that changes meet the quality gates
uv run python scripts/benchmark_profiles.py --profile medium --fail-on-gate
```

If your changes improve metrics, you should capture a new baseline:

```bash
uv run python scripts/benchmark_profiles.py --profile medium --capture-baseline --baseline-file benchmarks/baselines/control-medium.json
```

### Retrieval integrity

- **FTS Validation:** Hybrid search is a core feature. After any indexing operation, verify that the Full-Text Search (FTS) index has been rebuilt and is returning keyword-exact results.
- **Verification over Inference:** Never assume a logic change improved metrics. Always rerun the `control` suite and inspect the database directly to confirm metadata injection.

## Project Architecture

The project has moved to a modular structure under `plesk_unified/server/`:

- `bootstrap.py`: Environment configuration and logging setup.
- `lifecycle.py`: Startup/shutdown hooks and background task management.
- `main.py`: Entry point for the MCP server.

When adding new tools, prompts, or resources:
- Tool definitions should still reside in `plesk_unified/server.py` for now, but complex logic should be moved to `application/services/`.
- Ensure new prompts are documented in `docs/mcp-components.md`.

## Pull request checklist

Before submitting a PR, ensure:

- [ ] Code follows the style guide.
- [ ] Changes include proper documentation.
- [ ] You add no unnecessary dependencies.
- [ ] You regenerate the vector database if content parsing changed.
- [ ] **Benchmarks pass quality gates** (`--fail-on-gate`).
- [ ] You resolve merge conflicts with the main branch.
- [ ] Commit messages are clear and conventional.

## Report issues

### Bug reports

Include:

- A clear, descriptive title.
- Steps to reproduce.
- Expected behavior.
- Actual behavior.
- Python version and OS.
- Full error messages and traceback.
- Relevant code snippets.

### Feature requests

Include:

- A clear description of the feature.
- Use cases and benefits.
- A possible implementation approach.
- Examples of similar features in other projects.

## Questions?

- Check existing [GitHub Issues](https://github.com/barateza/mcp-plesk-unified/issues).
- Open a new Discussion or Issue.
- Be patient—maintainers are volunteers.

## Recognition

We recognize contributors in:

- Git commit history.
- Release notes for significant contributions.
- README contributors section (if implemented).

Thank you for helping make Plesk Unified better! 🙏

## Linting, type-checking, and tests

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Run the full quality suite before opening a PR:

```bash
# Lint and auto-fix (must pass in CI)
ruff check . --fix
ruff format .

# Type check
pyright plesk_unified/

# Run tests
pytest
```

## Pre-commit hooks

We use `pre-commit` to run formatters and linters automatically on each commit.
The hooks include `ruff` (lint + auto-fix and code formatting). If a hook modifies files, re-run `git add` and
commit again.

Install and enable hooks locally:

```bash
python -m pip install --upgrade pre-commit
pre-commit install
pre-commit run --all-files  # optional: verify everything passes
```
