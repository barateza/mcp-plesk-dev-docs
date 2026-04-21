# Retrieval Quality Benchmarks

Tracks retrieval quality and latency across the three built-in model profiles
(`light`, `medium`, `full`). Run with [`scripts/benchmark_profiles.py`](../scripts/benchmark_profiles.py).

---

## Quality Optimization Features (April 2026)

Following Phase 6, several architectural improvements were implemented to recover Hit Rate and improve Faithfulness:

1.  **Hybrid Search (Task A):** Combines dense vector retrieval (semantic) with Full-Text Search (keyword) using **Reciprocal Rank Fusion (RRF)**. This ensures that exact matches for technical terms (e.g., specific API paths or class names) are prioritized.
2.  **Parent-Header Injection (Task B):** Automatically prepends document **Title** and **Breadcrumb** path to every chunk before embedding. This makes every chunk self-describing and improves relevance for smaller models.
3.  **Sentinel Window Expansion (Task C):** Increased the default sentence window for narrative documents from 3 to **5 sentences**, providing more immediate context.
4.  **Neighborhood Retrieval (Task D):** For the top results, the system now automatically fetches the **immediate previous and next chunks** from the same file, effectively tripling the context available to the AI for grounding.

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
|`light`|BAAI/bge-small-en-v1.5|384|**80.0%**|**0.800**|0.525|**0.735**|**0.865**|1.18 s|~200 MB|
|`medium`|BAAI/bge-base-en-v1.5|768|**80.0%**|0.760|**0.635**|0.720|0.810|1.31 s|~600 MB|
|`full`|BAAI/bge-m3|1024|75.0%|0.750|0.420|0.545|0.735|3.63 s|~1 800 MB|
|`full-tq`|BAAI/bge-m3|1024|75.0%|0.750|0.365|0.515|0.720|**0.39 s**|~1 300 MB|

### Observations

1. **`light` profile provides the best retrieval/latency balance.** Surprising for this expanded suite, the `light` profile achieved the highest `MRR@5` (0.800) and `Context Precision` (0.865), while maintaining very low latency.

2. **Table-to-prose conversion significantly improves Faithfulness.** Following the implementation of structural HTML table normalization, all profiles now show healthy `faithfulness` scores, with `medium` leading at 0.635.

3. **TurboQuant efficiency remains superior.** `full-tq` delivers performance nearly identical to the full-precision `full` model with a 9x reduction in average latency, even with the added complexity of full-text search and RAGAS evaluation.

4. **Expanded query set reveals corpus-wide gaps.** All profiles hit between 75-80% HR@5, highlighting specific areas in the API and JS-SDK documentation that remain challenging for current embedding models.

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
