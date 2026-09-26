"""Q02 acceptance suite shared fixtures.

Covers the eight scenarios of the Q02 task card (controlled-ledger acceptance):

1. intent ordering          - class A, tests/parallel_acceptance/q02/test_s01_intent_order.py
2. readback confirmation    - class A, test_s02_readback_confirmation.py (+ mock_platform.py stub)
3. lost ACK / duplicates    - class A, test_s03_lost_ack_idempotency.py
4. cancel state matrix      - class A, test_s04_cancel_matrix.py
5. stale lease / fencing    - class A, test_s05_stale_lease_fencing.py
6. reconciliation branches  - class A, test_s06_reconciliation_branches.py
7. same-task recovery       - class A, test_s07_same_task_recovery.py
8. device restart + real-device readback - class B, test_s08_device_scenarios.py
   (skipped unless Q02_DEVICE_SERIAL/Q02_BASE_URL are set; the controller runs
   them while holding the DEVICE:<serial> lock - see
   artifacts/parallel/W5/Q02/README.md for the execution handbook).

Shared guarantees provided here:

- ``integration_sha``: same-integration-SHA guard. The suite refuses to run
  unless the expected integration SHA (file ``expected_integration_sha.txt``
  or env ``Q02_EXPECTED_SHA``) is an ancestor of the current ``HEAD``. This
  prevents mixing test runs across versions. Fail-closed on git errors.
- ``ledger``: per-scenario taskId/hash recorder. Every scenario records its
  taskIds, action keys, and content hashes to a tmp run directory
  (``<tmp>/q02-ledger/q02-ledger.jsonl`` + one JSON per test). The controller
  archives that directory to artifacts/parallel/W5/Q02/ for the real-device
  execution bookkeeping.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.settings import Settings
from fastapi import FastAPI

SUITE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SUITE_DIR.parents[2]
EXPECTED_SHA_FILE = SUITE_DIR / "expected_integration_sha.txt"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")

TENANT = "00000000-0000-7000-8000-000000000111"
OPERATOR = "00000000-0000-7000-8000-000000000222"

DEVICE_SERIAL_ENV = "Q02_DEVICE_SERIAL"
BASE_URL_ENV = "Q02_BASE_URL"
EXPECTED_SHA_ENV = "Q02_EXPECTED_SHA"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "device_q02: class-B real-device scenario; skipped unless "
        f"{DEVICE_SERIAL_ENV} and {BASE_URL_ENV} are set. Run only by the "
        "controller while holding the DEVICE:<serial> lock.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-skip class-B device scenarios when no device is bound."""
    if os.environ.get(DEVICE_SERIAL_ENV) and os.environ.get(BASE_URL_ENV):
        return
    skip = pytest.mark.skip(
        reason=f"class-B device scenario: set {DEVICE_SERIAL_ENV} and "
        f"{BASE_URL_ENV} (controller-only, DEVICE lock required)"
    )
    for item in items:
        if "device_q02" in item.keywords:
            item.add_marker(skip)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed git invocation on the repo
        ["git", "-C", str(repo), *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="session")
def integration_sha() -> str:
    """Same-integration-SHA guard; fails closed to prevent cross-version runs."""
    expected = os.environ.get(EXPECTED_SHA_ENV, "").strip()
    if not expected:
        expected = EXPECTED_SHA_FILE.read_text(encoding="utf-8").strip()
    if not SHA_PATTERN.match(expected):
        pytest.fail(
            f"q02 same-SHA guard: expected integration SHA {expected!r} is not a "
            f"40-hex commit (file {EXPECTED_SHA_FILE} or env {EXPECTED_SHA_ENV})"
        )
    head = _git(REPO_ROOT, "rev-parse", "HEAD")
    if head.returncode != 0:
        pytest.fail(
            f"q02 same-SHA guard: git rev-parse HEAD failed in {REPO_ROOT}: {head.stderr.strip()}"
        )
    head_sha = head.stdout.strip()
    ancestor = _git(REPO_ROOT, "merge-base", "--is-ancestor", expected, head_sha)
    if ancestor.returncode != 0:
        pytest.fail(
            f"q02 same-SHA guard: expected integration SHA {expected} is not an "
            f"ancestor of HEAD {head_sha}; refusing to mix versions. On the "
            f"merged integration branch set {EXPECTED_SHA_ENV} to the frozen "
            "integration SHA."
        )
    return head_sha


class ScenarioLedger:
    """Per-test taskId/hash recorder; see artifacts/parallel/W5/Q02/README.md."""

    def __init__(self, run_dir: Path, scenario: str, sha: str) -> None:
        self.run_dir = run_dir
        self.scenario = scenario
        self.sha = sha
        self.path = run_dir / f"{scenario}-{uuid.uuid4().hex[:8]}.json"
        self.entries: list[dict[str, Any]] = []

    def record(self, event: str, **fields: Any) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "scenario": self.scenario,
            "event": event,
            "recordedAt": datetime.now(UTC).isoformat(),
            "integrationSha": self.sha,
        }
        entry.update(fields)
        self.entries.append(entry)
        self.path.write_text(
            json.dumps(self.entries, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        with (self.run_dir / "q02-ledger.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def record_action(
        self,
        task_id: str,
        action_view: dict[str, Any] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {"taskId": task_id, **extra}
        if action_view is not None:
            fields.update(
                {
                    "actionKey": action_view.get("actionKey"),
                    "actionId": action_view.get("actionId"),
                    "parameterHash": action_view.get("parameterHash"),
                    "snapshotSha256": action_view.get("snapshotSha256"),
                    "recipeSha256": action_view.get("recipeSha256"),
                    "status": action_view.get("status"),
                    "resolutionRevision": action_view.get("resolutionRevision"),
                }
            )
        return self.record("controlled-action", **fields)


@pytest.fixture
def ledger(
    integration_sha: str, tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest
) -> ScenarioLedger:
    run_dir = tmp_path_factory.mktemp("q02-ledger")
    return ScenarioLedger(run_dir, request.node.originalname, integration_sha)


@pytest.fixture
async def api(integration_sha: str) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


def identity(*, role: str = "device_operator") -> dict[str, str]:
    return {
        "X-Tenant-Id": TENANT,
        "X-User-Id": OPERATOR,
        "X-Roles": role,
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }


async def create_direct_device(client: httpx.AsyncClient, name: str) -> str:
    response = await client.post(
        "/api/v1/mobile/devices",
        headers=identity(),
        json={"logicalName": name, "androidVersion": "14", "companionVersion": "1.0.0"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def create_account(client: httpx.AsyncClient, subject: str) -> str:
    response = await client.post(
        "/api/v1/accounts",
        headers=identity(),
        json={
            "platform": "xianyu",
            "externalSubjectRef": subject,
            "displayLabel": subject,
            "secretRef": f"vault://cloudctl/accounts/{subject}",
            "authorizationBasis": "Owner authorized the test account.",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def bind(client: httpx.AsyncClient, account_id: str, device_id: str) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/accounts/{account_id}/bindings",
        headers=identity(),
        json={"deviceId": device_id, "confirmationNote": "Owner confirmed."},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def enroll(client: httpx.AsyncClient, device_id: str, instance: str) -> dict[str, str]:
    enroll = await client.post(
        "/api/v1/mobile/enrollments",
        headers=identity(),
        json={"deviceId": device_id, "ttlSeconds": 600},
    )
    token_resp = await client.post(
        "/companion/v2/enroll",
        json={
            "code": enroll.json()["code"],
            "appInstanceId": instance,
            "companionVersion": "1.0.0",
        },
    )
    return {"Authorization": f"Bearer {token_resp.json()['bindingToken']}"}


async def claim(client: httpx.AsyncClient, auth: dict[str, str]) -> dict[str, Any]:
    response = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert response.status_code == 200, response.text
    return response.json()
