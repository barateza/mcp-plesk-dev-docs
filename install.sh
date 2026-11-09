#!/usr/bin/env bash
# install.sh — Bootstrap the mcp-plesk-dev-docs development environment
#
# Usage:
#   chmod +x install.sh && ./install.sh
#
# This script:
#   1. Installs the `uv` package manager if missing
#   2. Creates a Python virtual environment
#   3. Installs the project and its dev dependencies in editable mode

set -euo pipefail

echo "=== mcp-plesk-dev-docs — Environment Setup ==="

# ── 1. Ensure `uv` is available ──────────────────────────────────────────
if ! command -v uv &> /dev/null; then
    echo "[!] 'uv' is not installed."
    echo "    Install it first, then re-run this script:"
    echo "      https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi
echo "[✓] uv is available."

# ── 2. Create virtual environment ────────────────────────────────────────
echo "[*] Creating virtual environment..."
uv venv
echo "[✓] Virtual environment created (.venv/)."

# ── 3. Install project (editable + dev deps) ─────────────────────────────
echo "[*] Installing project and dev dependencies..."
uv pip install -e ".[dev]"
echo "[✓] Dependencies installed."

# ── Done ─────────────────────────────────────────────────────────────────
echo ""
echo "=== Setup complete! ==="
echo ""
echo "To run the MCP server:"
echo "  source .venv/bin/activate"
echo "  mcp-plesk-dev-docs"
echo ""
echo "Or configure your MCP client to run:"
echo "  $(pwd)/.venv/bin/mcp-plesk-dev-docs"
