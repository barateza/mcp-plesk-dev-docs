"""Build the light-profile index for the quality gate (run from the repo root)."""

import asyncio
import time

from mcp_plesk_dev_docs.paths import resolve_base_dir
from mcp_plesk_dev_docs.server.bootstrap import create_app
from mcp_plesk_dev_docs.settings import PleskSettings


def main() -> None:
    settings = PleskSettings(
        _env_file=None,
        plesk_model_profile="light",
        plesk_daemon_auto_warmup=False,
        plesk_auto_refresh_on_startup=False,
    )
    app = create_app(resolve_base_dir(), settings)
    started = time.time()
    report = asyncio.run(
        app.indexing_service.refresh_knowledge(category="all", reset_db=True)
    )
    print(report)
    print(f"elapsed {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
