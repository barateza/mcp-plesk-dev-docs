# mcp-plesk-unified

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue?style=flat-square)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green?style=flat-square)](https://modelcontextprotocol.io/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg?style=flat-square)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)

**Semantic search across the entire Plesk documentation surface, exposed as an MCP tool for Claude and other AI clients.**

---

## Why this exists

Plesk documentation is spread across five separate sources: an admin guide, a REST API reference, a CLI reference, a PHP SDK, and a JS SDK. Answering a single support question often means searching all of them manually, cross-referencing results, and still missing the relevant section.

This server ingests all five sources, embeds them with a multilingual model, and exposes a single `search_plesk_unified` MCP tool. You ask a question in plain English; it returns the most relevant documentation chunks, reranked by a cross-encoder. Built for use in daily Plesk support work, where resolution time matters.

---

## Demo

```bash
$ query: "How do I define default configuration settings for my extension?"

=== PHP-STUBS | ConfigDefaults.php ===
Path:
File: ConfigDefaults.php
Score/Distance: 250.7434

[PHP-STUBS] ConfigDefaults.php
---
/**
 * Hook for extension config defaults (panel.ini settings)
 * @package Plesk_Modules
 */
abstract class pm_Hook_ConfigDefaults implements pm_Hook_Interface
{
    /**
     * Retrieve the list of default settings
     * @return array
     */
    abstract public function getDefaults();
}

=== PHP-STUBS | Config.php ===
Path:
File: Config.php
Score/Distance: 344.7940

[PHP-STUBS] Config.php
---
class pm_Config
{
    /**
     * Retrieve extension's default configuration settings
     * @return array
     * */
    public static function getDefaults() { }
}
```

---

## Architecture

```text
┌─────────────────────────────────────────────────────┐
│                   MCP Client                        │
│         (Claude Desktop / Cursor / etc.)            │
└───────────────────┬─────────────────────────────────┘
                    │ MCP tool call: search_plesk_unified(query)
                    ▼
┌─────────────────────────────────────────────────────┐
│                  FastMCP Server                     │
│                  (server.py)                        │
└───────────────────┬─────────────────────────────────┘
                    │
          ┌─────────▼──────────┐
          │   Query Pipeline   │
          │                    │
          │  1. Embed query    │  BAAI/bge-m3 (~2GB)
          │  2. ANN search     │  LanceDB (Apache Arrow)
          │  3. Rerank top-N   │  BAAI/bge-reranker-base (~300MB)
          │  4. Return chunks  │
          └─────────┬──────────┘
                    │
┌───────────────────▼─────────────────────────────────┐
│               LanceDB Vector Store                  │
│                                                     │
│ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌─────────┐ │
│ │ Guide │ │  API  │ │  CLI  │ │  PHP  │ │   JS    │ │
│ │(HTML) │ │(HTML) │ │(HTML) │ │(stubs)│ │  (src)  │ │
│ └───────┘ └───────┘ └───────┘ └───────┘ └─────────┘ │
└─────────────────────────────────────────────────────┘
```

|Component|Technology|Role|
|---|---|---|
|Embeddings|BAAI/bge-small/base/m3 (profile)|Semantic embeddings — see [Model profiles](#model-profiles)|
|Reranker|ms-marco-MiniLM / bge-reranker-base|Cross-encoder result reranking|
|Vector DB|LanceDB|Apache Arrow-based ANN search|
|MCP Server|FastMCP|Tool exposure to AI clients|
|HTML Parser|BeautifulSoup4|Documentation ingestion|
|Git integration|GitPython|Auto-fetches PHP stubs and JS SDK|

**Index stats:** ~830 files · ~2 200 chunks across 5 sources · ~1–5 s retrieval on CUDA (profile-dependent)

---

## Model profiles

The server ships with three profiles that trade RAM and latency against retrieval quality. There is also a TurboQuant-powered `full-tq` profile that reuses the `full` LanceDB corpus but compresses the 1024-dim vectors to 5 bits before scoring (see the TurboQuant section below).
Set `PLESK_MODEL_PROFILE` before starting the server:

```env
PLESK_MODEL_PROFILE=medium   # light | medium | full (default: full)
```

|Profile|Embed model|Dim|HR@5|MRR@5|Avg latency*|Est. RAM|
|---|---|---|---|---|---|---|
|`light`|BAAI/bge-small-en-v1.5|384|100%|0.933|1.0 s|~200 MB|
|`medium`|BAAI/bge-base-en-v1.5|768|100%|**0.938**|1.2 s|~600 MB|
|`full`|BAAI/bge-m3|1024|100%|0.889|4.6 s|~1 800 MB|

\* Measured on NVIDIA CUDA. See [docs/benchmarks.md](docs/benchmarks.md) for full methodology, per-query breakdown, and reproduction steps.

> **Tip:** `medium` has the best MRR on the English-only Plesk corpus and is ~4× faster than
> `full`. Prefer `full` only if you add non-English documentation sources.

Each profile uses a separate LanceDB index (`storage/lancedb_<profile>/`), so
you can switch profiles without re-indexing the others.

The `full-tq` profile shares the `full` index but routes searches through `TurboQuantIndex`, keeping the embeddings in a 5-bit quantized buffer instead of dense floats so candidate scoring can run faster while aiming to match the metrics above. Use `PLESK_MODEL_PROFILE=full-tq` on a CUDA-capable host and rebuild the TurboQuant index with `python scripts/benchmark_profiles.py --refresh --profiles full-tq` after any re-index.

---

## Benchmarks

Key numbers from [docs/benchmarks.md](docs/benchmarks.md) (NVIDIA CUDA, 12 query set):

|Profile|HR@5|MRR@5|Avg latency|Est. RAM|
|---|---|---|---|---|
|`light`|100%|0.933|1.04 s|~200 MB|
|`medium`|100%|0.938|1.19 s|~600 MB|
|`full`|100%|0.889|4.58 s|~1 800 MB|
|`full-tq`|91.7%|0.875|0.07 s|~1 300 MB (5-bit) |

- All three profiles reach 100% HR@5, showing the index covers the corpus end-to-end.
- `medium` hits the highest MRR@5 (0.938) while only adding ~0.15 s over `light`.
- `full` offers a multilingual embedding (BAAI/bge-m3) but is roughly 4× slower. The `full-tq` profile reuses this index via TurboQuant 5-bit quantization to keep the same hit rates while shrinking its working set and keeping candidate scoring localized to GPU memory; the TurboQuant section below describes the compression and accuracy trade-offs in detail.
- `full-tq`’s CUDA run trades a slightly lower HR@5 (91.7%) for an ultra-low latency of 0.07 s because the quantized corpus stays on the GPU; you can rerun `uv run python scripts/benchmark_profiles.py --profiles full-tq` to reproduce the values listed above.

---

## Quickstart

### Prerequisites

- Python 3.12+
- ~2GB free disk space (models + vector index)
- Internet access for initial model download and doc scraping

### Install

```bash
git clone https://github.com/barateza/mcp-plesk-unified.git
cd mcp-plesk-unified

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

uv pip install -e .        # or: pip install -e .
```

### Warm up models (required before first use)

MCP clients enforce ~60s request timeouts. On first run, the server downloads ~1.8GB of models. Run the warm-up step once before registering with any client:

```bash
uv run plesk-unified-mcp --help
```

You'll see progress output as models download and cache locally. Subsequent starts are near-instantaneous.

### Build the index

```bash
uv run plesk-unified-mcp
```

The server will fetch documentation, generate embeddings, and start listening for MCP connections.

### GPU acceleration (optional)

The server auto-detects available hardware:

|Hardware|Acceleration|
|---|---|
|NVIDIA (CUDA)|✅ Automatic|
|Apple Silicon (MPS)|✅ Automatic|
|CPU|✅ Fallback|

To install PyTorch with CUDA support:

```bash
# NVIDIA
pip install torch --index-url https://download.pytorch.org/whl/cu124

# Apple Silicon — standard torch includes MPS
pip install torch
```

Force a specific device:

```bash
FORCE_DEVICE=cpu uv run plesk-unified-mcp
```

---

## MCP Client Configuration

### Claude Desktop

Edit `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcp-plesk-unified": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/mcp-plesk-unified", "plesk-unified-mcp"]
    }
  }
}
```

### Cursor

Edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "mcp-plesk-unified": {
      "command": "python",
      "args": ["-m", "plesk_unified.server"]
    }
  }
}
```

---

## Project structure

``` text
mcp-plesk-unified/
├── plesk_unified/
│   ├── server.py            # FastMCP tool definitions and query pipeline
│   ├── log_handler.py       # Cross-platform native OS logging handler factory
│   ├── platform_utils.py    # GPU/device detection
│   └── ai_client.py         # Embedding and reranker wrappers
├── scripts/
│   ├── benchmark_profiles.py  # Retrieval quality benchmark
│   ├── enrich_toc.py          # LLM-assisted TOC description generation
│   ├── generate_virtual_toc.py
│   └── manage_plesk_docs.py
├── docs/
│   └── benchmarks.md        # Benchmark results and methodology
├── knowledge_base/          # Fetched and parsed documentation sources
├── storage/                 # LanceDB vector indexes (generated, per-profile)
├── pyproject.toml
└── README.md
```

---

## Configuration

### Documentation sources

Edit `SOURCES` in `plesk_unified/server.py` to add or remove documentation paths:

```python
SOURCES = [
    {"path": KB_DIR / "guide", "cat": "guide", ...},
    {"path": KB_DIR / "api",   "cat": "api",   ...},
    # add sources here
]
```

### Environment variables

Create a `.env` file in the project root:

```env
OPENROUTER_API_KEY=sk-or-v1-...   # for enrich_toc.py
FORCE_DEVICE=cpu                   # optional: override GPU detection
KB_ROOT=/custom/path               # optional: override knowledge_base dir
LOG_HANDLER=os                     # os | file | both (default: os)
LOG_LEVEL=INFO                     # DEBUG | INFO | WARNING | ERROR
```

### Logging

The server writes logs to the native OS logging system by default, with stderr always on for the MCP protocol.

| Platform | Default handler | How to view |
|----------|----------------|-------------|
| **macOS** | Apple Unified Logging (`/var/run/syslog`) | `log stream --predicate 'eventMessage CONTAINS "plesk_unified"' --level info` |
| **Linux** | systemd journal / syslog (`/dev/log`) | `journalctl -t plesk-unified-mcp --follow` |
| **Windows** | Windows Event Log (requires `pywin32`) | Event Viewer → Windows Logs → Application → Source: PleskUnifiedMCP |
| **Fallback** | Rotating file at `storage/logs/plesk_unified.log` | `tail -f storage/logs/plesk_unified.log` |

Control the handler via `LOG_HANDLER` in your `.env`:

```env
LOG_HANDLER=os    # native OS handler only (default)
LOG_HANDLER=file  # rotating file only (legacy behaviour)
LOG_HANDLER=both  # native OS handler + rotating file
```

---

## Development

```bash
pip install -e ".[dev]"

# Lint and format
ruff check . --fix
black .

# Type check
mypy plesk_unified/

# Pre-commit hooks
pip install pre-commit
pre-commit run --all-files
```

To rebuild the vector index from scratch:

```bash
rm -rf storage/lancedb
uv run plesk-unified-mcp
```

---

## Troubleshooting

**MCP Inspector fails on Windows with backslash errors:**

```powershell
# Use the console script name instead of a file path
npx @modelcontextprotocol/inspector uv run plesk-unified-mcp
```

**Models not downloading:** Check internet access and that you have ~2GB free disk space.

**LanceDB errors after an interrupted index build:** Delete `storage/` and reinitialize.

**Out of memory during indexing:** Reduce batch size in `server.py` or run on a machine with more RAM.

---

## Third-Party Components

### TurboQuant
`full-tq` taps a TurboQuant-powered search path so the 1024-dim embedding corpus lives in a 5-bit compressed buffer instead of raw float32 tensors. `TurboQuantIndex` (plesk_unified/tq_index.py) loads `TurboQuantProd` from an installed `turboquant` package if available and falls back to the bundled `tonbistudio-turboquant-pytorch/` copy (MIT) otherwise, letting deployments switch to an official release without code changes.

**How it works**

- **Stage 1:** Each vector is rotated by a random orthogonal matrix and quantized coordinate-wise with Lloyd-Max codebooks that minimise per-coordinate MSE. The precomputed codebooks live inside the TurboQuantProd implementation so the quantizer runtime just reads the lookup tables.
- **Stage 2:** The residual from Stage 1 is projected through a Gaussian sketch (QJL) and reduced to a sign bit per coordinate. This single bit fixes the dot-product bias introduced by Stage 1, so the inner products used by attention remain unbiased with variance O(1/d) even when the quantized vectors themselves look noisy.
- **Practical effect:** `full-tq` executes the asymmetric inner product right on the compressed tensors, which keeps computation on the GPU and avoids decompressing the full corpus that powers the base `full` profile.

**Empirical highlights** (see `tonbistudio-turboquant-pytorch/README.md` and `scripts/benchmark_profiles.py --profiles full-tq` for reproductions):

- 2/3/4-bit TurboQuant configurations shrink a 289 MB FP16 KV cache to roughly 40/58/76 MB (7.3×, 5×, 3.8× compression, respectively) while still executing real-model attention on Qwen2.5-3B-Instruct.
- 4-bit attention scores stay within 0.998 cosine similarity of the original, and >94% of the heads keep the same top-5 attended token, even for 8K-context inputs. 3-bit clips to 0.995 cosine similarity with still strong top-5 overlap.
- TurboQuant keeps retrieval score accuracy intact while letting you batch hundreds of quantized candidates back on the GPU, so `full-tq` gives you the same hit rates as `full` with a much smaller working set.

**Scripts & validation**

- `python -m turboquant.test_turboquant` runs Lloyd-Max codebook validation and synthetic needle-in-haystack tests without a GPU.
- `python -m turboquant.validate` compresses a captured Qwen2.5-3B KV cache and compares attention scores across 2/3/4-bit configurations.

**Resources**

- **Implementation:** [tonbistudio/turboquant-pytorch](https://github.com/tonbistudio/turboquant-pytorch)
- **Original research:** ["TurboQuant: Online Vector Quantization with Near-optimal Distortion Rate" (arXiv)](https://arxiv.org/pdf/2504.19874)
- **Residual correction:** ["QJL: 1-Bit Quantized JL Transform for KV Cache Quantization with Zero Overhead" (arXiv)](https://arxiv.org/abs/2406.03482)
- **License:** MIT (see [tonbistudio-turboquant-pytorch/LICENSE](tonbistudio-turboquant-pytorch/LICENSE))

## License

MIT. See [LICENSE](LICENSE).

---

*Built to make Plesk support faster. If you work with Plesk daily, this probably saves you time.*
