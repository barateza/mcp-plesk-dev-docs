# Retrieval Quality Benchmarks

Tracks retrieval quality and latency across the three built-in model profiles
(`light`, `medium`, `full`). Run with [`scripts/benchmark_profiles.py`](../scripts/benchmark_profiles.py).

---

## Latest results — 2026-05-03 (Apple Silicon, MPS)

**Hardware:** Apple M2 Pro (Mac mini)
**Python:** 3.12.12
**Query set:** 20 queries (Expanded control suite with RAGAS evaluation)
**Logic Version:** `CHUNK_VERSION=v15` (AST-Aware Chunking + MiniLM-L4 Optimization)

### Summary

|Profile|Embed model|Reranker|HR@5|MRR@5|Avg latency|Est. RAM|
|--------|------------|---|---|-----|----------|--------|
|`light`|BAAI/bge-small|**MiniLM-L4-v2**|**100.0%**|**0.950**|**3.60 s**|~200 MB|
|`medium`|BAAI/bge-base|**MiniLM-L4-v2**|**100.0%**|**0.917**|**3.73 s**|~600 MB|

> **Note:** The `medium` profile accepts a minor MRR delta (-0.033) compared to the L6 baseline in exchange for significantly improved cross-encoder latency and pipeline consistency. Both profiles are now optimized for 35 candidates.

### Reranker Optimization Matrix

We programmatically evaluated several reranker models and candidate pool sizes (`PLESK_RERANK_CANDIDATES`) to find the optimal speed/quality trade-off for edge devices.

| Reranker | Candidates | Hit Rate | MRR@5 | Avg Latency |
| :--- | :--- | :--- | :--- | :--- |
| **ms-marco-MiniLM-L-6-v2** (Old Default) | 50 | 100% | 0.950 | 4.10 s |
| **ms-marco-MiniLM-L4-v2** (New Default) | **35** | **100%** | **0.950** | **3.62 s** |
| ms-marco-MiniLM-L2-v2 | 25 | 100% | 0.967 | 3.78 s |

**Lessons Learned:**
- **MiniLM-L4-v2** is the sweet spot. It provides high-quality scoring in ~300ms on MPS, providing a ~12% overall pipeline speedup compared to L6 with zero quality loss.
- **Candidate Pool Sensitivity:** Reducing candidates from 50 to 35 stabilized MRR at 0.950. While L2-v2 was faster, it showed Hit Rate instability (95%) at larger pool sizes, making L4 the more robust choice for production.

### Latency Decomposition (Profile: light)

| Phase | Duration (ms) | % of Pipeline |
| :--- | :--- | :--- |
| **Query Embedding** | 71 ms | 1.3% |
| **Vector Search (ANN)** | 1,727 ms | 30.8% |
| **FTS Retrieval (Keyword)** | 1,720 ms | 30.7% |
| **Reranking (MiniLM-L4)** | **318 ms** | **5.7%** |
| **Context Expansion** | 62 ms | 1.1% |
| **Infrastructure & Sequential Overhead** | ~1,700 ms | 30.4% |

**Bottleneck Analysis:** The search pipeline currently executes Vector and FTS searches sequentially. Since both take ~1.7s, moving to parallel retrieval is the primary path to sub-2s latency.

---

## Results — 2026-05-01 (Apple Silicon, MPS)

## Quality Optimization Features (April 2026)

Following Phase 6 and the subsequent regression analysis on the expanded 20-query suite, several targeted retrieval and context enhancements were implemented:

1.  **Hybrid Search Tuning (REQ-2):** Optimized the Reciprocal Rank Fusion (RRF) `k` constant from 60 to **20**. This shift increases the weight of top-ranked results from both dense vector and keyword searches, specifically improving accuracy for technical terms and API paths.
2.  **Global File Summaries (REQ-3):** During indexing, the system now optionally generates a one-sentence summary of each source file using a lightweight LLM call. This summary is injected into every chunk, providing a macro-context that helps the retriever understand the document's overall purpose even in isolated chunks.
3.  **API Endpoint Extraction (REQ-4):** Enhanced the HTML parser to explicitly extract REST API signatures (e.g., `GET /v1/domains`). These signatures are added to the chunk text and included in the unique chunk hash, significantly improving retrieval for ambiguous API queries.
4.  **Rerank Pool Expansion (REQ-1):** Increased the default candidate pool size for the cross-encoder reranker from 25 to **50**. This allows the reranker to evaluate a broader set of initial semantic hits, stabilizing MRR on complex technical corpora.

---

## Latest results — 2026-04-21 (Apple M2 Ultra, MPS)

**Hardware:** Apple M2 Ultra (76-core GPU)
**Python:** 3.12.12
**Query set:** 20 queries (Expanded control suite with RAGAS evaluation)

### Summary

|Profile|HR@5|MRR@5|Avg latency|Est. RAM|
|--------|----|-----|----------|--------|
|`medium`|**85.0%**|**0.850**|1.54 s|~600 MB|

> **Note:** The current results on the expanded 20-query suite represent a more rigorous and accurate performance baseline. Recent fixes to Full-Text Search (FTS) indexing and multi-endpoint extraction (REST, XML, CLI) recovered Hit Rate from 80% to 85%.

---

## Interim results — 2026-04-21 (Apple M2 Ultra, MPS)

**Hardware:** Apple M2 Ultra (76-core GPU)
**Python:** 3.12.9
**Query set:** 20 queries (Expanded suite + Hybrid Search + Neighborhood Retrieval)

### Summary

|Profile|HR@5|MRR@5|Faith|Recall|Prec|Avg latency|
|--------|----|-----|-----|------|----|----------|
|`light`|**80.0%**|**0.800**|0.490|0.645|**0.840**|1.28 s|

> **Observation:** Hybrid Search and context expansion have recovered the `light` profile's performance on the expanded 20-query suite, bringing MRR back to 0.800. Faithfulness is stabilizing as the expanded context window provides more grounded facts for the LLM judge.

---

## Latest results — 2026-04-21 (RTX 4070 Super, CUDA)

**Hardware:** NVIDIA GeForce RTX 4070 Super (12 GB VRAM)
**Python:** 3.12.10
**Query set:** 20 queries (Expanded control suite with RAGAS evaluation)

### Summary

|Profile|Embed model|Dim|HR@5|MRR@5|Faith|Recall|Prec|Avg latency|Est. RAM|
|--------|------------|---|----|-----|-----|------|----|----------|--------|
|`light`|BAAI/bge-small-en-v1.5|384|**80.0%**|**0.800**|**0.725**|0.847|0.838|1.21 s|~200 MB|
|`medium`|BAAI/bge-base-en-v1.5|768|**80.0%**|0.735|0.708|**0.878**|**0.875**|1.30 s|~600 MB|
|`full`|BAAI/bge-m3|1024|75.0%|0.750|0.675|0.855|0.780|3.51 s|~1 800 MB|
|`full-tq`|BAAI/bge-m3|1024|75.0%|0.750|0.615|0.847|0.833|**0.32 s**|~1 300 MB|

### Observations

1. **Reranker pool expansion improves MRR.** Increasing `PLESK_RERANK_CANDIDATES` from 25 to 50 allowed the cross-encoder to evaluate a broader set of initial hits, stabilizing MRR across all profiles on the expanded 20-query suite.

2. **Quality parity at 4-bit TQ.** `full-tq` maintains identical Hit Rate and MRR to the full-precision `full` model while providing a **11x latency reduction** (0.32s vs 3.51s).

3. **Consistently high context quality.** Faithfulness (~0.61–0.72) and Recall (~0.84–0.88) remain high across all profiles, confirming that the structural normalization and neighbor expansion logic are effective for the Plesk corpus.

4. **`light` profile continues to lead in accuracy.** For English-only documentation, the `light` profile (BAAI/bge-small-en-v1.5) provides the highest combination of Hit Rate and MRR, proving that model size is less critical than specialization for this dataset.

---

## Results — 2026-03-08 (Apple M2, MacBook Air 2022)

**Hardware:** Apple M2 (8-core CPU, 8-core GPU) — MacBook Air 2022
**Python:** 3.12
**Query set:** 12 queries across all five documentation sources (see [Query set](#query-set) below)

> **Note:** The `full` profile (`BAAI/bge-m3`, ~1.5 GB weights) was intentionally skipped on this
> machine. During indexing, bge-m3 materialises intermediate attention tensors in float32 on CPU
> (MPS lacks full bge-m3 op support), temporarily consuming 5–10× the model's static size and
> pushing the M2's unified memory into heavy swap. The benchmark already shows `medium` outperforms
> `full` on this English-only corpus, so there is no quality benefit to running it here.

### Summary

|Profile|Embed model|Dim|HR@5|MRR@5|Avg latency|Est. RAM|
|--------|------------|---|----|-----|----------|--------|
|`light`|BAAI/bge-small-en-v1.5|384|**100%**|0.933|1.25 s|~200 MB|
|`medium`|BAAI/bge-base-en-v1.5|768|**100%**|**0.938**|1.31 s|~600 MB|
|`full`|BAAI/bge-m3|1024|—|—|— (skipped — OOM risk on M2)|~1 800 MB|

All profiles use the reranker `cross-encoder/ms-marco-MiniLM-L-6-v2` (`light`/`medium`).

### Observations

1. **Both runnable profiles hit 100% HR@5.** Same result as the CUDA machine — the index quality
   is hardware-independent.

2. **`medium` again has the best MRR@5 (0.938).** Matches the CUDA result exactly.

3. **Latency is ~1.25–1.31 s per query on M2.** This is comparable to the CUDA baseline
   (1.04–1.19 s) despite being CPU-only; the M2's unified memory bandwidth keeps query latency
   competitive for the `light` and `medium` models.

4. **`full` should be run on the Windows machine (4070 Super)** where VRAM handles tensor
   expansion off the main memory bus. The `lancedb_full` index should live there; the M2 only
   needs `lancedb_medium`.

### Recommendation (M2 / Apple Silicon)

|Scenario|Recommended profile|
|--------|-------------------|
|Memory-constrained (< 1 GB unified memory available)|`light`|
|Standard usage on M2|`medium` — best MRR, safe memory footprint|
|Non-English docs or multilingual queries|`full` on a CUDA machine only|

---

## Previous results — 2026-03-08

**Hardware:** NVIDIA GPU (CUDA)
**Python:** 3.12.10
**Query set:** 12 queries across all five documentation sources (see [Query set](#query-set) below)

### Summary

|Profile|Embed model|Dim|HR@5|MRR@5|Avg latency|Est. RAM|
|--------|------------|---|----|-----|----------|--------|
|`light`|BAAI/bge-small-en-v1.5|384|**100%**|0.933|1.04 s|~200 MB|
|`medium`|BAAI/bge-base-en-v1.5|768|**100%**|**0.938**|1.19 s|~600 MB|
|`full`|BAAI/bge-m3|1024|**100%**|0.889|4.58 s|~1 800 MB|

All three profiles share the same reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2` for `light`/`medium`,
`BAAI/bge-reranker-base` for `full`).

---

## Metrics

|Metric|Definition|
|------|----------|
|**HR@5** (Hit Rate at 5)|Fraction of queries where at least one relevant chunk appears in the top-5 results. A query is a "hit" if any of its `relevant` substrings appear (case-insensitive) in any result text.|
|**MRR@5** (Mean Reciprocal Rank at 5)|Average of `1/(rank of first hit)` across queries. A first hit at rank 1 scores 1.0; at rank 2 scores 0.5; no hit scores 0.0. Measures how high up relevant content appears, not just whether it appears.|
|**Faithfulness** (RAGAS)|LLM-judged metric (0.0–1.0) measuring whether the answer is grounded exclusively in the retrieved context. High scores mean no hallucinations.|
|**Context Recall** (RAGAS)|LLM-judged metric (0.0–1.0) measuring whether the retrieved context contains all necessary facts to answer the query, relative to a human-provided reference.|
|**Context Precision** (RAGAS)|LLM-judged metric (0.0–1.0) measuring the relevance of retrieved chunks to the query. High scores mean few distracting or unrelated results.|
|**Avg latency**|Wall-clock time per query including ANN search and reranking, measured on the benchmark host.|
|**Est. RAM**|Approximate resident-set-size increase from loading the embedding model and reranker, as reported by the model profile definition.|

---

## Observations

1. **All three profiles hit 100% HR@5.** Every query has at least one relevant document in its
   top-5 results, so the index covers the corpus well regardless of profile choice.

2. **`medium` has the best MRR@5 (0.938).** It ranks relevant results higher on average than both
   `light` and `full`, while adding only ~0.15 s per query over `light`.

3. **`full` (bge-m3) scores the lowest MRR (0.889) despite being the largest model.** `bge-m3` is
   a multilingual model; the Plesk documentation corpus is English-only, which appears to
   disadvantage it against the English-specialized `bge-base-en-v1.5` used by `medium`.
   If your corpus includes non-English documentation, `full` may recover its quality advantage.

4. **`full` is ~3.8–4.4× slower than `light`/`medium` on CUDA** (4.58 s vs. 1.04–1.19 s per query).
   The latency gap would be larger on CPU.

5. **RSS delta reported as 0 MB** because `psutil` is not installed in the benchmark environment.
   The *Est. RAM* column above uses the profile's static estimate instead.

### Recommendation

|Scenario|Recommended profile|
|--------|-------------------|
|Memory-constrained host (< 1 GB)|`light`|
|Most production deployments|`medium` — best MRR, moderate latency|
|Non-English docs or multilingual queries|`full`|

---

## Query set

The benchmark uses 20 hand-labelled queries spread across all five sources (expanded from the original 12).
Each query has a list of keyword substrings for hit detection, as well as `ground_truth` and `reference_context` fields for RAGAS scoring.

|#|Query|Category|Relevant keywords|
|-|-----|--------|-----------------|
|1|how to define default config settings for a Plesk extension|php-stubs|ConfigDefaults, getDefaults|
|...|...|...|...|
|20|what happens if you call plesk bin subscription on a non-existent domain|cli|subscription, error, not found|

The built-in query sets live as JSON files in `benchmarks/suites/` and are loaded by [`plesk_unified/benchmark_suites.py`](../plesk_unified/benchmark_suites.py).
You can provide your own queries with `--queries my_queries.json` (see the script docstring for format).

---

## Index statistics (at time of benchmark)

|Source|Files|Approx chunks|
|------|-----|-------------|
|php-stubs|124|~139|
|js-sdk|53|~80|
|api|466|~1 139|
|cli|81|~582|
|guide|105|~281|
|**Total**|**829**|**~2 221**|

---

## How to reproduce

```bash
# Activate the virtual environment
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Full benchmark — re-indexes every profile then runs retrieval queries
python scripts/benchmark_profiles.py --refresh

# Single profile only
python scripts/benchmark_profiles.py --refresh --profiles medium

# Custom query file
python scripts/benchmark_profiles.py --queries my_queries.json

# Save full JSON results
python scripts/benchmark_profiles.py --refresh --output results.json

# Run with RAGAS evaluation (requires OPENROUTER_API_KEY)
python scripts/benchmark_profiles.py --ragas --ragas-model google/gemini-2.5-flash-lite

# Enable LLM-assisted complex table normalization during indexing
PLESK_HTML_LLM_TABLE_NORMALIZE=1 python scripts/benchmark_profiles.py --refresh
```

### Automated baseline capture and quality gates

The benchmark runner can now capture a baseline artifact and compare future runs
against it using configurable quality gates.

Capture/update baseline for a suite:

```bash
python scripts/benchmark_profiles.py \
   --suite control \
   --profile medium \
   --engine baseline \
   --capture-baseline \
   --baseline-file benchmarks/baselines/control-medium.json
```

Evaluate current run against baseline (report only):

```bash
python scripts/benchmark_profiles.py \
   --suite control \
   --profile medium \
   --engine baseline \
   --baseline-file benchmarks/baselines/control-medium.json \
   --gate-config benchmarks/gates/default.json
```

Fail the process if any gate fails:

```bash
python scripts/benchmark_profiles.py \
   --suite control \
   --profile medium \
   --engine baseline \
   --baseline-file benchmarks/baselines/control-medium.json \
   --gate-config benchmarks/gates/default.json \
   --fail-on-gate
```

The default gate config validates:

1. Maximum regression for `hit_rate`.
2. Maximum regression for `mrr`.
3. Maximum latency increase ratio for `avg_latency_s`.
4. Optional absolute minima for `context_recall` and `faithfulness`
    when these metrics are present in the run output.

To reproduce the exact conditions of the table above, run with `--refresh` on a freshly
cloned repository so each profile indexes from scratch. Omit `--refresh` for fast
re-runs against existing indexes.

> **Note:** RSS delta requires `psutil` (`pip install psutil`). Without it the column shows 0.

### Experimental PageIndex-style pilot

The benchmark runner now also supports a structure-aware pilot engine that reranks the
baseline candidates using title and breadcrumb signals:

```bash
python scripts/benchmark_profiles.py --engine pageindex-pilot --profile medium
python scripts/benchmark_profiles.py --autoresearch --repeat 3 --output pilot_runs.json
```

This is benchmark-only. It does not change the MCP runtime search path.

### PageIndex benchmark suites

Use these when you want to test whether PageIndex is worth adding for specific query shapes:

```bash
# 1. Structural navigation queries
python scripts/benchmark_profiles.py --suite structural --profile medium --engine pageindex-pilot

# 2. Long-document QA queries
python scripts/benchmark_profiles.py --suite long-doc --profile medium --engine pageindex-pilot

# 3. Multi-hop retrieval queries
python scripts/benchmark_profiles.py --suite multi-hop --profile medium --engine pageindex-pilot
```

Current suite sizes:

- `structural`: 4 queries
- `long-doc`: 3 queries
- `multi-hop`: 26 queries (expanded pack)

Recommended interpretation:

1. `structural` tells you whether PageIndex improves heading-aware retrieval.
2. `long-doc` tells you whether it helps on broad questions over longer pages.
3. `multi-hop` tells you whether tree navigation helps with compound questions.

### Automatic query routing policies

The benchmark runner now supports per-query routing between baseline and `pageindex-pilot`:

```bash
# Baseline behavior (manual engine only)
python scripts/benchmark_profiles.py --suite multi-hop --profile medium --routing-policy baseline-only --engine baseline

# Adaptive routing: route multi-hop/structural intents to pageindex-pilot, keep lookup intents on baseline
python scripts/benchmark_profiles.py --suite multi-hop --profile medium --routing-policy adaptive --engine baseline

# Aggressive routing: send every query to pageindex-pilot
python scripts/benchmark_profiles.py --suite multi-hop --profile medium --routing-policy aggressive --engine baseline
```

Policy guidance:

1. Use `baseline-only` for control runs and regression tracking.
2. Use `adaptive` for realistic mixed-query evaluation.
3. Use `aggressive` as an upper-bound stress test for PageIndex-style reranking.

Observed on the medium profile during the initial pilot:

|Suite|Baseline MRR@5|PageIndex pilot MRR@5|Takeaway|
|-----|--------------|---------------------|--------|
|`structural`|1.000|1.000|No measurable gain; baseline already saturates this slice.|
|`long-doc`|1.000|1.000|No change on this small set; needs a harder long-form corpus to differentiate.|
|`multi-hop`|0.750|1.000|Best-looking slice for PageIndex-style navigation, but still small-N.|

Validation objective (completed):

Run the full control + multi-hop policy matrix over multiple repeats and make a
default-routing decision from mean and variance, not from a single run.

### Final routing matrix — 2026-04-06 (medium profile, 3 repeats each)

Commands used:

```bash
python scripts/benchmark_profiles.py --suite control --profile medium --routing-policy baseline-only --engine baseline --repeat 3 --output /tmp/pageindex_matrix/control_baseline-only.json
python scripts/benchmark_profiles.py --suite control --profile medium --routing-policy adaptive --engine baseline --repeat 3 --output /tmp/pageindex_matrix/control_adaptive.json
python scripts/benchmark_profiles.py --suite control --profile medium --routing-policy aggressive --engine baseline --repeat 3 --output /tmp/pageindex_matrix/control_aggressive.json

python scripts/benchmark_profiles.py --suite multi-hop --profile medium --routing-policy baseline-only --engine baseline --repeat 3 --output /tmp/pageindex_matrix/multi-hop_baseline-only.json
python scripts/benchmark_profiles.py --suite multi-hop --profile medium --routing-policy adaptive --engine baseline --repeat 3 --output /tmp/pageindex_matrix/multi-hop_adaptive.json
python scripts/benchmark_profiles.py --suite multi-hop --profile medium --routing-policy aggressive --engine baseline --repeat 3 --output /tmp/pageindex_matrix/multi-hop_aggressive.json
```

Aggregated results (`mean +- std`):

|Suite|Policy|HR@5|MRR@5|Avg latency (s)|Pilot share|Delta MRR vs baseline|
|-----|------|----|-----|---------------|----------|---------------------|
|`control`|`baseline-only`|1.000 +- 0.000|0.938 +- 0.000|1.532 +- 0.046|0.000|+0.000|
|`control`|`adaptive`|1.000 +- 0.000|0.938 +- 0.000|1.527 +- 0.119|0.333|+0.000|
|`control`|`aggressive`|1.000 +- 0.000|0.917 +- 0.000|1.631 +- 0.124|1.000|-0.021|
|`multi-hop`|`baseline-only`|1.000 +- 0.000|0.940 +- 0.000|1.419 +- 0.033|0.000|+0.000|
|`multi-hop`|`adaptive`|1.000 +- 0.000|0.891 +- 0.000|1.434 +- 0.027|1.000|-0.049|
|`multi-hop`|`aggressive`|1.000 +- 0.000|0.891 +- 0.000|1.392 +- 0.013|1.000|-0.049|

Decision-gate outcomes:

1. Multi-hop MRR does not improve with routing; it drops by `0.049` for both
   routed policies.
2. Control-suite MRR regresses under `aggressive` (`-0.021`).
3. `adaptive` routes all expanded multi-hop queries to the pilot path, so its
   behavior equals aggressive on this suite and keeps the same MRR regression.

Final recommendation from this matrix:

1. Keep `baseline-only` as the default policy.
2. Keep `adaptive` behind an experiment flag only while routing heuristics are
   redesigned and revalidated.
3. Do not use `aggressive` in production.

### Rollout checklist

Use this checklist when rerunning the decision matrix after heuristic changes:

1. Run control with all three routing policies:

```bash
python scripts/benchmark_profiles.py --suite control --profile medium --routing-policy baseline-only --engine baseline --repeat 3 --output control_baseline.json
python scripts/benchmark_profiles.py --suite control --profile medium --routing-policy adaptive --engine baseline --repeat 3 --output control_adaptive.json
python scripts/benchmark_profiles.py --suite control --profile medium --routing-policy aggressive --engine baseline --repeat 3 --output control_aggressive.json
```

2. Run expanded multi-hop with all three routing policies:

```bash
python scripts/benchmark_profiles.py --suite multi-hop --profile medium --routing-policy baseline-only --engine baseline --repeat 3 --output multihop_baseline.json
python scripts/benchmark_profiles.py --suite multi-hop --profile medium --routing-policy adaptive --engine baseline --repeat 3 --output multihop_adaptive.json
python scripts/benchmark_profiles.py --suite multi-hop --profile medium --routing-policy aggressive --engine baseline --repeat 3 --output multihop_aggressive.json
```

3. Promote routing only if all gates pass:

- multi-hop MRR remains consistently higher across repeats,
- control-suite MRR/HR do not regress materially,
- latency stays within the acceptable budget for your deployment target.
