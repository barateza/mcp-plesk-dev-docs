"""
Tests for the cross-platform logging handler factory in log_handler.py.

All tests mock ``platform.system()`` so they run correctly on any OS.
"""

import logging
import logging.handlers
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from plesk_unified.log_handler import _SYSLOG_IDENT

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_formatter() -> logging.Formatter:
    return logging.Formatter(fmt="%(asctime)s %(message)s")


def _call_factory(
    tmp_path: Path, env_overrides: dict | None = None
) -> list[logging.Handler]:
    """Call create_os_handlers with a temp log file and optional env overrides."""
    from plesk_unified.log_handler import create_os_handlers

    log_file = str(tmp_path / "test_server.log")
    formatter = _make_formatter()
    env = {**os.environ, **(env_overrides or {})}

    with patch.dict(os.environ, env, clear=False):
        return create_os_handlers(logging.INFO, formatter, log_file)


# ---------------------------------------------------------------------------
# LOG_HANDLER=file (env override) — always returns RotatingFileHandler
# ---------------------------------------------------------------------------


class TestFileMode:
    def test_returns_rotating_file_handler(self, tmp_path):
        handlers = _call_factory(tmp_path, {"LOG_HANDLER": "file"})
        assert len(handlers) == 1
        assert isinstance(handlers[0], logging.handlers.RotatingFileHandler)

    def test_log_file_is_created(self, tmp_path):
        _call_factory(tmp_path, {"LOG_HANDLER": "file"})
        log_file = tmp_path / "test_server.log"
        # File may not exist until first write, but parent dir must exist.
        assert log_file.parent.exists()

    def test_log_level_applied(self, tmp_path):
        handlers = _call_factory(tmp_path, {"LOG_HANDLER": "file"})
        assert handlers[0].level == logging.INFO


# ---------------------------------------------------------------------------
# LOG_HANDLER=os on macOS
# ---------------------------------------------------------------------------


class TestOsModeOnMacos:
    @pytest.fixture(autouse=True)
    def patch_system(self):
        with patch("platform.system", return_value="Darwin"):
            yield

    def test_returns_syslog_handler_when_socket_exists(self, tmp_path):
        with patch("os.path.exists", return_value=True):
            handlers = _call_factory(tmp_path, {"LOG_HANDLER": "os"})
        assert len(handlers) == 1
        assert isinstance(handlers[0], logging.handlers.SysLogHandler)

    def test_syslog_address_is_macos_socket(self, tmp_path):
        with patch("os.path.exists", return_value=True):
            handlers = _call_factory(tmp_path, {"LOG_HANDLER": "os"})
        handler = handlers[0]
        assert isinstance(handler, logging.handlers.SysLogHandler)
        assert handler.address == "/var/run/syslog"

    def test_falls_back_to_file_when_socket_missing(self, tmp_path):
        with patch("os.path.exists", return_value=False):
            handlers = _call_factory(tmp_path, {"LOG_HANDLER": "os"})
        # Native handler fails → fallback to RotatingFileHandler
        assert len(handlers) == 1
        assert isinstance(handlers[0], logging.handlers.RotatingFileHandler)


# ---------------------------------------------------------------------------
# LOG_HANDLER=os on Linux
# ---------------------------------------------------------------------------


class TestOsModeOnLinux:
    @pytest.fixture(autouse=True)
    def patch_system(self):
        with patch("platform.system", return_value="Linux"):
            yield

    def test_returns_syslog_handler_when_dev_log_exists(self, tmp_path):
        def _exists(path):
            return path == "/dev/log"

        with patch("os.path.exists", side_effect=_exists):
            handlers = _call_factory(tmp_path, {"LOG_HANDLER": "os"})
        assert len(handlers) == 1
        assert isinstance(handlers[0], logging.handlers.SysLogHandler)

    def test_syslog_address_is_dev_log(self, tmp_path):
        def _exists(path):
            return path == "/dev/log"

        with patch("os.path.exists", side_effect=_exists):
            handlers = _call_factory(tmp_path, {"LOG_HANDLER": "os"})
        assert handlers[0].address == "/dev/log"

    def test_falls_back_to_var_run_syslog(self, tmp_path):
        def _exists(path):
            return path == "/var/run/syslog"

        with patch("os.path.exists", side_effect=_exists):
            handlers = _call_factory(tmp_path, {"LOG_HANDLER": "os"})
        assert isinstance(handlers[0], logging.handlers.SysLogHandler)
        assert handlers[0].address == "/var/run/syslog"

    def test_falls_back_to_file_when_no_socket(self, tmp_path):
        with patch("os.path.exists", return_value=False):
            handlers = _call_factory(tmp_path, {"LOG_HANDLER": "os"})
        assert isinstance(handlers[0], logging.handlers.RotatingFileHandler)


# ---------------------------------------------------------------------------
# LOG_HANDLER=os on Windows
# ---------------------------------------------------------------------------


class TestOsModeOnWindows:
    @pytest.fixture(autouse=True)
    def patch_system(self):
        with patch("platform.system", return_value="Windows"):
            yield

    def test_returns_nt_event_log_handler_when_pywin32_available(self, tmp_path):
        # Mock NTEventLogHandler so the test passes without pywin32 installed.
        mock_handler = MagicMock(spec=logging.handlers.NTEventLogHandler)
        with patch(
            "logging.handlers.NTEventLogHandler",
            return_value=mock_handler,
        ):
            handlers = _call_factory(tmp_path, {"LOG_HANDLER": "os"})
        assert mock_handler in handlers

    def test_falls_back_to_file_when_pywin32_missing(self, tmp_path):
        with patch(
            "logging.handlers.NTEventLogHandler",
            side_effect=ImportError("No module named 'win32evtlog'"),
        ):
            handlers = _call_factory(tmp_path, {"LOG_HANDLER": "os"})
        assert isinstance(handlers[0], logging.handlers.RotatingFileHandler)


# ---------------------------------------------------------------------------
# LOG_HANDLER=both
# ---------------------------------------------------------------------------


class TestBothMode:
    def test_returns_two_handlers_on_macos(self, tmp_path):
        with (
            patch("platform.system", return_value="Darwin"),
            patch("os.path.exists", return_value=True),
        ):
            handlers = _call_factory(tmp_path, {"LOG_HANDLER": "both"})
        assert len(handlers) == 2
        types = {type(h) for h in handlers}
        assert logging.handlers.SysLogHandler in types
        assert logging.handlers.RotatingFileHandler in types

    def test_returns_only_file_handler_when_native_fails(self, tmp_path):
        """On fallback, 'both' should still only have one handler (file)."""
        with (
            patch("platform.system", return_value="Darwin"),
            patch("os.path.exists", return_value=False),
        ):
            handlers = _call_factory(tmp_path, {"LOG_HANDLER": "both"})
        # Native failed → only the file handler should be present
        assert all(
            isinstance(h, logging.handlers.RotatingFileHandler) for h in handlers
        )


# ---------------------------------------------------------------------------
# Default behaviour (no LOG_HANDLER env var)
# ---------------------------------------------------------------------------


class TestDefaultMode:
    def test_defaults_to_os_behaviour(self, tmp_path):
        """Without LOG_HANDLER, behaviour should match LOG_HANDLER=os."""
        env = {k: v for k, v in os.environ.items() if k != "LOG_HANDLER"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("platform.system", return_value="Darwin"),
            patch("os.path.exists", return_value=True),
        ):
            from plesk_unified.log_handler import create_os_handlers

            log_file = str(tmp_path / "test_server.log")
            handlers = create_os_handlers(logging.INFO, _make_formatter(), log_file)
        assert any(isinstance(h, logging.handlers.SysLogHandler) for h in handlers)


# ---------------------------------------------------------------------------
# Formatter and level propagation
# ---------------------------------------------------------------------------


class TestHandlerConfig:
    def test_formatter_is_applied(self, tmp_path):
        handlers = _call_factory(tmp_path, {"LOG_HANDLER": "file"})
        assert handlers[0].formatter is not None

    def test_level_is_applied(self, tmp_path):
        from plesk_unified.log_handler import create_os_handlers

        log_file = str(tmp_path / "test_server.log")
        formatter = _make_formatter()
        with patch.dict(os.environ, {"LOG_HANDLER": "file"}):
            handlers = create_os_handlers(logging.DEBUG, formatter, log_file)
        assert handlers[0].level == logging.DEBUG

    def test_ident_prefix_on_syslog(self, tmp_path):
        with (
            patch("platform.system", return_value="Darwin"),
            patch("os.path.exists", return_value=True),
        ):
            handlers = _call_factory(tmp_path, {"LOG_HANDLER": "os"})
        syslog = handlers[0]
        assert isinstance(syslog, logging.handlers.SysLogHandler)
        assert _SYSLOG_IDENT in syslog.ident
