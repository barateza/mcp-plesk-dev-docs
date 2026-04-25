import time
from pathlib import Path

from plesk_unified.settings import settings
from plesk_unified.server.bootstrap import create_app
from plesk_unified.server.lifecycle import (
    log_server_ready,
    maybe_refresh_changed_sources,
    maybe_start_background_warmup,
)

# Root directory of the project
BASE_DIR = Path(__file__).parent.parent.parent


def run_server():
    """Main entrypoint for the MCP server."""
    start_time = time.perf_counter()

    # 1. Bootstrap (Composition Root)
    app = create_app(BASE_DIR, settings)

    # 2. Lifecycle hooks
    log_server_ready(start_time)
    maybe_refresh_changed_sources()
    maybe_start_background_warmup()

    # 3. Transport (MCP)
    from plesk_unified.legacy_server import mcp

    # In a later task, we will pass 'app' to the tool handlers.
    # For now, it's enough that we've centralized its construction.

    try:
        mcp.run()
    except Exception as e:
        app.logger.critical("Server crashed", exc_info=True)
        raise e


if __name__ == "__main__":
    run_server()
