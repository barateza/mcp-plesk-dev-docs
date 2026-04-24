#!/bin/bash
# setup_wsl.sh - Automate quality enforcement setup for WSL

echo "🚀 Starting mcp-plesk-unified setup on WSL..."

# 1. Ensure we are in the correct directory
REPO_DIR=~/mcp-plesk-unified
if [ -d "$REPO_DIR" ]; then
    cd "$REPO_DIR"
else
    echo "❌ Error: $REPO_DIR not found."
    exit 1
fi

# 2. Sync dependencies using uv
if command -v uv >/dev/null 2>&1; then
    echo "📦 Syncing dependencies..."
    uv sync
else
    echo "❌ Error: 'uv' is not installed. Please install it first: https://docs.astral.sh/uv/"
    exit 1
fi

# 3. Initialize Beads and Hooks
if command -v bd >/dev/null 2>&1; then
    echo "⚓ Setting up Beads hooks..."
    bd prime
else
    echo "⚠️  Warning: 'bd' (beads) not found. Setting hooks path manually..."
    git config core.hooksPath .beads/hooks
fi

# 4. Install Pre-Commit
echo "🛠️  Installing pre-commit hooks..."
./.venv/bin/pre-commit install

# 5. Verify OpenRouter API Key
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "⚠️  Note: OPENROUTER_API_KEY is not set. Retrieval benchmarks will skip RAGAS metrics."
else
    echo "✅ OPENROUTER_API_KEY detected."
fi

echo "✨ WSL Setup Complete! Your 'git push' is now protected by quality gates."
