from pathlib import Path
from mcp_plesk_dev_docs.settings import settings
from mcp_plesk_dev_docs.server.bootstrap import create_app
from mcp_plesk_dev_docs.server.mcp_app import create_mcp_app
from mcp_plesk_dev_docs.server.main import run_server as main

# Default instance for convenience, though main.run_server() is the preferred entrypoint
_BASE_DIR = Path(__file__).parent.parent.parent
_app = create_app(_BASE_DIR, settings)
mcp = create_mcp_app(_app)

__all__ = ["mcp", "main"]
