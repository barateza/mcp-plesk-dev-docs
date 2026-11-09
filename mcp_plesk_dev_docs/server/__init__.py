from mcp_plesk_dev_docs.paths import resolve_base_dir
from mcp_plesk_dev_docs.settings import settings
from mcp_plesk_dev_docs.server.bootstrap import create_app
from mcp_plesk_dev_docs.server.mcp_app import create_mcp_app
from mcp_plesk_dev_docs.server.main import run_server as main

# Default instance for convenience, though main.run_server() is the preferred entrypoint
_BASE_DIR = resolve_base_dir()
_app = create_app(_BASE_DIR, settings)
mcp = create_mcp_app(_app)

__all__ = ["mcp", "main"]
