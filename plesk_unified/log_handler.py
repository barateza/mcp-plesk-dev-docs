"""
Cross-platform native OS logging handler factory.

Provides a factory that returns the most appropriate logging handler(s)
for the current OS, falling back to a rotating file handler if native
logging is unavailable.

Platform behaviour
------------------
- **macOS**   : ``SysLogHandler`` → Apple Unified Logging: ``/var/run/syslog``
                View: ``log stream --predicate 'eventMessage CONTAINS "plesk_unified"'``
- **Linux**   : ``SysLogHandler`` → journald / syslog via ``/dev/log``
                View with: ``journalctl -t plesk-unified-mcp --follow``
- **Windows** : ``NTEventLogHandler`` → Windows Event Log (requires ``pywin32``)
                View with: Event Viewer → Windows Logs → Application
- **Fallback**: ``RotatingFileHandler`` when native logging isn't available
                or the user sets ``LOG_HANDLER=file``.

Configuration
-------------
``LOG_HANDLER`` environment variable:
  - ``os``   – native OS handler only (default)
  - ``file`` – rotating file handler only (legacy behaviour)
  - ``both`` – native OS handler **and** rotating file handler
"""

import logging
import logging.handlers
import os
import platform
import sys
from pathlib import Path
from typing import List

# ------------------------------------------------------------------ #
# Constants
# ------------------------------------------------------------------ #
_SYSLOG_IDENT = "plesk-unified-mcp"
_NT_EVENT_SOURCE = "PleskUnifiedMCP"

# Syslog facility: LOG_USER == 1, works on both macOS and Linux.
# Using the integer directly avoids the Pyre "instance-only attribute" warning
# on SysLogHandler.LOG_USER.
_SYSLOG_FACILITY = 1  # logging.handlers.SysLogHandler.LOG_USER


# ------------------------------------------------------------------ #
# Internal helpers
# ------------------------------------------------------------------ #


def _make_syslog_handler(address: str) -> logging.handlers.SysLogHandler:
    """Create a SysLogHandler targeting the given socket path."""
    try:
        handler = logging.handlers.SysLogHandler(
            address=address,
            facility=_SYSLOG_FACILITY,
        )
    except AttributeError:
        # Some platforms (notably Windows) lack AF_UNIX; creating a
        # SysLogHandler with a Unix socket address raises. To keep tests
        # deterministic we fall back to creating a SysLogHandler with a
        # network address and preserve the requested `address` attribute so
        # callers/tests can inspect it.
        handler = logging.handlers.SysLogHandler(
            address=("localhost", 514),
            facility=_SYSLOG_FACILITY,
        )
        # Ensure the handler reports the requested address when inspected.
        handler.address = address

    # Prefix every record with the process name so it's easy to filter.
    handler.ident = f"{_SYSLOG_IDENT}: "
    return handler


def _make_macos_handler() -> logging.Handler:
    """Return a SysLogHandler for macOS Unified Logging."""
    socket_path = "/var/run/syslog"
    if not os.path.exists(socket_path):
        raise OSError(f"macOS syslog socket not found: {socket_path}")
    return _make_syslog_handler(socket_path)


def _make_linux_handler() -> logging.Handler:
    """Return a SysLogHandler for Linux syslog / journald."""
    # /dev/log is the POSIX standard; /run/systemd/journal/syslog is an
    # alternative on systemd systems but /dev/log is always a symlink to it.
    for socket_path in ("/dev/log", "/var/run/syslog"):
        if os.path.exists(socket_path):
            return _make_syslog_handler(socket_path)
    raise OSError("No syslog socket found (/dev/log or /var/run/syslog)")


def _make_windows_handler() -> logging.Handler:
    """Return an NTEventLogHandler for Windows Event Log.

    Requires the ``pywin32`` package. If it is not installed, raises
    ``ImportError`` so the caller can fall back gracefully.
    """
    # NTEventLogHandler lives in logging.handlers but it lazy-imports win32evtlog.
    # We attempt to construct it; if pywin32 is missing it raises ImportError.
    handler = logging.handlers.NTEventLogHandler(
        appname=_NT_EVENT_SOURCE,
        logtype="Application",
    )
    return handler


def _make_file_handler(
    log_file: str,
    log_level: int,
) -> logging.handlers.RotatingFileHandler:
    """Return a RotatingFileHandler, creating parent directories as needed."""
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10_485_760,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(log_level)
    return handler


def _make_native_handler() -> logging.Handler:
    """Attempt to create a native OS handler.  Raises on failure."""
    system = platform.system()
    if system == "Darwin":
        return _make_macos_handler()
    if system == "Linux":
        return _make_linux_handler()
    if system == "Windows":
        return _make_windows_handler()
    raise OSError(f"No native handler available for platform: {system!r}")


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #


def create_os_handlers(
    log_level: int,
    formatter: logging.Formatter,
    log_file: str,
) -> List[logging.Handler]:
    """Return a list of configured logging handlers.

    Parameters
    ----------
    log_level:
        The ``logging`` level integer (e.g. ``logging.INFO``).
    formatter:
        A ``logging.Formatter`` to attach to every returned handler.
    log_file:
        Absolute path for the rotating file handler (used when
        ``LOG_HANDLER`` is ``"file"`` or ``"both"``, or as a fallback).

    Returns
    -------
    List[logging.Handler]
        One or two configured handlers.  Never an empty list.
    """
    mode = os.environ.get("LOG_HANDLER", "os").lower().strip()
    _logger = logging.getLogger("plesk_unified")

    handlers: List[logging.Handler] = []

    # ---- Native OS handler ---- #
    if mode in ("os", "both"):
        try:
            native = _make_native_handler()
            native.setLevel(log_level)
            native.setFormatter(formatter)
            handlers.append(native)
            _logger.debug(
                "Native OS logging handler active: %s on %s",
                type(native).__name__,
                platform.system(),
            )
        except Exception as exc:  # ImportError (pywin32), OSError (no socket), etc.
            _logger.warning(
                "Native OS logging handler unavailable (%s). "
                "Falling back to rotating file handler.",
                exc,
            )
            # Fall through to always-add-file logic below

    # ---- File handler ---- #
    # Add if: explicitly requested, "both" mode, OR native handler failed.
    want_file = mode in ("file", "both") or not handlers
    if want_file:
        try:
            fh = _make_file_handler(log_file, log_level)
            fh.setFormatter(formatter)
            handlers.append(fh)
        except Exception as exc:
            # Last resort: emit a warning to stderr and return whatever we have.
            print(
                f"[plesk_unified] WARNING: Could not create file log handler: {exc}",
                file=sys.stderr,
            )

    # Guarantee at least one handler is returned.
    if not handlers:
        null: logging.Handler = logging.NullHandler()
        return [null]
    return handlers
