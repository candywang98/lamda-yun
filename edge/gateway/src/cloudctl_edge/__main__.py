from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence

from .runtime import compose_gateway
from .settings import GatewaySettings, SettingsError


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CloudCtl outbound Edge gateway")
    parser.add_argument(
        "--check",
        action="store_true",
        help="perform a network-free import/startup check and exit",
    )
    arguments = parser.parse_args(argv)
    if arguments.check:
        print(json.dumps({"status": "ok", "mode": "network-free-check"}, sort_keys=True))
        return 0
    try:
        settings = GatewaySettings.from_env()
        runtime = compose_gateway(settings)
        asyncio.run(runtime.run())
    except (SettingsError, OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
