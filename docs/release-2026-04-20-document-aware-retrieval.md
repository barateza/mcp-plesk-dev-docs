# Release: Document-aware Retrieval & Benchmark Gates (2026-04-20)

Introduces document-aware retrieval, automated baseline capture, and quality gates for regression detection.

## Highlights & Rationale
- **Semantic Structure**: sentence-window/hierarchical chunking and HTML table normalization (table-to-prose) preserve context.
- **Incremental Refresh**: Source fingerprinting detects changed files, shrinking reindex windows.
- **Reliability**: DocType stamping for reranking and low-confidence fallback (via `PLESK_MIN_RELEVANCE_THRESHOLD`) reduce noisy results.
- **Verification**: Built-in baseline capture and quality gates (`benchmarks/gates/default.json`) enable deterministic regression checks.

## Key Changes
- `chunking.py`: Sentence-window and hierarchical chunkers.
- `html_utils.py`: Table-to-prose normalization.
- `io_utils.py`: `compute_source_fingerprint()` logic.
- `server.py`: DocType stamping, selective reindex, and confidence fallback.
- `benchmark_gates.py` & `benchmark_profiles.py`: Baseline capture and gate enforcement logic.

## Environment Flags
- `PLESK_MIN_RELEVANCE_THRESHOLD`: Fallback threshold (default ~0.55).
- `PLESK_AUTO_REFRESH_ON_STARTUP`: Toggle server startup indexing.
- `PLESK_MODEL_PROFILE`: Select `light|medium|full` profile.

## Baseline Capture Reproduction
```bash
BP="python scripts/benchmark_profiles.py"
$BP --suite control --profile medium --engine baseline --refresh \
    --capture-baseline --baseline-file benchmarks/baselines/control-medium.json
```

## Validation & Artifacts
- **Tests**: 114/114 passed (covers chunking, html_utils, io_utils, gates).
- **Baseline**: `benchmarks/baselines/control-medium.json`
- **Gates**: `benchmarks/gates/default.json`
- **Metadata**: Commit `52c07b0` | Date 2026-04-20

## Next Steps
1. Add CI job to enforce benchmark gates on PRs.
2. Promote DocType to a persisted DB field.
3. Integrate external judges (RAGAS) for faithfulness gates.
