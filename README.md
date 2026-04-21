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

Query sent to the MCP tool:

```
search_plesk_unified("How do I define default configuration settings for my extension?")
```

Results returned:

```text
=== GUIDE | Custom Settings ===
Path: Plesk Features Available for Extensions > Retrieve Data from Plesk > Custom Settings
File: 77178.htm
URL: https://docs.plesk.com/en-US/obsidian/extensions-guide/77178.htm
Relevance: 0.9341

[GUIDE] Custom Settings
---
## Custom Settings

Plesk SDK API provides the ability to customize the behavior of
extensions editing the `panel.ini` configuration file.

Storing the default settings is implemented via a hook class at
`plib/hooks/ConfigDefaults.php` that extends `pm_Hook_ConfigDefaults`:

    class Modules_CustomConfig_ConfigDefaults extends pm_Hook_ConfigDefaults
    {
        public function getDefaults()
        {
            return [
                'homepage' => 'https://www.plesk.com/',
                'timeout'  => 60,
            ];
        }
    }

=== PHP-STUBS | ConfigDefaults.php ===
Path:
File: ConfigDefaults.php
Relevance: 0.8712

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
```

---

## Architecture

```mermaid
flowchart TD
    Client["MCP Client\n(Claude Desktop / Cursor / etc.)"]

    Client -->|"search_plesk_unified(query)"| Server

    subgraph Server["FastMCP Server · plesk_unified/server.py"]
        direction TB
        E["1 · Embed query\n(profile-selected model)"]
        S["2 · ANN search\nLanceDB (Apache Arrow)"]
        R["3 · Rerank top-N\n(profile-selected reranker)"]
        O["4 · Return top-5 results"]
        E --> S --> R --> O
    end

    subgraph Store["LanceDB Vector Store"]
        direction LR
        G["Guide\nHTML"]
        A["API\nHTML"]
        C["CLI\nHTML"]
        P["PHP Stubs\nPHP"]
        J["JS SDK\nJS"]
    end

    S <--> Store
```

See [Model profiles](#model-profiles) for the available embed and reranker model options.

|Component|Technology|Role|
|---|---|---|
|Embeddings|BAAI/bge-small · bge-base · bge-m3 (profile)|Semantic embeddings — see [Model profiles](#model-profiles)|
|Reranker|ms-marco-MiniLM / bge-reranker-base (profile)|Cross-encoder result reranking (always applied)|
|Vector DB|LanceDB|Apache Arrow-based ANN search|
|MCP Server|FastMCP|Tool exposure to AI clients (`plesk_unified/server.py`)|
|HTML Parser|BeautifulSoup4|Documentation ingestion|
|Git integration|Git (stdlib subprocess)|Auto-fetches PHP stubs and JS SDK|

**Index stats:** ~830 files · ~2 200 chunks across 5 sources · ~1–5 s retrieval on CUDA (profile-dependent)

---

## Model profiles

The server ships with three profiles that trade RAM and latency against retrieval quality. There is also a TurboQuant-powered `full-tq` profile that reuses the `full` LanceDB corpus but compresses the 1024-dim vectors to 5 bits before scoring (see the TurboQuant section below).
Set `PLESK_MODEL_PROFILE` before starting the server:

```env
PLESK_MODEL_PROFILE=full-tq   # light | medium | full | full-tq (default: full-tq)
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

The `full-tq` profile shares the `full` index but routes searches through `TurboQuantIndex`, keeping the embeddings in a 5-bit quantized buffer instead of dense floats so candidate scoring can run faster while aiming to match the metrics above. Use `PLESK_MODEL_PROFILE=full-tq` on a CUDA-capable host and rebuild the TurboQuant index with `python scripts/benchmark_profiles.py --refresh --profiles full-tq` after any re-index. See [docs/turboquant.md](docs/turboquant.md) for full technical details.

---

## Benchmarks

Key numbers from [docs/benchmarks.md](docs/benchmarks.md) (NVIDIA CUDA, 12 query set):

<details>
<summary>Show full benchmark table</summary>

|Profile|HR@5|MRR@5|Avg latency|Est. RAM|
|---|---|---|---|---|
|`light`|100%|0.933|1.04 s|~200 MB|
|`medium`|100%|0.938|1.19 s|~600 MB|
|`full`|100%|0.889|4.58 s|~1 800 MB|
|`full-tq`|91.7%|0.875|0.07 s|~1 300 MB (5-bit) |

- All three profiles reach 100% HR@5, showing the index covers the corpus end-to-end.
- `medium` hits the highest MRR@5 (0.938) while only adding ~0.15 s over `light`.
- `full` offers a multilingual embedding (BAAI/bge-m3) but is roughly 4× slower. The `full-tq` profile reuses this index via TurboQuant 5-bit quantization to keep the same hit rates while shrinking its working set and keeping candidate scoring localized to GPU memory; see [docs/turboquant.md](docs/turboquant.md) for compression and accuracy trade-offs.
- `full-tq`’s CUDA run trades a slightly lower HR@5 (91.7%) for an ultra-low latency of 0.07 s because the quantized corpus stays on the GPU; reproduce with `uv run python scripts/benchmark_profiles.py --profiles full-tq`.

</details>

---

## Quickstart

### Prerequisites

- Python 3.12+
- [`uv`](https://astral.sh/uv) (recommended package manager — `pip` works too)
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

For an already running MCP server, call the `warmup_server` tool once to
preload the embedding model, reranker, and database table without
re-indexing. Use `list_model_profiles` to inspect the available profiles
and confirm which one is active.

### Running the server

#### Standard mode

```bash
uv run plesk-unified-mcp
```

The server fetches documentation, generates embeddings on first run, and starts listening for MCP connections.

#### Daemon / background mode

Set `PLESK_DAEMON_AUTO_WARMUP=true` to keep startup responsive while models
and DB state load in a background thread:

```bash
PLESK_DAEMON_AUTO_WARMUP=true uv run plesk-unified-mcp
```

Then verify readiness from your MCP client:

- `daemon_health` → `"warmup_state": "ready"`
- `daemon_health` → `"table_ready": true`

Use `daemon_health` at any time to check warmup state (`idle`, `running`,
`ready`, or `failed`) plus table and TurboQuant artifact status. Call
`warmup_server` manually for deterministic preloading without indexing.

#### GPU acceleration (optional)

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
│   ├── server.py              # FastMCP tool definitions and query pipeline
│   ├── ai_client.py           # Embedding and reranker model wrappers
│   ├── model_config.py        # Model profile definitions (light/medium/full/full-tq)
│   ├── chunking.py            # Document chunking and LanceDB persistence
│   ├── html_utils.py          # HTML parsing with BeautifulSoup4 + markdownify
│   ├── io_utils.py            # Source fetching (Git clone, ZIP download)
│   ├── platform_utils.py      # GPU/device detection
│   ├── log_handler.py         # Cross-platform native OS logging handler factory
│   ├── tq_index.py            # TurboQuant search index
│   ├── benchmark_engines.py   # Benchmarking engine implementations
│   ├── benchmark_suites.py    # Benchmark suite loader
│   └── turboquant/            # In-repo TurboQuant quantization package
├── scripts/
│   ├── benchmark_profiles.py  # Retrieval quality benchmark
│   ├── enrich_toc.py          # LLM-assisted TOC description generation
│   ├── generate_virtual_toc.py
│   └── manage_plesk_docs.py
├── benchmarks/
│   ├── suites/                # JSON query definitions (control, multi-hop, etc.)
│   ├── baselines/             # Golden artifacts for regression testing
│   └── gates/                 # Quality gate threshold configurations
├── tests/                     # Pytest test suite
├── docs/
│   ├── benchmarks.md          # Benchmark results and methodology
│   └── turboquant.md          # TurboQuant technical breakdown and validation
├── knowledge_base/            # Fetched and parsed documentation sources
├── storage/                   # LanceDB vector indexes (generated, per-profile)
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

Copy the bundled template and fill in your values:

```bash
cp .env.example .env
```

Key variables:

```env
OPENROUTER_API_KEY=sk-or-v1-...   # for RAGAS and table normalization
PLESK_HTML_LLM_TABLE_NORMALIZE=1   # optional: enable LLM-assisted complex table parsing
FORCE_DEVICE=cpu                   # optional: override GPU detection
PLESK_DAEMON_AUTO_WARMUP=true      # optional: daemon-only background warmup
PLESK_MIN_RELEVANCE_THRESHOLD=0.55 # optional: profile-aware fallback gate
PLESK_RERANK_CANDIDATES=25         # optional: candidate pool size before reranking
KB_ROOT=/custom/path               # optional: override knowledge_base dir
LOG_HANDLER=os                     # os | file | both (default: os)
LOG_LEVEL=INFO                     # DEBUG | INFO | WARNING | ERROR
```

See `.env.example` for the full list of options with inline documentation.

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

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full development workflow — linting, type-checking, tests, and pre-commit hooks.

To rebuild the vector index from scratch:

```bash
rm -rf storage/lancedb
uv run plesk-unified-mcp
```

To run retrieval quality benchmarks:

```bash
# Standard run
uv run python scripts/benchmark_profiles.py --profile medium

# With RAGAS evaluation
uv run python scripts/benchmark_profiles.py --profile medium --ragas

# With LLM-assisted table normalization (during index refresh)
PLESK_HTML_LLM_TABLE_NORMALIZE=1 uv run python scripts/benchmark_profiles.py --refresh --profiles medium
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

**Out of memory during indexing:** Reduce batch size in `plesk_unified/server.py` or run on a machine with more RAM.

### Cache management

To free disk space, you can delete the following generated directories:

| What | Path | Notes |
|------|------|-------|
| Vector indexes | `storage/lancedb*/` | Rebuilt automatically on next start |
| TurboQuant index | `storage/turboquant/` | Rebuilt with `--refresh --profiles full-tq` |
| HuggingFace models | `~/.cache/huggingface/` | Re-downloaded (~1.8 GB) on next start |
| All generated data | `storage/` | Nuclear option — full rebuild on next start |

```bash
# Remove all vector indexes (triggers full re-index on next start)
rm -rf storage/lancedb*/

# Remove only the TurboQuant quantized index
rm -rf storage/turboquant/

# Remove cached HuggingFace model weights (~1.8 GB)
rm -rf ~/.cache/huggingface/hub/models--BAAI*
```

---

## Third-Party Components

### TurboQuant

The `full-tq` profile uses in-repo TurboQuant (`plesk_unified/turboquant/`) to compress
1024-dim embeddings to 5-bit vectors via Lloyd-Max codebooks and a QJL residual-correction
sketch. This keeps the indexed corpus resident in GPU memory for fast asymmetric inner-product
scoring while matching the retrieval quality of the uncompressed `full` profile.
See **[docs/turboquant.md](docs/turboquant.md)** for the full technical breakdown, empirical
validation numbers, and reproduction steps.

## License

MIT. See [LICENSE](LICENSE).

---

*Built to make Plesk support faster. If you work with Plesk daily, this probably saves you time.*
