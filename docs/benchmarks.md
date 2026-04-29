# Retrieval Quality Benchmarks

Tracks retrieval quality and latency across the three consolidated model profiles
(`local`, `pro`, `sandbox`). Run with [`scripts/benchmark_profiles.py`](../scripts/benchmark_profiles.py).

---

## Architectural Consolidation (April 2026)

Following an architectural review of the project's corpus (~2,200 chunks, ~6.8 MB total), the profile system was consolidated from 4 tiers down to 3 intent-based tiers. This move eliminated the 1.8 GB `bge-m3` OOM risk and replaced legacy models with state-of-the-art English retrieval alternatives.

1.  **`local` Profile**: Replaces `light`. Uses `snowflake-arctic-embed-s` (384d). Ideal for M1/M2/M3 MacBooks with limited unified memory.
2.  **`pro` Profile**: Replaces `medium` and `full`. Uses `Alibaba-NLP/gte-modernbert-base` (768d). The new default for high-quality English retrieval.
3.  **`sandbox` Profile**: Replaces `full-tq`. Uses `Alibaba-NLP/gte-large-en-v1.5` (1024d) + TurboQuant. Dedicated for quantization research and massive model testing.

---

## Current Baselines (April 2026)

**Hardware:** Apple M2 (MacBook Air 2022, 16GB) | NVIDIA RTX 4070 Super (CUDA)
**Query set:** 20 queries (Expanded control suite with RAGAS)

### Apple M2 (MacBook Air 2022, 16GB)

|Profile|Embed model|Dim|HR@5|MRR@5|Faith|Recall|Prec|Latency|Est. RAM|
|--------|------------|---|----|-----|-----|------|----|----------|--------|
|`local`|arctic-embed-s|384|*TBD*|*TBD*|*TBD*|*TBD*|*TBD*|~1.1s|~130 MB|
|`pro`|modernbert-base|768|*TBD*|*TBD*|*TBD*|*TBD*|*TBD*|~1.3s|~500 MB|
|`sandbox`|gte-large-v1.5|1024|*TBD*|*TBD*|*TBD*|*TBD*|*TBD*|~0.5s|~1.3 GB|

*Note: Baselines currently being re-captured following profile consolidation.*

---

## Legacy Baselines (April 2026 - Pre-Consolidation)

Legacy data for the previous 4-tier system (`light`, `medium`, `full`, `full-tq`).

### NVIDIA RTX 4070 Super (12GB VRAM)

|Profile|Embed model|Dim|HR@5|MRR@5|Faith|Recall|Prec|Latency|Est. RAM|
|--------|------------|---|----|-----|-----|------|----|----------|--------|
|`light`|bge-small-en-v1.5|384|80.0%|0.800|0.725|0.847|0.838|1.21 s|~200 MB|
|`medium`|bge-base-en-v1.5|768|80.0%|0.735|0.708|0.878|0.875|1.30 s|~600 MB|
|`full`|bge-m3|1024|75.0%|0.750|0.675|0.855|0.780|3.51 s|~1.8 GB|
|`full-tq`|bge-m3 (4-bit)|1024|75.0%|0.750|0.615|0.847|0.833|0.32 s|~1.3 GB|

---

## General Insights & Recommendations

1. **`pro` is the new sweet spot:** `ModernBERT` offers state-of-the-art English retrieval with significantly lower memory and latency overhead than `bge-m3`.
2. **`local` eliminates OOM risk:** At ~130MB, the `local` profile is safe for even the most memory-constrained environments.
3. **TurboQuant is for research:** Quantization is retained in the `sandbox` profile for research purposes but is no longer the recommended default for the 7MB Plesk vector corpus.
4. **Consistency is key:** Hybrid search and 50-candidate reranking remain the backbone of the quality pipeline across all profiles.

---

## Metrics Definitions

|Metric|Definition|
|------|----------|
|**HR@5**|Fraction of queries with a relevant chunk in the top 5 results.|
|**MRR@5**|Mean Reciprocal Rank (1/rank) of the first hit. Measures ranking quality.|
|**Faithfulness**|RAGAS: Answer grounded exclusively in context (no hallucinations).|
|**Context Recall**|RAGAS: Context contains all facts required for reference answer.|
|**Context Precision**|RAGAS: Signal-to-noise ratio in retrieved context.|
|**Avg latency**|Wall-clock time per query (ANN + Reranking).|

---

## Query Set & Index Statistics

The benchmark uses **20 hand-labeled queries** (expanded from 12) across five sources.

|Source|Files|Chunks|Category Coverage|
|------|-----|------|-----------------|
|php-stubs|124|~139|PHP API definitions|
|js-sdk|53|~80|JavaScript SDK usage|
|api|466|~1,139|REST API signatures|
|cli|81|~582|Command-line tools|
|guide|105|~281|Admin documentation|
|**Total**|829|~2,221|Full Plesk Corpus|

---

## Reproduction & CLI Reference

**Base command:** `BP="python scripts/benchmark_profiles.py"`

### Basic Execution
- **Full Refresh:** `$BP --refresh`
- **Single Profile:** `$BP --refresh --profile pro`
- **RAGAS Eval:** `$BP --ragas --ragas-model google/gemini-2.5-flash-lite`

### Baseline & Quality Gates
Capture a baseline and fail if metrics regress beyond gates:
```bash
# Capture
$BP --suite control --profile pro --engine baseline --capture-baseline --baseline-file benchmarks/baselines/control-pro.json

# Evaluate (Fail on Gate)
$BP --suite control --profile pro --engine baseline --baseline-file benchmarks/baselines/control-pro.json --gate-config benchmarks/gates/default.json --fail-on-gate
```
