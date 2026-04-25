import logging
from typing import Any

logger = logging.getLogger("plesk_unified")


class AdminTools:
    def __init__(self, model_runtime: Any, warmup_service: Any, health_service: Any):
        self.model_runtime = model_runtime
        self.warmup_service = warmup_service
        self.health_service = health_service

    async def warmup_server(self, ctx: Any = None) -> str:
        """Preload the active profile models and table without running indexing."""
        if not self.warmup_service.begin_warmup():
            return "Warmup already running."

        try:
            # Report progress
            if ctx and hasattr(ctx, "report_progress"):
                await ctx.report_progress(1, 4)

            parts = self.warmup_service.run_warmup_sequence()
            self.warmup_service.finish_warmup()

            if ctx and hasattr(ctx, "report_progress"):
                await ctx.report_progress(4, 4)

            return "\n".join(parts)
        except Exception as e:
            self.warmup_service.finish_warmup(e)
            logger.exception("Manual warmup failed.")
            return f"Warmup failed: {e}"

    async def daemon_health(self) -> str:
        """Return daemon-centric readiness status."""
        import json

        report = self.health_service.get_health_report()
        return json.dumps(report, indent=2)

    def list_model_profiles(self) -> str:
        """List built-in model profiles and show the active profile."""
        from plesk_unified.model_config import list_profiles

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
