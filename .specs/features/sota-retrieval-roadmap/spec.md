# Feature spec: SOTA retrieval roadmap (Phase 1 and Phase 2)

Establish a two-phase plan that delivers near-term retrieval upgrades while
capturing heavier SOTA items for a later release.

## 1. Objectives

- Restore hybrid lexical retrieval and strengthen exact-match coverage.
- Improve code chunk boundaries with AST-aware chunking.
- Add deterministic MCP tools for file-level and reference-level lookups.
- Require inline citations in synthesized answers and enable streaming when
  supported.
- Document Phase 2 SOTA items for later implementation.

## 2. Scope

### Phase 1 (implementation)

- Re-enable FTS in hybrid search with performance guardrails.
- Add AST-based chunking for PHP and JS (optional dependency).
- Add MCP tools: get_file_content and resolve_references.
- Add inline citations in synthesized answers and plan for streaming.

### Phase 2 (documented, deferred)

- Late interaction retrieval (ColBERT or LanceDB late interaction).
- Query rewriting and HyDE pre-retrieval synthesis.
- GraphRAG for relation-aware retrieval.
- Semantic HTML chunking based on embedding similarity.
- VLM-based diagram and image captioning during indexing.

### Out of scope

- Replacing LanceDB with another vector store.
- Adding new documentation sources beyond the five Plesk categories.
- Mandatory model downloads beyond existing profiles.

## 3. Constraints

- Keep dependencies lightweight by default and gate heavy features behind
  optional extras.
- Maintain balanced latency targets for the medium profile.
- Preserve existing tool signatures for backward compatibility.

## 4. Requirements

### Phase 1 requirements

- Hybrid search SHALL include an FTS candidate pool and use RRF merging.
- AST chunking SHALL preserve class and method boundaries and fall back to
  regex or line-based chunking when parsing fails.
- MCP SHALL expose get_file_content and resolve_references with strict path
  validation.
- Synthesized answers SHALL include inline citations mapped to chunk IDs.
- Streaming SHALL be enabled only when MCP transport supports it.

### Phase 2 requirements

- Late interaction retrieval SHALL fuse with vector and FTS results.
- HyDE and query rewriting SHALL be gated by a settings flag.
- GraphRAG SHALL remain lightweight with a local graph store by default.
- Semantic HTML chunking SHALL be opt-in and benchmarked for regressions.
- VLM captioning SHALL be optional and cached to avoid reprocessing.

## 5. Success criteria

- Hybrid search returns exact keyword matches verified by FTS checks.
- Inline citations appear in every synthesized answer when enabled.
- Phase 1 changes pass retrieval quality gates without latency regressions.
- Phase 2 scope is documented with clear prerequisites and constraints.
