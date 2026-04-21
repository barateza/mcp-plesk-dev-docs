# Tasks: Retrieval Quality Optimization

## Phase 1: Foundation & Data Enrichment
- [ ] **Task B:** Implement Metadata Injection in `chunking.py`.
- [ ] **Task C:** Increase `window_size` to 5 in `chunking.py`.
- [ ] **Task E:** Add API endpoint extraction regex to `html_utils.py`.
- [ ] **Verification:** Re-index `light` profile and verify metadata is visible in `final_verification.json`.

## Phase 2: Hybrid Retrieval
- [ ] **Task A:** Enable FTS in `chunking.py` schema creation.
- [ ] **Task A:** Implement RRF reranking in `server.py`.
- [ ] **Task D:** Implement Neighborhood Retrieval (adjacent chunks) in `server.py`.
- [ ] **Verification:** Run `control` benchmark and verify Hit Rate > 85%.

## Phase 3: Structural Refinement
- [ ] **Task F:** Implement PHP Hierarchical Chunker.
- [ ] **Task F:** Implement JS Hierarchical Chunker.
- [ ] **Verification:** Run full RAGAS benchmark and verify Faithfulness > 0.80.

## Final Review
- [ ] Run benchmarks for `light` and `medium` profiles.
- [ ] Update `benchmarks/baselines/control.json` with new golden scores.
