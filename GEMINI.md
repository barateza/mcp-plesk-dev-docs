# Engineering Guidelines (mcp-plesk-unified)

## RAG Indexing & Development

1.  **Prefer the `medium` profile during feature development.** 
    *   `PLESK_MODEL_PROFILE=medium`
    *   It is ~3x faster to index than `full` and offers superior MRR for the Plesk English corpus. 
    *   This preserves your context window and local iteration time.

2.  **Use `reset_db=False` (Incremental Refresh) by default.** 
    *   The system uses **Chunk-Level Fingerprinting** to skip re-embedding identical content.
    *   `CHUNK_VERSION` (in `plesk_unified/server.py`) tracks logic changes. Bump this version when modifying structural HTML normalization, chunking boundaries, or embedding enrichment to force a clean re-embed of only affected chunks.
    *   Only use `reset_db=True` for major schema migrations or when switching embedding models.

3.  **Optimize GPU throughput via Chunk Batching.**
    *   Indexing now batches by **chunk count** (default: 1000) rather than file count. 
    *   This ensures maximum utilization of the 12GB VRAM on the RTX 4070 Super.

4.  **Leverage Parallel Indexing.**
    *   Documentation sources are indexed in parallel using a `ThreadPoolExecutor`. 
    *   LanceDB handles these concurrent appends safely.

## Quality & Benchmarking

*   Always re-verify retrieval quality after logic changes using `scripts/benchmark_profiles.py`.
*   Maintain the **Golden Baseline** in `benchmarks/baselines/control.json`.
*   Hybrid Search (Vector + FTS) is now the default; ensure any schema changes preserve the Tantivy FTS index.
