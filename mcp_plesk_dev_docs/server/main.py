import time
from mcp_plesk_dev_docs.paths import resolve_base_dir

from mcp_plesk_dev_docs.settings import settings
from mcp_plesk_dev_docs.server.bootstrap import create_app
from mcp_plesk_dev_docs.server.lifecycle import (
    log_server_ready,
    maybe_refresh_changed_sources,
    maybe_start_background_warmup,
)

# Root directory of the project
BASE_DIR = resolve_base_dir()


def run_server():
    """Main entrypoint for the MCP server."""
    # 0. Single-instance lock — prevent concurrent LanceDB access
    from mcp_plesk_dev_docs.server.lock import acquire_lock

    acquire_lock()

    start_time = time.perf_counter()

    # 1. Bootstrap (Composition Root). This is the only eager construction
    # point on the serving path; importing the package builds nothing.
    app = create_app(BASE_DIR, settings)

    try:
        # 2. Lifecycle hooks
        log_server_ready(start_time)
        maybe_refresh_changed_sources(app)
        maybe_start_background_warmup(app)

        # 3. Transport (MCP)
        from mcp_plesk_dev_docs.server.mcp_app import create_mcp_app

        mcp = create_mcp_app(app)

        mcp.run()
    except Exception:
        app.logger.critical("Server crashed", exc_info=True)
        raise
    finally:
        # Release every pool the container owns, whatever ended the transport:
        # normal shutdown, a crash in mcp.run(), or Ctrl-C (BaseException).
        app.shutdown()


if __name__ == "__main__":
    run_server()
