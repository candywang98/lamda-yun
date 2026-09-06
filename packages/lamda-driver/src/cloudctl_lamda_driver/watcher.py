from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from .errors import DeviceDriverError, DriverErrorCode


class WatcherBackend(Protocol):
    def register_watcher(self, name: str, attributes: Mapping[str, object]) -> None: ...
    def remove_watcher(self, name: str) -> None: ...


@dataclass(frozen=True, slots=True)
class WatcherDefinition:
    name: str
    purpose: str
    attributes: Mapping[str, object]
    max_triggers: int = 3


class WatcherManager:
    ALLOWED_PURPOSES = frozenset({"permission_prompt", "update_prompt", "network_error"})
    PROHIBITED_WORDS = frozenset({"captcha", "verification code", "transaction", "commit"})

    def __init__(self, backend: WatcherBackend, *, app_version: str, automation_version: str):
        self._backend = backend
        self._prefix = f"{app_version}:{automation_version}"
        self._definitions: dict[str, WatcherDefinition] = {}
        self._trigger_counts: dict[str, int] = {}

    @contextmanager
    def task_scope(self, definitions: Sequence[WatcherDefinition]) -> Iterator[WatcherManager]:
        registered: list[str] = []
        try:
            for definition in definitions:
                self._validate(definition)
                qualified = f"{self._prefix}:{definition.name}"
                self._backend.register_watcher(qualified, definition.attributes)
                self._definitions[qualified] = definition
                self._trigger_counts[qualified] = 0
                registered.append(qualified)
            yield self
        finally:
            for qualified in reversed(registered):
                try:
                    self._backend.remove_watcher(qualified)
                finally:
                    self._definitions.pop(qualified, None)

    def record_trigger(self, qualified_name: str) -> int:
        definition = self._definitions.get(qualified_name)
        if definition is None:
            raise KeyError("watcher is not active")
        count = self._trigger_counts[qualified_name] + 1
        self._trigger_counts[qualified_name] = count
        if count > definition.max_triggers:
            raise DeviceDriverError(
                DriverErrorCode.CAPABILITY_DENIED,
                "watcher trigger threshold exceeded; UI state is abnormal",
                retryable=False,
            )
        return count

    @classmethod
    def _validate(cls, definition: WatcherDefinition) -> None:
        normalized = f"{definition.name} {definition.purpose} {definition.attributes}".lower()
        if definition.purpose not in cls.ALLOWED_PURPOSES:
            raise PermissionError("watcher purpose is not allowed")
        if any(word in normalized for word in cls.PROHIBITED_WORDS):
            raise PermissionError("watcher cannot handle verification or irreversible actions")
        if definition.max_triggers < 1:
            raise ValueError("watcher max_triggers must be positive")
