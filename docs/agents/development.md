# Development

Stack, layout and the guidance that applies when changing retrieval behaviour.

## Stack

- **Python 3.13+** (`requires-python >=3.13`, `.python-version: 3.13`)
- **FastMCP** (`fastmcp>=3.2.4`) — MCP server framework
- **LanceDB** (`lancedb>=0.40.0`) — vector database (hybrid search: vector + native
  FTS; the Tantivy backend was removed in 0.40)
- **sentence-transformers** — embeddings (`BAAI/bge-m3`) + cross-encoder reranking
- **tq-search** — local editable dep for TurboQuant 4-bit quantization (see `hazards.md`)
- **pydantic-settings** — env-var config (`PleskSettings`)

## Layout

- `mcp_plesk_dev_docs/` — the package (application, config, domain, formatting, infrastructure, server)
- `tests/` — 20 flat test files, pytest with `asyncio_mode=auto`
- `scripts/` — benchmark runner, TOC enrichment, summary-cache backfill
- `knowledge_base/` — raw docs (api-rpc, cli-linux, extensions-guide, sdk, stubs)
- `storage/` — LanceDB DBs, source_state.json, summaries_cache.json, turboquant pickles, logs
- `benchmarks/` — baseline JSONs, gate config, benchmark suites
- `.specs/features/` — feature specs (design.md, spec.md, tasks.md per feature); gitignored, local only

## RAG indexing and development

- **Apple Silicon (MPS)**: indexing automatically detects `mps` and reduces
  `BATCH_SIZE_CHUNKS=256` for stability.
- **Prefer the `medium` profile** during development (`PLESK_MODEL_PROFILE=medium`).
  ~3x faster to index than `full`.
- **Use `reset_db=False` (incremental refresh) by default.** Chunk-level fingerprinting
  skips re-embedding identical content. Bump `CHUNK_VERSION` only when modifying
  structural HTML normalization, chunking boundaries, or embedding enrichment — see
  ADR [0003](../adr/0003-chunk-versioning-drives-re-embedding.md).
- **Chunk batching**: indexing batches by chunk count (default 1000), not file count.
- **Parallel indexing**: sources are indexed in parallel via `ThreadPoolExecutor`.
  LanceDB handles concurrent appends safely; the PID-file lock is what keeps *other
  processes* out — see ADR [0002](../adr/0002-pid-file-lock-for-lancedb-access.md).
- **Hybrid search** (vector + FTS) is the default. Queries must pass
  `query_type="fts"` — the default `"auto"` embeds the string and runs a *vector*
  search even when an inverted index exists. The native FTS index must be rebuilt
  after indexing, and a rebuild failure must fail the job — see ADR
  [0001](../adr/0001-full-text-search-in-lancedb.md).
- Maintain low cyclomatic complexity — decompose functions exceeding Ruff C901 thresholds.

## Retrieval integrity

- **FTS validation**: after any indexing, verify the FTS index is rebuilt and returning
  keyword-exact results.
- **AST-aware chunking**: for PHP and JS/TS sources, prefer AST-aware chunking
  (`plesk_enable_ast_chunking`) — preserves class/method boundaries.
- **Deterministic tools**: use `get_file_content` for full document retrieval and
  `resolve_references` for symbol cross-referencing when vector snippets are insufficient.
- Use `verify_refresh.py` to confirm incremental indexing correctly skips unchanged sources.
