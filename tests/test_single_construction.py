"""Regression tests for issue #92: one application container per process.

Importing ``mcp_plesk_dev_docs.server`` used to build a container and a FastMCP
app at import time, and ``run_server`` then built a second one. Each container
owns thread pools, so the first one leaked on every start.
"""

import concurrent.futures
import importlib
import logging
import subprocess
import sys
import tomllib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_plesk_dev_docs.application.services.container import AppContainer
from mcp_plesk_dev_docs.server import mcp_app
from mcp_plesk_dev_docs.server.main import run_server
from mcp_plesk_dev_docs.server.mcp_app import container_lifespan, create_mcp_app

REPO_ROOT = Path(__file__).resolve().parents[1]

# ``import mcp_plesk_dev_docs.server.main as m`` binds the re-exported function
# (the package sets ``main = run_server``), so fetch the module explicitly.
server_main_module = importlib.import_module("mcp_plesk_dev_docs.server.main")


def _fake_container() -> MagicMock:
    """A container whose ``shutdown`` really releases its thread pools."""
    container = MagicMock()
    container.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    container.indexing_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def _shutdown() -> None:
        container.executor.shutdown(wait=False)
        container.indexing_executor.shutdown(wait=False)

    container.shutdown.side_effect = _shutdown
    return container


def _real_container(
    executor: concurrent.futures.ThreadPoolExecutor,
    indexing_executor: concurrent.futures.ThreadPoolExecutor,
    search_service: MagicMock,
) -> AppContainer:
    return AppContainer(
        settings=MagicMock(),
        logger=MagicMock(),
        executor=executor,
        sources=MagicMock(),
        model_runtime=MagicMock(),
        storage_runtime=MagicMock(),
        warmup_service=MagicMock(),
        health_service=MagicMock(),
        search_formatter=MagicMock(),
        toc_formatter=MagicMock(),
        lancedb_repo=MagicMock(),
        source_state_repo=MagicMock(),
        summary_cache_repo=MagicMock(),
        search_service=search_service,
        indexing_service=MagicMock(),
        processor_registry=MagicMock(),
        indexing_executor=indexing_executor,
    )


def test_run_server_builds_exactly_one_container(caplog):
    containers = []

    def fake_create_app(base_dir, settings):
        container = _fake_container()
        containers.append(container)
        return container

    transport = MagicMock()

    with (
        caplog.at_level(logging.INFO, logger="mcp_plesk_dev_docs"),
        patch.object(server_main_module, "create_app", side_effect=fake_create_app),
        patch.object(server_main_module, "maybe_refresh_changed_sources"),
        patch.object(server_main_module, "maybe_start_background_warmup"),
        patch("mcp_plesk_dev_docs.server.lock.acquire_lock"),
        patch.object(mcp_app, "create_mcp_app", return_value=transport),
    ):
        run_server()

    assert len(containers) == 1
    containers[0].shutdown.assert_called_once()
    transport.run.assert_called_once()
    assert caplog.text.count("Starting Plesk Unified MCP Server...") == 1
    assert caplog.text.count("Server module initialized in") == 1


def test_run_server_shuts_the_container_down_when_the_transport_fails():
    container = _fake_container()
    transport = MagicMock()
    transport.run.side_effect = RuntimeError("transport exploded")

    with (
        patch.object(server_main_module, "create_app", return_value=container),
        patch.object(server_main_module, "maybe_refresh_changed_sources"),
        patch.object(server_main_module, "maybe_start_background_warmup"),
        patch("mcp_plesk_dev_docs.server.lock.acquire_lock"),
        patch.object(mcp_app, "create_mcp_app", return_value=transport),
    ):
        with pytest.raises(RuntimeError, match="transport exploded"):
            run_server()

    container.shutdown.assert_called_once()
    container.logger.critical.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_releases_every_pool_owned_by_the_container():
    shared = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    indexing = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    retrieval = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    search_service = MagicMock()
    search_service.shutdown.side_effect = lambda: retrieval.shutdown(wait=False)
    container = _real_container(shared, indexing, search_service)

    # The lifespan callable ignores its server argument; FastMCP passes one.
    async with container_lifespan(container)(MagicMock()):
        pass

    for pool in (shared, indexing, retrieval):
        with pytest.raises(RuntimeError):
            pool.submit(lambda: None)


@pytest.mark.asyncio
async def test_create_mcp_app_wires_the_container_lifespan():
    container = MagicMock()

    server = create_mcp_app(container)
    # FastMCP exposes no public accessor for the constructor lifespan; its
    # low-level manager is what `mcp.run()` drives on exit.
    async with server._lifespan_manager():
        pass

    container.shutdown.assert_called_once()


def test_container_shutdown_is_idempotent():
    shared = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    indexing = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    container = _real_container(shared, indexing, MagicMock())

    container.shutdown()
    container.shutdown()

    for pool in (shared, indexing):
        with pytest.raises(RuntimeError):
            pool.submit(lambda: None)
    container.logger.info.assert_called_once_with("Shutting down AppContainer...")


_IMPORT_PROBE = """
import importlib

bootstrap = importlib.import_module("mcp_plesk_dev_docs.server.bootstrap")

created = []


def _record_create_app(*args, **kwargs):
    created.append(args)
    return object()


bootstrap.create_app = _record_create_app

server_pkg = importlib.import_module("mcp_plesk_dev_docs.server")
importlib.reload(server_pkg)

assert not created, f"importing the package built {len(created)} container(s)"
assert "mcp" not in vars(server_pkg), "the package built `mcp` at import time"
"""


def test_importing_the_server_package_builds_nothing():
    result = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_console_script_and_module_entrypoint_share_run_server():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text("utf-8"))
    target = pyproject["project"]["scripts"]["mcp-plesk-dev-docs"]
    module_name, function_name = target.split(":")
    entry = getattr(importlib.import_module(module_name), function_name)

    module_entry = importlib.import_module("mcp_plesk_dev_docs.server.__main__")

    assert entry is run_server
    assert module_entry.run_server is run_server
