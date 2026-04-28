# Tasks: SOTA retrieval roadmap (Phase 1 and Phase 2)

**Design**: .specs/features/sota-retrieval-roadmap/design.md
**Status**: Draft

---

## Phase 1: Implementation

- [ ] Re-enable FTS candidate retrieval and RRF merging.
- [ ] Add settings flag to gate FTS use and log timing.
- [ ] Implement AST chunking for PHP and JS with fallbacks.
- [ ] Add settings flag to enable AST chunking when deps exist.
- [ ] Add MCP tool get_file_content with path validation.
- [ ] Add MCP tool resolve_references with FTS lookup and optional neighbors.
- [ ] Require inline citations in synthesized answers.
- [ ] Add streaming synthesis path when MCP supports it.
- [ ] Update tests for hybrid search, MCP tools, and citations.

### Phase 1 verification

- [ ] Rebuild FTS index and confirm keyword-exact hits are surfaced.
- [ ] Validate AST chunking boundaries on representative files.
- [ ] Run benchmark gates with --fail-on-gate.

## Phase 2: Documented and deferred

- [ ] Late interaction retrieval with RRF fusion.
- [ ] Query rewriting and HyDE pre-retrieval synthesis.
- [ ] GraphRAG relation extraction and traversal fusion.
- [ ] Semantic HTML chunking based on sentence similarity.
- [ ] VLM-based diagram and image captioning.

### Phase 2 verification

- [ ] Add regression tests for new retrieval modes.
- [ ] Update baseline benchmarks only after gates pass.
