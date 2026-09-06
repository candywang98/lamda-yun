from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_lamda_import_is_isolated() -> None:
    violations: list[str] = []
    for base in (ROOT / "packages", ROOT / "services", ROOT / "edge"):
        for path in base.rglob("*.py"):
            if "packages/lamda-driver" in path.as_posix():
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"(^|\n)\s*(?:from\s+lamda|import\s+lamda)\b", text):
                violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_deployment_does_not_expose_device_port() -> None:
    deployable_suffixes = {".yml", ".yaml", ".tf"}
    violations: list[str] = []
    for base in (ROOT / "infra", ROOT / "services"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or (
                path.suffix not in deployable_suffixes and path.name != "Caddyfile"
            ):
                continue
            if re.search(r"(?<!\d)65000(?!\d)", path.read_text(encoding="utf-8")):
                violations.append(str(path.relative_to(ROOT)))
    assert violations == []
