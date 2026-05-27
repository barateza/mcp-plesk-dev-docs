import logging
import json
import asyncio
from typing import Any
from fastmcp import Context
from mcp_plesk_dev_docs.server.error_handling import tool_error_boundary
from mcp_plesk_dev_docs.application.services.profile_service import list_profiles

logger = logging.getLogger("mcp_plesk_dev_docs")


class AdminTools:
    """
    Logic for administrative and health-related tools.
    """

    def __init__(
        self,
        model_runtime: Any,
        warmup_service: Any,
        health_service: Any,
        executor: Any,
    ):
        self.model_runtime = model_runtime
        self.warmup_service = warmup_service
        self.health_service = health_service
        self.executor = executor

    async def warmup_server(self, ctx: Context) -> str:
        """Preload the active profile models and table without running indexing."""
        if not self.warmup_service.begin_warmup():
            return "Warmup already running."

        try:
            # Report progress
            await ctx.report_progress(1, 4)

            loop = asyncio.get_running_loop()
            parts = await loop.run_in_executor(
                self.executor, self.warmup_service.run_warmup_sequence
            )
            self.warmup_service.finish_warmup()

            await ctx.report_progress(4, 4)

            return "\n".join(parts)
        except Exception as e:
            self.warmup_service.finish_warmup(e)
            logger.exception("Manual warmup failed.")
            return f"Warmup failed: {e}"

    async def daemon_health(self) -> str:
        """Return daemon-centric readiness status."""
        report = self.health_service.get_health_report()
        return json.dumps(report, indent=2)

    def list_model_profiles(self) -> str:
        """List built-in model profiles and show the active profile."""
        profile = self.model_runtime.get_profile()
        profiles = list_profiles()

        lines = ["=== Available Model Profiles ===\n"]
        for name, info in profiles.items():
            active_mark = "*" if name == profile.name else " "
            line = (
                f"{active_mark} {name}: embed_model={info['embed_model']}, "
                f"dim={info['embed_dim']}, reranker={info['reranker_model']} "
                f"(~{info['approx_ram_mb']} MB)"
            )
            lines.append(line)
        return "\n".join(lines)


@tool_error_boundary
async def warmup_server(ctx: Context) -> str:
    """Preload the active profile models and table without running indexing."""
    container = ctx.request_context.lifespan_context["container"]  # type: ignore[union-attr]
    tools = AdminTools(
        container.model_runtime,
        container.warmup_service,
        container.health_service,
        container.executor,
    )
    return await tools.warmup_server(ctx)


@tool_error_boundary
async def daemon_health(ctx: Context) -> str:
    """Return daemon-centric readiness status."""
    container = ctx.request_context.lifespan_context["container"]  # type: ignore[union-attr]
    tools = AdminTools(
        container.model_runtime,
        container.warmup_service,
        container.health_service,
        container.executor,
    )
    return await tools.daemon_health()


@tool_error_boundary
async def list_model_profiles(ctx: Context) -> str:
    """List built-in model profiles and show the active profile."""
    container = ctx.request_context.lifespan_context["container"]  # type: ignore[union-attr]
    tools = AdminTools(
        container.model_runtime,
        container.warmup_service,
        container.health_service,
        container.executor,
    )
    return tools.list_model_profiles()
