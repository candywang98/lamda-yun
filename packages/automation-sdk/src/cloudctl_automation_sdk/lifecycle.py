"""Deterministic automation lifecycle sequencing at the runner boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from .protocols import DeviceDriver


@dataclass(frozen=True, slots=True)
class AutomationContext:
    tenant_id: str
    target_id: str
    snapshot_sha256: str
    commit_intent_id: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)


class ReconcileResult(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class AutomationPackage(Protocol):
    async def validate(self, context: AutomationContext) -> None: ...

    async def preflight(self, driver: DeviceDriver, context: AutomationContext) -> None: ...

    async def prepare(self, driver: DeviceDriver, context: AutomationContext) -> None: ...

    async def before_commit(self, driver: DeviceDriver, context: AutomationContext) -> None: ...

    async def commit_once(self, driver: DeviceDriver, context: AutomationContext) -> None: ...

    async def reconcile(
        self, driver: DeviceDriver, context: AutomationContext
    ) -> ReconcileResult: ...

    async def cleanup(self, driver: DeviceDriver, context: AutomationContext) -> None: ...


class LifecycleRunner:
    def __init__(self, package: AutomationPackage, driver: DeviceDriver) -> None:
        self._package = package
        self._driver = driver
        self._consumed_commit_intents: set[str] = set()

    async def prepare(self, context: AutomationContext) -> None:
        await self._package.validate(context)
        await self._package.preflight(self._driver, context)
        await self._package.prepare(self._driver, context)
        await self._package.before_commit(self._driver, context)

    async def commit_and_reconcile(self, context: AutomationContext) -> ReconcileResult:
        if context.commit_intent_id is None:
            raise ValueError("commit_once requires a durable commit_intent_id")
        if context.commit_intent_id in self._consumed_commit_intents:
            raise RuntimeError("commit_once has already been attempted for this commit_intent_id")
        # Consume before the call. A lost response is UNKNOWN and must be reconciled, never retried.
        self._consumed_commit_intents.add(context.commit_intent_id)
        await self._package.commit_once(self._driver, context)
        return await self._package.reconcile(self._driver, context)

    async def cleanup(self, context: AutomationContext) -> None:
        try:
            await self._package.cleanup(self._driver, context)
        finally:
            await self._driver.clear_watchers()

    async def run(self, context: AutomationContext) -> ReconcileResult:
        try:
            await self.prepare(context)
            return await self.commit_and_reconcile(context)
        finally:
            await self.cleanup(context)
