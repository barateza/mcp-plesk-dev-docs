"""Tests for the single-instance PID-file lock (``server/lock.py``)."""

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from mcp_plesk_dev_docs.server import lock


@pytest.fixture
def lock_file(tmp_path, monkeypatch):
    """Point the module-level lock path at a per-test file."""
    path = tmp_path / "mcp_plesk_dev_docs.lock"
    monkeypatch.setattr(lock, "LOCK_FILE", str(path))
    # Successful acquisitions register `release_lock` with atexit. After the
    # fixture tears down, `LOCK_FILE` points back at the real temp path, so a
    # leftover hook would delete a live server's lock file at pytest exit.
    monkeypatch.setattr(
        lock, "atexit", SimpleNamespace(register=lambda *args, **kwargs: None)
    )
    return path


def _dead_pid() -> int:
    """Return a PID that is guaranteed not to be running (a reaped child)."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def test_second_instance_exits_with_tempfail(lock_file, capsys):
    lock_file.write_text(str(os.getpid()))

    with pytest.raises(SystemExit) as excinfo:
        lock.acquire_lock()

    assert excinfo.value.code == 75
    assert excinfo.value.code == lock.EX_TEMPFAIL

    stderr = capsys.readouterr().err
    assert str(os.getpid()) in stderr
    assert str(lock_file) in stderr
    assert "delete the lock file" in stderr


def test_second_instance_leaves_the_holder_lock_file_in_place(lock_file, capsys):
    lock_file.write_text(str(os.getpid()))

    with pytest.raises(SystemExit):
        lock.acquire_lock()

    assert lock_file.read_text() == str(os.getpid())


def test_stale_lock_is_replaced(lock_file):
    lock_file.write_text(str(_dead_pid()))

    lock.acquire_lock()

    assert lock_file.read_text() == str(os.getpid())


def test_corrupt_lock_is_replaced(lock_file):
    lock_file.write_text("not-a-pid")

    lock.acquire_lock()

    assert lock_file.read_text() == str(os.getpid())
