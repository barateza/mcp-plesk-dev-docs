import functools
import logging
from typing import Any, Callable, TypeVar
import inspect

logger = logging.getLogger("plesk_unified")

# Try to import LanceDB exceptions for precise matching
try:
    import lancedb.exceptions as lancedb_exc

    LANCEDB_EXCEPTIONS_AVAILABLE = True
except ImportError:
    LANCEDB_EXCEPTIONS_AVAILABLE = False

F = TypeVar("F", bound=Callable[..., Any])


def _classify_error(exc: Exception) -> str:
    """Map known exception types to user-friendly guidance strings."""
    exc_msg = str(exc)
    exc_msg_lower = exc_msg.lower()
    exc_type_name = type(exc).__name__

    # 1. LanceDB TableNotFoundError
    if (
        LANCEDB_EXCEPTIONS_AVAILABLE
        and hasattr(lancedb_exc, "TableNotFoundError")
        and isinstance(exc, lancedb_exc.TableNotFoundError)
    ):
        return (
            "[ERROR] Knowledge base not indexed. "
            "Call refresh_knowledge(reset_db=True) first."
        )
    if exc_type_name == "TableNotFoundError":
        return (
            "[ERROR] Knowledge base not indexed. "
            "Call refresh_knowledge(reset_db=True) first."
        )

    # Handle ValueError that some versions of LanceDB raise when a table is missing
    if isinstance(exc, ValueError) and "was not found" in exc_msg_lower:
        return (
            "[ERROR] Knowledge base not indexed. "
            "Call refresh_knowledge(reset_db=True) first."
        )

    # 2. LanceDB connection error
    # Connection errors in LanceDB can manifest as various exceptions
    # depending on the storage backend
    if (
        "lancedb" in exc_msg_lower
        or "database" in exc_msg_lower
        or "connection" in exc_msg_lower
    ):
        if (
            "not found" not in exc_msg_lower
        ):  # Avoid collision with TableNotFoundError if not caught above
            return (
                "[ERROR] Database unavailable. Check storage/lancedb/ path. "
                "Call daemon_health for details."
            )

    # 3. RuntimeError containing "model"
    if isinstance(exc, RuntimeError) and "model" in exc_msg_lower:
        return "[ERROR] Embedding model not loaded. Call warmup_server first."

    # 4. PermissionError
    if isinstance(exc, PermissionError):
        return "[ERROR] Path traversal detected. Operation rejected."

    # --- NEW FIX: Classify ValueError from _validate_category ---
    if isinstance(exc, ValueError) and "invalid category" in exc_msg_lower:
        # Re-raise as a more specific error message, keeping context
        return f"[ERROR] Invalid argument: {exc_msg}. Check allowed category values."

    # 5. Generic fallback
    return (
        "[ERROR] Unexpected server error. "
        "Call daemon_health to check server state, then retry."
    )


def tool_error_boundary(fn: F) -> F:
    """
    Decorator for MCP tools to catch exceptions and return sanitized guidance.

    Logs the full traceback to the module logger and returns a string starting
    with [ERROR] that provides actionable instructions for the LLM.
    """
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> str:
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                logger.error("Tool %s failed", fn.__name__, exc_info=True)
                return _classify_error(exc)

        return async_wrapper  # type: ignore
    else:

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> str:
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                logger.error("Tool %s failed", fn.__name__, exc_info=True)
                return _classify_error(exc)

        return sync_wrapper  # type: ignore
