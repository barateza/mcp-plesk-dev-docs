import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.getcwd())

# Import after sys.path update
from plesk_unified.settings import settings
from plesk_unified.server.bootstrap import create_app

# Configure logging to see the "SKIPPED" messages
logging.basicConfig(level=logging.INFO, stream=sys.stderr)


async def run_verify():
    print("--- Running Refresh (Should SKIP all if already indexed) ---")

    # Initialize container
    container = create_app(Path(os.getcwd()), settings)

    # This will use the existing LanceDB and source_state.json
    report = await container.indexing_service.refresh_knowledge(
        category="all", reset_db=False
    )
    print("Report:")
    print(report)


if __name__ == "__main__":
    asyncio.run(run_verify())
