#!/usr/bin/env python3
"""Export the canonical Control API contract from the FastAPI application."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cloudctl_api.app import create_app
from cloudctl_api.settings import Settings


def export_openapi(destination: Path) -> None:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "destination",
        nargs="?",
        type=Path,
        default=Path("packages/api-contracts/openapi.json"),
    )
    args = parser.parse_args()
    export_openapi(args.destination)


if __name__ == "__main__":
    main()
