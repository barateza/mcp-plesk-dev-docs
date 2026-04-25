import logging
from typing import Any, Dict
from datetime import datetime, timezone

logger = logging.getLogger("plesk_unified")


class HealthService:
    def __init__(
        self,
        settings: Any,
        model_runtime: Any,
        storage_runtime: Any,
        warmup_service: Any,
    ):
        self.settings = settings
        self.model_runtime = model_runtime
        self.storage_runtime = storage_runtime
        self.warmup_service = warmup_service
        self.start_time = datetime.now(timezone.utc)

    def get_health_report(self) -> Dict[str, Any]:
        """Generate a comprehensive health report of the server and its dependencies."""
        table_ok, table_err = self.storage_runtime.table_health()
        profile = self.model_runtime.get_profile()

        return {
            "status": "ok" if table_ok else "degraded",
            "uptime_seconds": (
                datetime.now(timezone.utc) - self.start_time
            ).total_seconds(),
            "profile": profile.name,
            "device": self.model_runtime.detect_device(),
            "warmup": {
                "state": self.warmup_service.state,
                "error": self.warmup_service.error,
            },
            "table": {
                "ready": table_ok,
                "error": table_err,
                "path": str(self.storage_runtime.db_path),
            },
        }
