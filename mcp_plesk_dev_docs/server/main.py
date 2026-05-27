import time
from pathlib import Path

from mcp_plesk_dev_docs.settings import settings
from mcp_plesk_dev_docs.server.bootstrap import create_app
from mcp_plesk_dev_docs.server.lifecycle import (
    log_server_ready,
    maybe_refresh_changed_sources,
    maybe_start_background_warmup,
)

# Root directory of the project
BASE_DIR = Path(__file__).parent.parent.parent


def run_server():
    """Main entrypoint for the MCP server."""
    # 0. Single-instance lock — prevent concurrent LanceDB access
    from mcp_plesk_dev_docs.server.lock import acquire_lock

    acquire_lock()

    start_time = time.perf_counter()

    # 1. Bootstrap (Composition Root)
    app = create_app(BASE_DIR, settings)

    # 2. Lifecycle hooks
    log_server_ready(start_time)
    maybe_refresh_changed_sources(app)
    maybe_start_background_warmup(app)

    # 3. Transport (MCP)
    from mcp_plesk_dev_docs.server.mcp_app import create_mcp_app

    mcp = create_mcp_app(app)

    try:
        mcp.run()
    except Exception as e:
        app.logger.critical("Server crashed", exc_info=True)
        raise e


if __name__ == "__main__":
    run_server()
