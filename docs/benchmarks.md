# Retrieval Quality Benchmarks

Tracks retrieval quality and latency across the three built-in model profiles
(`light`, `medium`, `full`). Run with [`scripts/benchmark_profiles.py`](../scripts/benchmark_profiles.py).

---

## Latest results — 2026-03-08

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

The benchmark uses 12 hand-labelled queries spread across all five sources.
Each query has a list of keyword substrings that must appear in at least one top-5 result to count as a hit.

|#|Query|Category|Relevant keywords|
|-|-----|--------|-----------------|
|1|how to define default config settings for a Plesk extension|php-stubs|ConfigDefaults, getDefaults|
|2|retrieve extension configuration values|php-stubs|pm_Config, getDefaults|
|3|hook interface for Plesk modules|php-stubs|pm_Hook_Interface, Hook|
|4|restart Plesk service from command line|cli|plesk repair, restart|
|5|create a new subscription via CLI|cli|subscription, add|
|6|list all domains via Plesk REST API|api|GET /domains, /api/v2/domains|
|7|authenticate with Plesk API using secret key|api|X-API-Key, secret_key, Authorization|
|8|add a custom button to Plesk panel|guide|button, custom_buttons, addButton|
|9|package a Plesk extension for distribution|guide|plesk ext, package, .zip|
|10|register a new page in Plesk JS SDK|js-sdk|registerPage, router|
|11|SSL certificate management|*(all)*|certificate, SSL, TLS|
|12|backup and restore Plesk|*(all)*|backup, restore|

The built-in query set lives in [`scripts/benchmark_profiles.py`](../scripts/benchmark_profiles.py#L29).
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
```

To reproduce the exact conditions of the table above, run with `--refresh` on a freshly
cloned repository so each profile indexes from scratch. Omit `--refresh` for fast
re-runs against existing indexes.

> **Note:** RSS delta requires `psutil` (`pip install psutil`). Without it the column shows 0.
