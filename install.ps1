# install.ps1 — Bootstrap the mcp-plesk-dev-docs development environment (Windows)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# This script:
#   1. Installs the `uv` package manager if missing
#   2. Creates a Python virtual environment
#   3. Installs the project and its dev dependencies in editable mode

$ErrorActionPreference = "Stop"

Write-Host "=== mcp-plesk-dev-docs — Environment Setup ==="

# ── 1. Ensure `uv` is available ──────────────────────────────────────────
$uvPath = Get-Command uv -ErrorAction SilentlyContinue

if (-not $uvPath) {
    Write-Host "[*] Installing the 'uv' package manager..."
    irm https://astral.sh/uv/install.ps1 | iex

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "Machine")

    $uvPath = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvPath) {
        Write-Host "[!] uv installation succeeded but 'uv' is not on PATH."
        Write-Host "    Restart your terminal or add %USERPROFILE%\.local\bin to PATH."
        exit 1
    }
    Write-Host "[✓] uv installed."
}
else {
    Write-Host "[✓] uv is already available."
}

# ── 2. Create virtual environment ────────────────────────────────────────
Write-Host "[*] Creating virtual environment..."
uv venv
Write-Host "[✓] Virtual environment created (.venv\)."

# ── 3. Install project (editable + dev deps) ─────────────────────────────
Write-Host "[*] Installing project and dev dependencies..."
uv pip install -e ".[dev]"
Write-Host "[✓] Dependencies installed."

# ── Done ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Setup complete! ==="
Write-Host ""
Write-Host "To run the MCP server:"
Write-Host "  .venv\Scripts\Activate.ps1"
Write-Host "  mcp-plesk-dev-docs"
Write-Host ""
Write-Host "Or configure your MCP client to run:"
Write-Host "  $(Get-Location)\.venv\Scripts\mcp-plesk-dev-docs.exe"
