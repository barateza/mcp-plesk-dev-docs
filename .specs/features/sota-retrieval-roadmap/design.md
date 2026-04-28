# Design: SOTA retrieval roadmap (Phase 1 and Phase 2)

**Spec**: .specs/features/sota-retrieval-roadmap/spec.md
**Status**: Draft

## 1. Architecture overview

Phase 1 focuses on hybrid retrieval, AST chunking, and MCP tooling with minimal
new dependencies. Phase 2 captures heavier retrieval upgrades behind optional
flags.

## 2. Phase 1 design

### 2.1 Hybrid FTS re-enable

- Use LanceDB FTS results as an explicit candidate pool.
- Merge vector and FTS candidates via RRF with a fixed k.
- Keep FTS behind a settings flag to control performance impact.

### 2.2 AST-based chunking

- Add tree-sitter chunkers for PHP and JS in the chunking layer.
- Keep regex and line-based chunkers as fallbacks.
- Bump CHUNK_VERSION when AST chunking becomes active.

### 2.3 MCP tool expansion

- get_file_content reads full files by category and filename, validates paths,
  and supports optional line ranges.
- resolve_references performs FTS lookups for exact symbol matches and can
  optionally return neighbor chunks for context.

### 2.4 Inline citations and streaming

- Extend synthesis prompts to require inline citations like [1], [2].
- Return a citation map that resolves each index to filename and chunk_id.
- Stream synthesis output only when MCP supports streaming responses.

## 3. Phase 2 design

### 3.1 Late interaction retrieval

- Add a token-embedding index or table and a new retrieval path.
- Fuse late interaction results with vector and FTS via RRF.

### 3.2 Query rewriting and HyDE

- Add an optional pre-retrieval rewrite step using ctx.sample.
- Embed the synthetic passage for retrieval when enabled.

### 3.3 GraphRAG

- Extract entities and relations during indexing.
- Store a lightweight graph locally and merge traversal results with search.

### 3.4 Semantic HTML chunking

- Use sentence embeddings to split when similarity drops below a threshold.
- Cache sentence embeddings to reduce reindex time.

### 3.5 VLM diagram parsing

- Extract images and generate captions during indexing.
- Store captions as additional chunks linked to the source file.

## 4. Settings and flags

- plesk_enable_fts: enable FTS candidates for hybrid retrieval.
- plesk_enable_ast_chunking: enable tree-sitter chunkers when installed.
- plesk_enable_streaming: enable streaming for synthesis responses.
- plesk_enable_hyde, plesk_enable_query_rewrite: Phase 2 optional flags.

## 5. Verification approach

- Validate FTS exact-match behavior after any reindex.
- Confirm AST chunk boundaries on representative PHP and JS files.
- Verify citations map correctly to chunk IDs in synthesized answers.
- Run benchmark gates before updating baselines.
