# Engineering Guidelines (mcp-plesk-dev-docs)

## RAG Indexing & Development

0.  **Apple Silicon (MPS) Optimization**
    *   Indexing automatically detects `mps` and uses a reduced `BATCH_SIZE_CHUNKS=256` to ensure stability and prevent memory lock-ups during the "Materializing" phase.


1.  **Prefer the `medium` profile during feature development.**
    *   `PLESK_MODEL_PROFILE=medium`
    *   It is ~3x faster to index than `full` and offers superior MRR for the Plesk English corpus.
    *   This preserves your context window and local iteration time.

2.  **Use `reset_db=False` (Incremental Refresh) by default.**
    *   The system uses **Chunk-Level Fingerprinting** to skip re-embedding identical content.
    *   `CHUNK_VERSION` (in `plesk_unified/chunking.py`) tracks logic changes. Bump this version when modifying structural HTML normalization, chunking boundaries, or embedding enrichment to force a clean re-embed of only affected chunks.
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
    *   **Verified Performance (2026-05-01):**
        *   **Light:** 100% Hit Rate, 0.917 MRR (Avg Latency: ~1.007s)
        *   **Medium:** 100% Hit Rate, 0.95 MRR (Avg Latency: ~2.6s)

*   Hybrid Search (Vector + FTS) is now the default; ensure any schema changes preserve the Tantivy FTS index.
*   **Maintain low cyclomatic complexity.** Refactor functions that exceed Ruff C901 thresholds by decomposing logic into focused helper functions.
*   **Keep pre-commit hooks active.** Ensure `ruff check` and `ruff format` pass locally before pushing to CI.

## Tooling Utilities

*   Use `verify_refresh.py` to confirm that the incremental indexing logic correctly skips unchanged sources. This is essential for verifying that `CHUNK_VERSION` or fingerprinting logic is working as intended without waiting for a full re-index.

---

## Gemini CLI Mandates (Added April 2026)

### Long-Running Tasks & Monitoring
To prevent tool timeouts and ensure transparency, you **must not** use silent `sleep` commands or infer progress for background tasks.

**The Heartbeat Rule:**
When waiting for a background process (e.g., re-indexing, benchmarks):
1.  Use a `while` loop to poll the process status (e.g., `kill -0 $PID`).
2.  Print a "heartbeat" message with a timestamp at least every 60 seconds.
3.  `tail` the relevant log file during each iteration to provide exact, verifiable progress.

**Example Implementation:**
```bash
while kill -0 $PID 2>/dev/null; do
  echo "[$(date +%T)] Still running..."
  tail -n 5 output.log
  sleep 60
done
```

### Retrieval Integrity
- **FTS Validation:** Hybrid search is a core feature. After any indexing operation, you must verify that the Full-Text Search (FTS) index has been rebuilt and is returning keyword-exact results.
- **AST-Aware Chunking:** For PHP and JS/TS sources, prefer AST-aware chunking (enabled via `plesk_enable_ast_chunking`). This preserves structural boundaries like class and method definitions, leading to superior retrieval for technical code queries.
- **Deterministic Tools:** Use `get_file_content` for full document retrieval and `resolve_references` for symbol cross-referencing when vector search snippets provide insufficient context.
- **Verification over Inference:** Never assume a logic change improved metrics. Always rerun the `control` suite and inspect the database directly to confirm metadata injection.

### Dual-Sync Initialization
1. **Always Sync First:** You MUST run `git pull --rebase` and `bd dolt pull` as your first actions in a new session or after a long break.
2. **Prevent Split-Brain:** This ensures that changes from other machines (e.g., WSL vs macOS) are synchronized before you begin modifying files.
3. **Verify State:** Use `git status` and `bd ready` to confirm you are on the latest state of both code and issues.

### Hard Quality Restriction
1. **No Speculative Pushing:** You are strictly forbidden from executing `git push` or `bd close` until you have executed `scripts/benchmark_profiles.py` with the `--fail-on-gate` flag.
2. **Evidence-Based Completion:** You must include the `MRR@5` and `Hit Rate` results in your final session summary.
3. **Regression Recovery:** If a gate fails, you must revert the logic change or optimize the chunking/embedding parameters until the metrics match or exceed the baseline.

### Shell Command Safety
- **No Inline Expansion:** Never use `bash -c` with inline code strings to write or modify files. This prevents unintended shell expansion of variables or special characters within the code block.
- **Heredoc Requirement:** If you need to create or edit a file via the shell, you must strictly use single-quoted heredocs to prevent bash expansion.
  - **Example:** `cat << 'EOF' > filename.php`
