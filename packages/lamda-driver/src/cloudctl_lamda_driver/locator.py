from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from .errors import DeviceDriverError, DriverErrorCode, map_exception
from .protocols import Element, Locator, LocatorCandidate


class SelectorBackend(Protocol):
    def select(self, attributes: Mapping[str, object], timeout_seconds: float) -> Element: ...


class LocatorResolver:
    STRATEGIES = (
        "resource_id",
        "text",
        "hierarchy",
        "ocr",
        "image",
        "coordinates",
    )

    def __init__(self, on_degraded: Callable[[str, str], None] | None = None):
        self._on_degraded = on_degraded or (lambda _name, _strategy: None)

    def resolve(self, backend: SelectorBackend, locator: Locator) -> Element:
        candidates = (locator.primary, *locator.fallbacks)
        failures: list[DeviceDriverError] = []
        for index, candidate in enumerate(candidates):
            self._validate_candidate(candidate)
            try:
                element = backend.select(candidate.attributes, locator.timeout_seconds)
                self._assert(element, locator.assertions)
            except Exception as exc:
                failures.append(map_exception(exc))
                continue
            if index > 0 or self.STRATEGIES.index(candidate.strategy) > 1:
                self._on_degraded(locator.name, candidate.strategy)
            return element
        detail = "; ".join(error.code for error in failures) or "no locator candidates"
        raise DeviceDriverError(
            DriverErrorCode.ELEMENT_NOT_FOUND,
            f"locator {locator.name!r} failed: {detail}",
            retryable=False,
        )

    @classmethod
    def _validate_candidate(cls, candidate: LocatorCandidate) -> None:
        if candidate.strategy not in cls.STRATEGIES:
            raise ValueError(f"unsupported locator strategy: {candidate.strategy}")
        if not candidate.attributes:
            raise ValueError("locator candidate attributes cannot be empty")
        if candidate.strategy == "coordinates":
            required = {"x", "y", "width", "height", "orientation"}
            if not required <= candidate.attributes.keys():
                raise ValueError(
                    "coordinate locator requires coordinates, resolution and orientation"
                )

    @staticmethod
    def _assert(element: Element, assertions: tuple[str, ...]) -> None:
        for assertion in assertions:
            if assertion == "exists" and not element.exists():
                raise LookupError("element does not exist")
            if assertion == "text_nonempty" and not element.text().strip():
                raise LookupError("element text is empty")
            if assertion not in {"exists", "text_nonempty"}:
                raise ValueError(f"unsupported locator assertion: {assertion}")
