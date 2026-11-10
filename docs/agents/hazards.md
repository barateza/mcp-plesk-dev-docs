# Known traps

Read this first when something behaves oddly — most surprise failures in this repo are
one of these five.

- **`tq-search` is a local editable dep** in `pyproject.toml`:
  `path = "/Users/gilsonsiqueira/tq-search"`. Won't resolve on other machines.
- **Concurrent LanceDB access** is prevented by a PID-file lock (`server/lock.py`).
  A second live instance prints the holder PID and the lock-file path to
  stderr and exits with code **75** (`EX_TEMPFAIL`), never 0 — a zero exit
  always means the server ran to completion. The lock file is
  `mcp_plesk_dev_docs.lock` in the system temp directory
  (`tempfile.gettempdir()`; `/tmp` on Linux, `%TEMP%` on Windows), *not* in
  `storage/`. Stop the holder process first; delete the file only when that PID
  is really gone (a live PID is honoured even if the holder is stuck). Stale or
  corrupt lock files are replaced automatically at startup.
- **`plesk_unified.egg-info/`** is stale from the pre-rename era. Only
  `mcp_plesk_dev_docs.egg-info/` is current. Delete the old one if it causes confusion.
- **`knowledge_base/` sources** are downloaded at runtime (git clone / zip fetch) by
  `infrastructure/sources/acquisition.py`. They are gitignored patterns in `.gitignore`
  under `storage/` but the `knowledge_base/` directory itself is committed empty.
- **`tree-sitter-language-pack`** replaced `tree-sitter-languages` (no cp313 wheels).
  The code in `infrastructure/parsers/chunking.py` imports it inside a try/except — AST
  chunking degrades gracefully if unavailable.
- **Sandboxed caches.** `uv` writes to `~/.cache/uv` and Hugging Face to
  `~/.cache/huggingface`; both are outside the workspace and fail with
  `Permission denied` in a sandboxed session. Point them inside the checkout:
  `UV_CACHE_DIR=$PWD/.scratch/uv-cache HF_HOME=$PWD/.cache/hf`. `scripts/bootstrap_index.py`
  sets `HF_HOME` itself, so only `uv` needs the prefix.
- **A fresh checkout has no index.** `knowledge_base/` and `storage/` are gitignored, so
  the quality gate has nothing to query. Run `uv run python scripts/bootstrap_index.py
  --profile light` first (~15 min on a CPU box; it prints the row count and the indexes).
- **The local GPU is a Maxwell card and needs the cu124 torch line.**
  `nvidia-smi` reports a GTX 860M (compute **5.0**, 2 GB) on driver
  `550.163.01` (CUDA 12.4). PyPI's default `torch` wheel is now a cu13x build:
  it requires driver >= 580 and ships no `sm_50` kernels, so it installs cleanly
  but `torch.cuda.is_available()` stays `False` ("driver too old", or error 304
  when the device is sandboxed). Linux therefore pins `torch<2.7` in
  `pyproject.toml`; a matching install must report `sm_50` in
  `torch.cuda.get_arch_list()` before the GPU can be used. The light profile
  needs only ~210 MiB of VRAM, and on this CPU box it cuts the control-suite
  latency from ~2.8 s to ~0.6 s. The deployed server venv is rebuilt with
  `scripts/provision_mcp_server_venv.sh` (torch cu124 installed first, then the
  package, or `--local .` to install this checkout); rebuilding it with a plain
  `uv pip install` would reinstall a newer
  torch and silently return the server to CPU. The MCP client respawns the
  server when its process is killed, so swapping `venv` -> `venv.new` and
  killing the old PID is the whole restart.
