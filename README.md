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
          │  1. Embed query    │  BAAI/bge-m3 (~1.5GB)
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

| Component | Technology | Role |
| --- | --- | --- |
| Embeddings | BAAI/bge-m3 | Multilingual semantic embeddings |
| Reranker | BAAI/bge-reranker-base | Cross-encoder result reranking |
| Vector DB | LanceDB | Apache Arrow-based ANN search |
| MCP Server | FastMCP | Tool exposure to AI clients |
| HTML Parser | BeautifulSoup4 | Documentation ingestion |
| Git integration | GitPython | Auto-fetches PHP stubs and JS SDK |

**Index stats:** ~790 documents across 5 sources · ~300ms retrieval on CPU · ~2GB disk for models + index

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

| Hardware | Acceleration |
| --- | --- |
| NVIDIA (CUDA) | ✅ Automatic |
| Apple Silicon (MPS) | ✅ Automatic |
| CPU | ✅ Fallback |

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

```
mcp-plesk-unified/
├── plesk_unified/
│   ├── server.py            # FastMCP tool definitions and query pipeline
│   ├── platform_utils.py    # GPU/device detection
│   └── ai_client.py         # Embedding and reranker wrappers
├── scripts/
│   ├── enrich_toc.py        # LLM-assisted TOC description generation
│   ├── generate_virtual_toc.py
│   └── manage_plesk_docs.py
├── knowledge_base/          # Fetched and parsed documentation sources
├── storage/                 # LanceDB vector index (generated)
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

## License

MIT. See [LICENSE](LICENSE).

---

*Built to make Plesk support faster. If you work with Plesk daily, this probably saves you time.*