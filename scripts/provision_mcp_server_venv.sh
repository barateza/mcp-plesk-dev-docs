#!/usr/bin/env bash
# Provision the venv the pleskdocs MCP server is launched from.
#
# The DSH profile launches an absolute console script (not `uvx`) so a
# dependency re-resolve cannot swap torch underneath a running server. This
# script rebuilds that venv reproducibly:
#
#   1. create the venv with the requested Python,
#   2. install torch FIRST, from the CUDA 12.4 index (or the CPU index),
#   3. install the package (or the local checkout) afterwards, so the resolver
#      keeps the torch that is already present.
#
# Why the torch pin: PyPI's default torch is now a CUDA 13.x build. It needs
# driver >= 580 and ships no Maxwell (sm_50) kernels, so on a GTX 860M
# (driver 550 = CUDA 12.4) it installs cleanly but CUDA stays unavailable.
# cu124 still carries sm_50 and runs on any driver >= 525.
#
# Usage:
#   scripts/provision_mcp_server_venv.sh                 # default venv, PyPI pin
#   scripts/provision_mcp_server_venv.sh --venv /tmp/v   # build elsewhere
#   scripts/provision_mcp_server_venv.sh --local .       # install this checkout
#   scripts/provision_mcp_server_venv.sh --cpu           # CPU-only torch
#
# The target must not exist yet, so a live server can keep serving from its own
# venv while a replacement is built and swapped in.
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)

VENV="$HOME/.local/share/dsh-mcp/plesk-dev-docs/venv"
PACKAGE="mcp-plesk-dev-docs==0.7.1"
LOCAL=""
PYTHON="3.13"
TORCH_VERSION="2.6.0"
CUDA_FLAVOUR="cu124"
USE_CPU=0

usage() {
    sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --venv) VENV="$2"; shift 2 ;;
        --package) PACKAGE="$2"; shift 2 ;;
        --local) LOCAL="$2"; shift 2 ;;
        --python) PYTHON="$2"; shift 2 ;;
        --torch) TORCH_VERSION="$2"; shift 2 ;;
        --cpu) USE_CPU=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

command -v uv >/dev/null 2>&1 || { echo "uv not found on PATH" >&2; exit 1; }
if [ -e "$VENV" ]; then
    echo "refusing to overwrite existing venv: $VENV" >&2
    echo "pick another --venv and swap it in, or remove the old one first" >&2
    exit 1
fi

UV_CACHE_DIR="${UV_CACHE_DIR:-$REPO_ROOT/.scratch/uv-cache}"
export UV_CACHE_DIR
mkdir -p "$UV_CACHE_DIR"

echo "==> creating venv: $VENV (python $PYTHON)"
uv venv --python "$PYTHON" "$VENV"
PY="$VENV/bin/python"

if [ "$USE_CPU" -eq 1 ]; then
    echo "==> installing CPU torch $TORCH_VERSION"
    uv pip install --python "$PY" "torch==${TORCH_VERSION}+cpu" \
        --index-url https://download.pytorch.org/whl/cpu
else
    echo "==> installing torch ${TORCH_VERSION}+${CUDA_FLAVOUR} (first, so the resolver keeps it)"
    uv pip install --python "$PY" "torch==${TORCH_VERSION}+${CUDA_FLAVOUR}" \
        --index-url "https://download.pytorch.org/whl/${CUDA_FLAVOUR}" \
        --extra-index-url https://pypi.org/simple \
        --index-strategy unsafe-best-match
fi

if [ -n "$LOCAL" ]; then
    echo "==> installing editable checkout: $LOCAL"
    uv pip install --python "$PY" -e "$LOCAL"
else
    echo "==> installing $PACKAGE"
    uv pip install --python "$PY" "$PACKAGE"
fi

echo "==> verifying torch"
"$PY" - <<'PYEOF'
import torch

print(f"torch {torch.__version__} (built for CUDA {torch.version.cuda})")
if "+cpu" in torch.__version__:
    print("CPU-only build: CUDA is unavailable by design")
else:
    archs = torch.cuda.get_arch_list() if torch.cuda.is_available() else []
    print("arch list:", archs or "(empty: CUDA not initialisable in this shell)")
    if archs and "sm_50" not in archs:
        raise SystemExit(
            "ERROR: this wheel has no sm_50 kernels; it cannot drive a Maxwell GPU"
        )
    if not torch.cuda.is_available():
        print("note: CUDA not initialisable here (sandbox/device access), arch list checked")
PYEOF

echo "==> done: $VENV/bin/mcp-plesk-dev-docs"
echo "    restart the server to load it (kill the process; the MCP client respawns it)"
