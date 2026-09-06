from __future__ import annotations

import uuid

import pytest
from cloudctl_automation_sdk import AutomationContext, LifecycleRunner, ReconcileResult
from cloudctl_domain import (
    ConflictError,
    ForbiddenError,
    Permission,
    PublishState,
    Role,
    assert_publish_transition,
    canonical_hash,
    new_uuid7,
    require_permissions,
)


def test_uuid7_is_time_ordered_and_has_rfc_variant() -> None:
    first = new_uuid7(timestamp_ms=1000)
    second = new_uuid7(timestamp_ms=1001)
    assert first < second
    assert first.version == 7
    assert first.variant == uuid.RFC_4122


def test_canonical_hash_is_key_order_independent() -> None:
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})


def test_rbac_and_publish_state_machine_reject_unsafe_actions() -> None:
    require_permissions([Role.PUBLISHER], Permission.PUBLISH_CREATE)
    with pytest.raises(ForbiddenError):
        require_permissions([Role.CONTENT_EDITOR], Permission.PUBLISH_CREATE)
    assert_publish_transition(PublishState.COMMITTING, PublishState.RECONCILING)
    with pytest.raises(ConflictError):
        assert_publish_transition(PublishState.COMMITTING, PublishState.CANCELED)


class FakeDriver:
    capabilities = frozenset({"ui.selectors"})

    def __init__(self) -> None:
        self.cleared = 0

    async def clear_watchers(self) -> None:
        self.cleared += 1


class FailingPackage:
    def __init__(self) -> None:
        self.cleanup_calls = 0

    async def validate(self, context):
        return None

    async def preflight(self, driver, context):
        return None

    async def prepare(self, driver, context):
        raise RuntimeError("prepare failed")

    async def before_commit(self, driver, context):
        return None

    async def commit_once(self, driver, context):
        return None

    async def reconcile(self, driver, context):
        return ReconcileResult.SUCCEEDED

    async def cleanup(self, driver, context):
        self.cleanup_calls += 1


@pytest.mark.asyncio
async def test_automation_lifecycle_always_cleans_package_and_watchers() -> None:
    package = FailingPackage()
    driver = FakeDriver()
    runner = LifecycleRunner(package, driver)
    context = AutomationContext(
        tenant_id="tenant",
        target_id="target",
        snapshot_sha256="0" * 64,
        commit_intent_id="intent",
    )
    with pytest.raises(RuntimeError, match="prepare failed"):
        await runner.run(context)
    assert package.cleanup_calls == 1
    assert driver.cleared == 1


@pytest.mark.asyncio
async def test_automation_commit_requires_durable_intent() -> None:
    runner = LifecycleRunner(FailingPackage(), FakeDriver())
    context = AutomationContext(tenant_id="tenant", target_id="target", snapshot_sha256="0" * 64)
    with pytest.raises(ValueError, match="commit_intent_id"):
        await runner.commit_and_reconcile(context)


class SuccessfulPackage(FailingPackage):
    def __init__(self) -> None:
        super().__init__()
        self.commit_calls = 0

    async def prepare(self, driver, context):
        return None

    async def commit_once(self, driver, context):
        self.commit_calls += 1


@pytest.mark.asyncio
async def test_automation_commit_intent_is_consumed_before_single_attempt() -> None:
    package = SuccessfulPackage()
    runner = LifecycleRunner(package, FakeDriver())
    context = AutomationContext(
        tenant_id="tenant",
        target_id="target",
        snapshot_sha256="0" * 64,
        commit_intent_id="intent-once",
    )

    assert await runner.commit_and_reconcile(context) is ReconcileResult.SUCCEEDED
    with pytest.raises(RuntimeError, match="already been attempted"):
        await runner.commit_and_reconcile(context)
    assert package.commit_calls == 1
