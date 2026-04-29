# TurboQuant: 5-bit Vector Quantization for Fast Retrieval

The `full-tq` profile uses `TurboQuantIndex` to maintain a 1024-dim corpus in a 5-bit compressed buffer, enabling GPU-resident scoring without decompressing the full float32 corpus.

---

## How it works

1. **Stage 1 — Lloyd-Max quantization**: Vectors are rotated by a random orthogonal matrix and coordinate-wise quantized using MSE-minimizing Lloyd-Max codebooks.
2. **Stage 2 — QJL residual correction**: A 1-bit Gaussian sketch (QJL) corrects Stage 1 residuals, keeping inner products unbiased with O(1/d) variance.
3. **Asymmetric Scoring**: Queries remain at full precision; only the corpus is compressed. Inner products are executed directly on compressed tensors.

---

## Empirical Performance

| Metric | Profile: `full-tq` | Original FP16 KV Cache (Qwen2.5) |
|--------|--------------------|---------------------------------|
| **HR@5** | 91.7% | 4-bit Cosine Sim: 0.998 |
| **MRR@5** | 0.875 | 4-bit Head Agreement: >94% |
| **Latency**| 0.07 s (CUDA) | 4-bit Ratio: 3.8× |
| **RAM** | ~1.3 GB (5-bit) | 3-bit Ratio: 5.0× |

---

## Scripts & Validation

```bash
BP="python scripts/benchmark_profiles.py"

# Validate Lloyd-Max codebooks + synthetic needle-in-haystack
python -m turboquant.test_turboquant

# Compare attention scores across 2/3/4-bit configurations
python -m turboquant.validate

# Rebuild TurboQuant index
$BP --refresh --profiles full-tq
```

---

## Technical References

| Resource | Link |
|----------|------|
| **Base Implementation** | [tonbistudio/turboquant-pytorch](https://github.com/tonbistudio/turboquant-pytorch) |
| **Lloyd-Max Research** | [TurboQuant (arXiv 2504.19874)](https://arxiv.org/pdf/2504.19874) |
| **Residual Correction**| [QJL (arXiv 2406.03482)](https://arxiv.org/abs/2406.03482) |
| **License** | MIT |
