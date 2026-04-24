import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict


class JobRegistry:
    """Thread-safe in-memory store for background indexing job state."""

    def __init__(self) -> None:
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def submit_job(self, fn: Callable[..., Any], *args: Any) -> str:
        """
        Submit a function to be run in a background thread.
        Returns the job_id (first 8 chars of a uuid4).
        """
        job_id = str(uuid.uuid4())[:8]
        with self._lock:
            self._jobs[job_id] = {
                "status": "queued",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "error": None,
            }

        def _target() -> None:
            with self._lock:
                self._jobs[job_id]["status"] = "running"

            try:
                fn(*args)
                with self._lock:
                    self._jobs[job_id]["status"] = "completed"
            except Exception as exc:
                with self._lock:
                    self._jobs[job_id]["status"] = "failed"
                    self._jobs[job_id]["error"] = str(exc)
            finally:
                with self._lock:
                    self._jobs[job_id]["finished_at"] = datetime.now(
                        timezone.utc
                    ).isoformat()

        thread = threading.Thread(target=_target, name=f"job-{job_id}", daemon=True)
        thread.start()
        return job_id

    def get_status(self, job_id: str) -> Dict[str, Any]:
        """Return the job dict or {"status": "not_found"}."""
        with self._lock:
            return self._jobs.get(job_id, {"status": "not_found"})
