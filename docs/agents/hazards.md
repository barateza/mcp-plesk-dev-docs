# Known traps

Read this first when something behaves oddly — most surprise failures in this repo are
one of these five.

- **`tq-search` is a local editable dep** in `pyproject.toml`:
  `path = "/Users/gilsonsiqueira/tq-search"`. Won't resolve on other machines.
- **Concurrent LanceDB access** is prevented by a PID-file lock (`server/lock.py`).
  If the server won't start, check for a stale lock file in `storage/`.
- **`plesk_unified.egg-info/`** is stale from the pre-rename era. Only
  `mcp_plesk_dev_docs.egg-info/` is current. Delete the old one if it causes confusion.
- **`knowledge_base/` sources** are downloaded at runtime (git clone / zip fetch) by
  `infrastructure/sources/acquisition.py`. They are gitignored patterns in `.gitignore`
  under `storage/` but the `knowledge_base/` directory itself is committed empty.
- **`tree-sitter-language-pack`** replaced `tree-sitter-languages` (no cp313 wheels).
  The code in `infrastructure/parsers/chunking.py` imports it inside a try/except — AST
  chunking degrades gracefully if unavailable.
