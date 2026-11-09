"""
Single-instance lock for the MCP server.

Prevents multiple server processes from concurrently accessing the same LanceDB
database, which can cause corruption, crashes, or memory exhaustion.

Uses a PID file in the system temp directory with cross-platform liveness
checks via `psutil` (already a project dependency).

A second live instance refuses to start: it prints the holder PID, the lock-file
path and a recovery hint to stderr, then exits with ``EX_TEMPFAIL`` (75) so a
caller can tell a lock conflict from a successful run.
"""

import atexit
import logging
import os
import sys
import tempfile

import psutil

logger = logging.getLogger("mcp_plesk_dev_docs.lock")

LOCK_FILE = os.path.join(tempfile.gettempdir(), "mcp_plesk_dev_docs.lock")

# `os.EX_TEMPFAIL` is Unix-only; Windows must still exit with the same code.
EX_TEMPFAIL = getattr(os, "EX_TEMPFAIL", 75)


def acquire_lock() -> None:
    """Acquire the single-instance lock.

    If a lock file exists and the PID within it is still alive, the current
    process prints the holder PID, the lock-file path and a recovery hint to
    stderr, then exits with ``EX_TEMPFAIL`` (75).  Stale lock files (PID no longer
    running) are cleaned up automatically.
    """
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as fh:
                pid = int(fh.read().strip())
        except (ValueError, OSError):
            # Corrupt lock file — remove and proceed
            logger.warning("Corrupt lock file found; removing.")
            _remove_lock_file()
        else:
            if _pid_is_alive(pid):
                print(
                    "MCP server is already running (PID %d). "
                    "Refusing to start a second instance." % pid,
                    file=sys.stderr,
                )
                print(
                    "Lock file: %s\n"
                    "If that process is not running, delete the lock file and "
                    "retry (exit code %d: EX_TEMPFAIL)." % (LOCK_FILE, EX_TEMPFAIL),
                    file=sys.stderr,
                )
                sys.exit(EX_TEMPFAIL)
            else:
                logger.warning(
                    "Stale lock file found (PID %d no longer alive); removing.", pid
                )
                _remove_lock_file()

    # Write our PID
    with open(LOCK_FILE, "w") as fh:
        fh.write(str(os.getpid()))

    # Ensure cleanup on normal exit
    atexit.register(release_lock)

    logger.debug("Instance lock acquired (PID %d).", os.getpid())


def release_lock() -> None:
    """Release the instance lock by removing the lock file."""
    _remove_lock_file()
    logger.debug("Instance lock released (PID %d).", os.getpid())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _pid_is_alive(pid: int) -> bool:
    """Return True if a process with *pid* is currently running."""
    try:
        proc = psutil.Process(pid)
        # On some platforms a zombie process may exist briefly
        return proc.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def _remove_lock_file() -> None:
    """Best-effort removal of the lock file."""
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass
