# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-05-23

### Fixed
- **Retrieval Quality for Full Profile.** Fixed `source_state.json` key isolation per-profile in `indexing_service.py` to prevent state collision, and resolved `max_rerank` candidate truncation in `search_service.py` (fixed at 35).
- **Apple Silicon MPS Deadlocks.** Bypassed thread executor during document persistence on `mps` to avoid multi-threaded PyTorch deadlocks and reduce memory footprints (eliminating the 19GB memory bloat).
- **PyTorch CPU Contention.** Added process-wide CPU threading environment variables in `bootstrap.py` to optimize macOS PyTorch execution.
- **MCP Publisher server.json Versioning.** Bumped `server.json` version metadata to `0.5.0` to fix the duplicate version error during MCP Registry publishing.

### Added
- **GitHub Actions Publish Workflow.** Configured `.github/workflows/publish.yml` to support PyPI Trusted Publishing (OIDC).

## [0.4.4] - 2026-04-21


### Added
- **`verify_refresh.py` utility.** A new helper script to verify that documentation indexing correctly skips unchanged sources based on fingerprinting.

### Changed
- **Cyclomatic complexity reduction.** Refactored `evaluate_quality_gates` and `_check_metrics` in `plesk_unified/benchmark_gates.py` into smaller, testable helper functions to improve maintainability and satisfy C901 linting rules.

### Fixed
- **Ruff linting compliance.** Resolved multiple linting failures (E501 line length, W293 blank line whitespace, C901 complexity) across `benchmark_gates.py`, `server.py`, and `benchmark_engines.py`.

### Security
- **Git pre-commit hooks.** Installed and activated `pre-commit` locally to enforce `ruff` linting and formatting on every commit, preventing future CI regressions.

## [0.4.3] - 2026-04-20

### Added

- **Document-aware retrieval pipeline.** Sentence-window and hierarchical chunkers, HTML table-to-prose normalization, and doctype-aware chunk routing improve chunk boundaries and semantic relevance across `guide`, `api`, `cli`, `php-stubs`, and `js-sdk` sources.
- **Source fingerprinting & selective reindex.** Startup now computes stable source fingerprints to support incremental reindexing and faster startup refreshes.
- **Low-confidence retrieval fallback.** Retrieval now includes a configurable low-confidence threshold (`PLESK_MIN_RELEVANCE_THRESHOLD`) and a fallback pathway when top results fall below the threshold.
- **Benchmark baseline capture & quality gates.** Added an automated baseline capture and gate evaluation engine to the benchmark runner to detect regressions in `hit_rate`, `mrr`, and `avg_latency_s`.

### Changed

- **Benchmark runner enhancements.** `scripts/benchmark_profiles.py` gained CLI flags for baseline capture (`--capture-baseline`), baseline file selection, and gate evaluation (`--gate-config`, `--fail-on-gate`). A default gate config shipped at `benchmarks/gates/default.json`.
- **Runtime behavior.** `server.py` gained doctype inference, DocType stamping on chunks, and selective refresh hooks to avoid full reindexes on unchanged sources.

### Tests

- New and updated tests covering chunking, HTML table normalisation, source fingerprinting, benchmark gates, and end-to-end benchmark capture. Full test-suite passing locally (114 tests).

### Notes

- Release authored and pushed as commit `52c07b0` on `main`.

## [0.4.2] - 2026-04-17

### Added

- **Documentation URL attribution in search results.** `search_plesk_unified`
  now includes a `URL:` line for every result whose category has a known
  Plesk Docs base URL (`guide`, `api`, `cli`). The URL is derived
  automatically from the `zip_url` in each SOURCES entry via
  `CATEGORY_DOC_BASE_URLS` and the new `_build_doc_url` helper, closing the
  source-attribution gap identified in a side-by-side comparison with
  Context7 output. GitHub-only categories (`php-stubs`, `js-sdk`) are
  unaffected — no `URL:` line appears when no base URL is known.

### Fixed

- **`pyproject.toml` version** was still `0.3.2` after the `0.4.1` release;
  bumped to `0.4.2`.
- **`pyproject.toml` dependency indent** — `scipy` had 2-space indent
  instead of 4-space, inconsistent with all other dependencies.

### Tests

- Added `tests/test_search_helpers.py` covering `_sigmoid`, `_rerank_and_score`,
  `_deduplicate_by_filename`, `_build_doc_url`, and `CATEGORY_DOC_BASE_URLS`
  (all added in `0.4.1` with no test coverage).
- Added `test_search_result_includes_doc_url_for_html_category` and
  `test_search_result_no_url_for_github_only_categories` to
  `tests/test_startup_path.py` to verify the URL attribution end-to-end.
- Added `test_parse_html_file_preserves_code_blocks` to
  `tests/test_html_utils.py` as a regression guard for the `markdownify`
  change introduced in `0.4.1`.

## [0.4.1] - 2026-04-17

### Fixed

- **Search quality — reranker now always applied.** The `CrossEncoder` model was
  loaded at startup but never called during `search_plesk_unified`. The tool now
  fetches a wider candidate pool first (default 25, configurable via
  `PLESK_RERANK_CANDIDATES`) and runs the cross-encoder over all candidates before
  returning the top-5 results. Applies to both the standard LanceDB path and the
  `full-tq` TurboQuant path.
- **Relevance scores are now normalised to [0, 1].** Cross-encoder logits are
  mapped through a sigmoid function. Result output now shows `Relevance: 0.9341`
  instead of the raw L2 distance (`Score/Distance: 250.74`).
- **Duplicate source files no longer fill all result slots.** A
  `_deduplicate_by_filename` pass keeps only the highest-ranked chunk per source
  file, so five distinct documents are returned rather than five chunks of the
  same page.

### Changed

- `html_utils.parse_html_file` now converts cleaned HTML to Markdown via
  `markdownify` instead of stripping all formatting with `get_text()`. Code
  blocks (`<pre><code>`) and headings are preserved in indexed content, improving
  the readability of search results and matching Context7-quality output. Takes
  effect on the next `refresh_knowledge` run.

## [0.4.0] - 2026-03-09

### Added
- New cross-platform native OS logging handler (`log_handler.py`) supporting:
  - macOS: Unified Logging via `/var/run/syslog`
  - Linux: journald/syslog via `/dev/log`
  - Windows: Windows Event Log (requires `pywin32`)
- `LOG_HANDLER` environment variable to toggle between `os`, `file`, or `both`.
- Unit tests for the new log handler.
- Explicit `pytest` dependency in `pyproject.toml`.

### Changed
- Updated `model_config.py` to use `medium` as the default model profile (was `full`) for better resource efficiency.
- Refined `io_utils.py` with specific file exclusions for `api`, `guide`, and `js-sdk` categories.
- Enhanced zip extraction in `io_utils.py` to automatically strip single top-level directories.
- Adjusted `server.py` to use the new native OS logging handler.

### Fixed
- Base directory calculation in `server.py` to correctly locate the `storage` directory.

## [0.3.1] - 2026-02-22

### Changed
- Upgraded `fastmcp` framework from `3.0.0` to `3.0.1` to incorporate latest bug fixes and performance improvements.

## [0.3.0] - 2026-02-21

### Added

- Integrated `api-rpc`, `cli-linux`, and `extensions-guide` documentation sources into the unified search index.

### Changed

- Relocated manual documentation sources from `storage` to `knowledge_base` for better project organization.
- Enhanced `manage_plesk_docs.py` to automatically clean up `.zip` artifacts after extraction.
- Optimized GitHub source management in `io_utils.py` to automatically remove `.git`, `.github`, and `tests` directories from cloned repositories.

### Fixed

- Improved permission handling during directory cleanup on Windows systems.

## [0.2.0] - 2026-02-21

### Changed

- Evaluated and overhauled core documentation (`README.md`, `CONTRIBUTING.md`, `SECURITY.md`) to comply with industry standard `docs-writer` guidelines.
- Standardized documentation to use active voice, imperative mood instructions, and consistent 80-character line wrapping.

### Removed

- Deleted obsolete `TLC-Refactor-C901.md` log file.

## [0.1.0] - 2025-02-08

### Added

- Initial release of Plesk Unified MCP Server
- Unified knowledge base aggregating multiple Plesk documentation sources:
  - API Documentation
  - CLI Reference
  - Admin Guide
  - PHP API Stubs
  - JavaScript SDK
- Semantic search using BAAI/bge-m3 embeddings
- Intelligent reranking with BAAI/bge-reranker-base cross-encoder
- LanceDB vector database for efficient storage and retrieval
- Auto-Git integration for automatic PHP stubs and JS SDK updates
- FastMCP server implementation for Model Context Protocol compatibility
- HTML/PHP/JavaScript documentation parsing
- Comprehensive README and documentation
- MIT License
- Contributing guidelines

### Features

- 🧠 Multilingual semantic search beyond keyword matching
- 🎯 Cross-encoder reranking for improved result relevance
- ⚡ Efficient vector database with Apache Arrow backend
- 🔄 Automatic repository cloning and updates
- 🔌 Full MCP protocol support for integration with Claude and other AI tools

---

## Unreleased
### Changed (2026-05-22)

- **Benchmark baseline updated:** `benchmarks/baselines/light.json` updated to HR@5=1.0, MRR@5=0.917, `avg_latency_s`=1.007 after a verified re-run; the benchmark gate was re-run and accepted the new baseline.
- **Docs synchronized:** Updated `README.md`, `docs/benchmarks.md`, and `GEMINI.md` to reflect the accepted light-profile baseline and latency measurements.
- **Pre-push gate adjusted:** `.beads/hooks/pre-push` now runs the `light` profile against `benchmarks/baselines/light.json` to align the local pre-push quality gate with the active benchmark profile.
- **Human-facing rename & shim:** Added compatibility shim package `mcp_plesk_dev_docs` and updated human-facing references to `mcp-plesk-dev-docs` across README, Dockerfile, CI workflows, and CONTRIBUTING.
- **Settings & tests fixes:** Resolved Pydantic `PleskSettings` issues (`embedding_model_dimensions`, explicit `model_config` usage) and updated related tests — full test-suite and `ruff` passed locally.
- **Committed & pushed:** All changes were committed and pushed to `main` after pre-push verification passed.

### Planned

- [ ] Batch API for multiple queries
- [ ] Caching layer for frequently accessed documents
- [ ] Web UI for documentation browsing
- [ ] REST API endpoint option
- [ ] Support for additional Plesk locales
- [ ] Performance optimization for large-scale deployments
- [ ] Custom embedding model support
- [ ] Integration tests
- [ ] Docker support

---

[0.5.0]: https://github.com/barateza/mcp-plesk-dev-docs/releases/tag/v0.5.0
[0.4.4]: https://github.com/barateza/mcp-plesk-dev-docs/releases/tag/v0.4.4
[0.4.3]: https://github.com/barateza/mcp-plesk-dev-docs/releases/tag/v0.4.3
[0.4.2]: https://github.com/barateza/mcp-plesk-dev-docs/releases/tag/v0.4.2
[0.4.1]: https://github.com/barateza/mcp-plesk-dev-docs/releases/tag/v0.4.1
[0.4.0]: https://github.com/barateza/mcp-plesk-dev-docs/releases/tag/v0.4.0
[0.3.1]: https://github.com/barateza/mcp-plesk-dev-docs/releases/tag/v0.3.1
[0.3.0]: https://github.com/barateza/mcp-plesk-dev-docs/releases/tag/v0.3.0
[0.2.0]: https://github.com/barateza/mcp-plesk-dev-docs/releases/tag/v0.2.0
[0.1.0]: https://github.com/barateza/mcp-plesk-dev-docs/releases/tag/v0.1.0
