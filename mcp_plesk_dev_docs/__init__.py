"""Compatibility shim package.

This package exists to provide a stable, human-facing import name
`mcp_plesk_dev_docs` while leaving the existing internal package
`plesk_unified` intact. Importing submodules from
`mcp_plesk_dev_docs` will resolve into the `plesk_unified` package
directory so both import paths work.

Example:
    python -m mcp_plesk_dev_docs.server

The shim intentionally keeps runtime logic minimal and only adjusts
`__path__` so the interpreter can load subpackages from the original
`plesk_unified` package directory.
"""

from importlib import import_module as _import_module

try:
    _plesk_pkg = _import_module("plesk_unified")
    __path__ = list(getattr(_plesk_pkg, "__path__", []))
except Exception:
    # If `plesk_unified` is not importable at shim-install time, keep an
    # empty __path__ so imports only fail later when the real package
    # is unavailable. This avoids import-time crashes during packaging.
    __path__ = []

__all__ = []
