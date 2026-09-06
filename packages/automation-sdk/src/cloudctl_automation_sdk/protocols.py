"""The only device surface available to automation packages."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Protocol

VIEW_FRAME_CAPABILITY = "view.frame"
VIEW_LAYOUT_CAPABILITY = "view.layout"
INPUT_TAP_CAPABILITY = "input.tap"
INPUT_TEXT_CAPABILITY = "input.text"
INPUT_SWIPE_CAPABILITY = "input.swipe"
EVIDENCE_CAPTURE_CAPABILITY = "evidence.capture"
UI_SELECTORS_CAPABILITY = "ui.selectors"
APP_LIFECYCLE_CAPABILITY = "app.lifecycle"
FILE_PUSH_CAPABILITY = "file.push"
SCREENSHOT_CAPABILITY = "screenshot"
UI_DUMP_CAPABILITY = "ui.dump"

MAX_INPUT_TEXT_LENGTH = 4096
MIN_SWIPE_STEPS = 1
MAX_SWIPE_STEPS = 200
_LOCATOR_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


class CapabilityDenied(PermissionError):
    pass


class SwipeDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"


def require_capability(capabilities: frozenset[str], capability: str) -> None:
    if capability not in capabilities:
        raise CapabilityDenied(f"debug capability is not granted: {capability}")


def validate_locator_name(locator: str) -> str:
    if not _LOCATOR_NAME.fullmatch(locator):
        raise ValueError("locator must be a signed registry name")
    return locator


def validate_input_text(text: str) -> str:
    if len(text) > MAX_INPUT_TEXT_LENGTH:
        raise ValueError(f"input text must be at most {MAX_INPUT_TEXT_LENGTH} characters")
    if "\x00" in text:
        raise ValueError("input text cannot contain NUL")
    return text


def validate_swipe(
    direction: SwipeDirection | str,
    steps: int,
) -> tuple[SwipeDirection, int]:
    try:
        parsed_direction = SwipeDirection(direction)
    except ValueError as exc:
        raise ValueError("swipe direction must be UP, DOWN, LEFT or RIGHT") from exc
    if isinstance(steps, bool) or not isinstance(steps, int):
        raise ValueError("swipe steps must be an integer")
    if not MIN_SWIPE_STEPS <= steps <= MAX_SWIPE_STEPS:
        raise ValueError(f"swipe steps must be between {MIN_SWIPE_STEPS} and {MAX_SWIPE_STEPS}")
    return parsed_direction, steps


class DeviceDriver(Protocol):
    capabilities: frozenset[str]

    async def observe(self, locator: str) -> dict[str, object] | None: ...

    async def select(self, locator: str) -> None: ...

    async def tap(self, locator: str) -> None: ...

    async def input_text(self, locator: str, text: str, *, replace: bool = True) -> None: ...

    async def swipe(
        self,
        locator: str,
        direction: SwipeDirection,
        *,
        steps: int = 32,
    ) -> None: ...

    async def push_file(self, artifact_ref: str, destination: str) -> None: ...

    async def screenshot(self, label: str) -> str: ...

    async def dump_ui(self, label: str) -> str: ...

    async def app_start(self, package_name: str) -> None: ...

    async def register_watcher(
        self,
        name: str,
        locator: str,
        callback: Callable[[], Awaitable[None]],
    ) -> None: ...

    async def clear_watchers(self) -> None: ...
