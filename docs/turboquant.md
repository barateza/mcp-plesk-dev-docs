# TurboQuant: 4-bit Vector Quantization for Fast Retrieval

The `full-tq` profile routes searches through `TurboQuantIndex`
(`plesk_unified/tq_index.py`), keeping the 1024-dim embedding corpus in a
4-bit compressed buffer instead of raw float32 tensors.  This lets candidate
scoring run entirely in GPU memory and avoids decompressing the full corpus
that powers the base `full` profile.  The implementation lives in the
in-repo `plesk_unified.turboquant` package.

---

## How it works

### Stage 1 — Lloyd-Max vector quantization

Each vector is rotated by a random orthogonal matrix and then quantized
coordinate-wise with Lloyd-Max codebooks that minimise per-coordinate MSE.
The precomputed codebooks live inside the `TurboQuantProd` implementation;
the quantizer runtime only reads the lookup tables, so there is no
calibration overhead at query time.

### Stage 2 — QJL residual correction

The residual from Stage 1 is projected through a Gaussian sketch (QJL) and
reduced to a sign bit per coordinate.  This single bit fixes the dot-product
bias introduced by Stage 1, keeping inner products unbiased with variance
O(1/d) even when the quantized vectors look noisy.

### Asymmetric scoring

`full-tq` executes the asymmetric inner product directly on the compressed
tensors.  Queries are kept at full precision; only the indexed corpus vectors
are compressed.  This means the index scales to hundreds of thousands of
documents while staying resident in VRAM.

---

## Empirical highlights

Numbers below were collected with `scripts/benchmark_profiles.py
--profiles full-tq`.  Re-run the script at any time to reproduce them.

| Metric | Value |
|--------|-------|
| HR@5   | 91.7% |
| MRR@5  | 0.875 |
| Avg latency (CUDA) | 0.07 s |
| Est. RAM | ~1 300 MB (4-bit) |

### Compression characteristics

Measured on a 289 MB FP16 KV cache (Qwen2.5-3B-Instruct, 8K context):

| Bit width | Compressed size | Compression ratio | Cosine sim to original | Top-5 head agreement |
|-----------|----------------|-------------------|------------------------|----------------------|
| 2-bit | ~40 MB | 7.3× | — | — |
| 3-bit | ~58 MB | 5.0× | 0.995 | strong |
| 4-bit | ~76 MB | 3.8× | 0.998 | >94% |

4-bit attention scores stay within 0.998 cosine similarity of the original,
and more than 94% of heads keep the same top-5 attended token, even for
8K-context inputs.

---

## Scripts and validation

```bash
# Lloyd-Max codebook validation + synthetic needle-in-haystack (no GPU needed)
python -m turboquant.test_turboquant

# Compress a captured Qwen2.5-3B KV cache and compare attention scores
# across 2/3/4-bit configurations
python -m turboquant.validate

# Rebuild the TurboQuant index after a full re-index
python scripts/benchmark_profiles.py --refresh --profiles full-tq
```

---

## Resources

| Resource | Link |
|----------|------|
| Base implementation | [tonbistudio/turboquant-pytorch](https://github.com/tonbistudio/turboquant-pytorch) |
| Original research | ["TurboQuant: Online Vector Quantization with Near-optimal Distortion Rate" (arXiv 2504.19874)](https://arxiv.org/pdf/2504.19874) |
| Residual correction | ["QJL: 1-Bit Quantized JL Transform for KV Cache Quantization" (arXiv 2406.03482)](https://arxiv.org/abs/2406.03482) |
| License | MIT (base implementation: [tonbistudio/turboquant-pytorch](https://github.com/tonbistudio/turboquant-pytorch)) |
