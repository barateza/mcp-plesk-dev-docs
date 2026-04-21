# Feature Spec: Retrieval Quality Optimization

Improve retrieval metrics (Hit Rate, Faithfulness, Context Recall) across `light` and `medium` profiles through hybrid search, structural context injection, and specialized chunking.

## 1. Objectives
*   **Recover Hit Rate:** Return from 70% to 90%+ HR@5 on the expanded control suite.
*   **Increase Faithfulness:** Improve grounding from ~0.50 to 0.80+ by expanding retrieved context windows and neighborhood retrieval.
*   **Fix API Retrieval:** Solve specific failures in endpoint matching for the REST API documentation.

## 2. Requirements (The 6 Tasks)

### Task A: Hybrid Search (Vector + BM25)
*   Integrate Full-Text Search (FTS) using LanceDB.
*   Combine vector similarity with keyword matching for technical terms (e.g., specific class names, endpoints).
*   Implement Reciprocal Rank Fusion (RRF) to merge rankings.

### Task B: Parent-Header Injection
*   Prepend document title and breadcrumb path to every chunk before embedding.
*   Ensure every chunk is self-describing even when separated from the source.

### Task C: Sentinel Window Expansion
*   Increase the default sentence-window size for HTML docs from 3 to 5.
*   Provide more surrounding context to the judge/LLM to satisfy faithfulness requirements.

### Task D: Neighborhood Retrieval
*   Implement a "Look-around" strategy at retrieval time.
*   For the top-K chunks, automatically pull adjacent chunks (prev/next) based on stored metadata.

### Task E: API Endpoint Extraction
*   Add a specialized HTML parser for API documentation.
*   Detect `GET /path` patterns and store them in a dedicated `endpoint` metadata field to prioritize exact path matches.

### Task F: Hierarchical Code Chunking (JS/PHP)
*   Replace generic line-based splitting with structural parsing.
*   Chunks should respect class and method boundaries to prevent context fragmentation in SDK documentation.

## 3. Success Criteria
*   `python scripts/benchmark_profiles.py --ragas` shows:
    *   **Hit Rate:** > 90%
    *   **Faithfulness:** > 0.80
    *   **Context Recall:** > 0.85
*   No regressions in average latency (> 2.0s per query on M2/Apple Silicon).
