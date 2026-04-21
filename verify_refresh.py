import logging
import os
import sys

# Add project root to sys.path
sys.path.append(os.getcwd())

# Import after sys.path update
from plesk_unified.server import refresh_knowledge  # noqa: E402

# Configure logging to see the "SKIPPED" messages
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

if __name__ == "__main__":
    print("--- Running Refresh (Should SKIP all if already indexed) ---")
    # This will use the existing LanceDB and source_state.json
    report = refresh_knowledge(target_category="all", reset_db=False)
    print("Report:")
    print(report)
