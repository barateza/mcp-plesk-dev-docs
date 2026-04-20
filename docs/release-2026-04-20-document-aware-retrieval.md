# Release: Document-aware retrieval & Benchmark Gates (2026-04-20)

This release introduces a set of document-aware retrieval improvements, an automated benchmark baseline capture workflow, and enforceable quality gates. It is intended to improve ranking stability, reduce noisy chunking artifacts, and provide reproducible regression detection for retrieval quality.

**Summary (high-level)**

- Document-aware chunking and HTML table normalization to preserve semantic structure.
- Doctype-aware routing and DocType stamping for better downstream reranking.
- Source fingerprinting and selective reindex on startup to shrink refresh windows.
- Low-confidence retrieval fallback with environment-configurable threshold.
- Benchmark baseline capture and quality gates integrated into the benchmark runner.

**Key files changed/added**

- `plesk_unified/chunking.py`: sentence-window and hierarchical chunkers for PHP/JS and long HTML pages.
- `plesk_unified/html_utils.py`: table-to-prose normalization and integration into the HTML parsing flow.
- `plesk_unified/io_utils.py`: `compute_source_fingerprint()` to detect changed sources.
- `plesk_unified/server.py`: doctype inference, DocType stamping, selective reindex, and low-confidence fallback.
- `plesk_unified/benchmark_gates.py`: baseline capture, gate evaluation, and reporting helpers.
- `scripts/benchmark_profiles.py`: CLI flags and wiring for baseline capture, gate evaluation, and failing on gate violations.
- `benchmarks/gates/default.json`: default gate thresholds used by the benchmark runner.
- `docs/benchmarks.md`: runbook updated with baseline/gate usage instructions.

**Motivation & rationale**

1. Semantic chunk boundaries are critical for retrieval: naive fixed-size chunks often split headings or tables, harming reranker performance. The new chunkers prefer sentence windows and hierarchical grouping to keep conceptual units intact.
2. HTML tables frequently encode configuration or examples; converting tables to prose before chunking preserves their semantics in the embeddings.
3. Full reindexes on every start are slow and unnecessary; fingerprinting enables incremental reindexing by filename and content signature.
4. Benchmarks need to be continuously comparable. Built-in baseline capture + gates provide deterministic regression checks for `hit_rate`, `mrr`, and latency.

**Developer notes & environment flags**

- `PLESK_MIN_RELEVANCE_THRESHOLD` (env): fallback threshold for low-confidence retrieval (default ~0.55). If top-ranked results fall below this value, the server can trigger an alternative pathway (e.g., contextual expansion or broader candidate pool).
- `PLESK_AUTO_REFRESH_ON_STARTUP` (env): controls automatic refresh behavior on server start.
- `PLESK_MODEL_PROFILE` (env): `light|medium|full` selects embedding and reranker profiles used by the benchmark runner and server.

**How to reproduce the benchmark baseline capture**

Activate your virtualenv and run the benchmark capture command (example used during validation):

```bash
source .venv/bin/activate
python scripts/benchmark_profiles.py \
  --suite control \
  --profile medium \
  --engine baseline \
  --refresh \
  --capture-baseline \
  --baseline-file benchmarks/baselines/control-medium.json \
  --output /tmp/control_medium_iter_1.json
```

**Where to look for artifacts**

- Baseline artifact: `benchmarks/baselines/control-medium.json`
- Gate config: `benchmarks/gates/default.json`
- Full run output (example): `/tmp/control_medium_iter_1.json`

**Tests & verification**

All new and updated tests passed locally (114/114). Relevant test modules:

- `tests/test_chunking.py`
- `tests/test_html_utils.py`
- `tests/test_io_utils.py`
- `tests/test_benchmark_gates.py`

**Release metadata**

- Commit: `52c07b0` (pushed to `origin/main`)
- Release date: 2026-04-20

**Next steps / recommendations**

1. Add a CI job to run the benchmark/gate comparison on PRs and fail when gates break.
2. Consider promoting DocType to a persisted DB field and add a migration for existing indexes.
3. Integrate an external judge (RAGAS or similar) to enable faithfulness/context-recall gates.

---

If you want, I can now open a PR with these docs, add the CI job, or run the benchmark gate check in CI form locally. Which would you like next?
