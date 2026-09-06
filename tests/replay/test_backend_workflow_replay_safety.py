from __future__ import annotations

import ast
import inspect

import pytest
from cloudctl_worker import workflows
from cloudctl_worker.backend import InMemoryActivityBackend
from cloudctl_worker.contracts import PublishTargetInput


def test_commit_activity_retry_policy_is_exactly_once() -> None:
    assert workflows.COMMIT_ONCE_RETRY.maximum_attempts == 1


def test_workflow_source_has_no_nondeterministic_io_calls() -> None:
    tree = ast.parse(inspect.getsource(workflows))
    forbidden = {
        "datetime.now",
        "datetime.utcnow",
        "time.time",
        "random.random",
        "uuid.uuid4",
        "open",
        "requests.get",
        "requests.post",
    }
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            current = node.func
            parts = []
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
                calls.add(".".join(reversed(parts)))
    assert not (calls & forbidden)


@pytest.mark.asyncio
async def test_development_backend_refuses_second_commit() -> None:
    backend = InMemoryActivityBackend()
    input = PublishTargetInput(
        tenant_id="tenant",
        plan_id="plan",
        target_id="target",
        snapshot_id="snapshot",
        device_id="device",
    )
    lease = await backend.acquire_lease(input, "workflow")
    evidence = await backend.prepare(input, lease)
    intent = await backend.write_commit_intent(input, lease, evidence)
    await backend.commit_once(input, lease, intent)
    try:
        await backend.commit_once(input, lease, intent)
    except RuntimeError as exc:
        assert "more than once" in str(exc)
    else:
        raise AssertionError("second commit was accepted")
