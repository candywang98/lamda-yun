#!/usr/bin/env python3
"""Explicit, synthetic-only Jev check. No device, database, or real message access."""

from __future__ import annotations

import argparse
import asyncio
import json
import stat
import sys
from dataclasses import asdict
from pathlib import Path

from pydantic_settings import DotEnvSettingsSource

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/control-api/src"))

from cloudctl_api.im_classifier import ImMessageClassifier  # noqa: E402
from cloudctl_api.settings import Settings  # noqa: E402

FIXTURES = {
    "human": ("Test buyer", "Is this item still available?"),
    "system": ("System notice", "Your order was automatically closed because payment expired."),
    "promotion": ("Daily offers", "Today's recommended listings: open the app to explore deals."),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".cloudctl-secrets/jev.env")
    parser.add_argument("--fixture", choices=FIXTURES, default="human")
    parser.add_argument("--execute-synthetic", action="store_true")
    args = parser.parse_args()
    try:
        info = args.env_file.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise ValueError("Use a regular owner-only configuration file (0600)")
        values = DotEnvSettingsSource(Settings, env_file=args.env_file)()
        settings = Settings.model_validate({**values, "im_classifier_enabled": True})
    except (OSError, ValueError):
        print(json.dumps({"status": "INVALID_PRIVATE_CONFIG"}))
        return 2
    if not args.execute_synthetic:
        print(
            json.dumps(
                {
                    "status": "DRY_RUN",
                    "model": settings.im_classifier_model,
                    "endpoint": f"{settings.im_classifier_base_url}/systemone",
                    "fixture": args.fixture,
                    "network_requests": 0,
                    "live_intake_enabled": False,
                }
            )
        )
        return 0
    title, text = FIXTURES[args.fixture]
    assessment = asyncio.run(
        ImMessageClassifier(settings).classify(platform="xianyu", title=title, text=text)
    )
    print(json.dumps({"fixture": args.fixture, **asdict(assessment)}))
    return 0 if assessment.status == "CLASSIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
