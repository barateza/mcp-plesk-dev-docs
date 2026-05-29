import json
import logging
from pathlib import Path
from typing import Any, Dict
from datetime import datetime, timezone

logger = logging.getLogger("mcp_plesk_dev_docs")


class SourceStateRepository:
    def __init__(self, state_path: Path):
        self.state_path = state_path

    def load(self) -> Dict[str, Any]:
        """Load the source state from disk."""
        if not self.state_path.exists():
            return {"version": 1, "sources": {}}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"version": 1, "sources": {}}
            if "sources" not in data or not isinstance(data["sources"], dict):
                data["sources"] = {}
            return data
        except Exception:
            logger.warning("Failed to load source state file.", exc_info=True)
            return {"version": 1, "sources": {}}

    def save(self, state: Dict[str, Any]) -> None:
        """Save the source state to disk."""
        payload = dict(state)
        payload["version"] = 1
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
