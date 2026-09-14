"""P14 frozen recipe-version/20260909.1 API and real database concurrency checks."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import shutil
import socket
import subprocess
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.builtin_recipes import builtin_recipe_ref
from cloudctl_api.db import AuditEventRow, MobileTaskRow, RecipeDeploymentRow
from cloudctl_api.settings import Settings
from cloudctl_automation_sdk import package_signature_payload
from cloudctl_automation_sdk.recipe import CURRENT_ENGINE_VERSION, canonical_recipe_bytes
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from test_backend_control_api import (
    AUTOMATION_KEY_ID,
    AUTOMATION_PRIVATE_KEY,
    CREATOR,
    TENANT,
    automation_public_key,
    headers,
    signed_recipe_package,
)
from test_platform_tasks import PROBE, _enroll, bind, create_account, create_direct_device, identity

DEVELOPER = headers(CREATOR, "automation_developer")


@pytest.fixture(scope="module")
def isolated_postgres(tmp_path_factory):
    """Never use DATABASE_URL: start our own disposable cluster on a free port."""
    if not all(shutil.which(tool) for tool in ("initdb", "pg_ctl", "createdb")):
        pytest.skip("local PostgreSQL binaries unavailable")
    root = tmp_path_factory.mktemp("p14-postgres")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
        ["initdb", "-D", str(root / "data"), "-A", "trust", "-U", "p14test"],  # noqa: S607
        check=True,
        capture_output=True,
    )
    subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
        [  # noqa: S607
            "pg_ctl",
            "-D",
            str(root / "data"),
            "-l",
            str(root / "server.log"),
            "-o",
            f"-h 127.0.0.1 -p {port} -c unix_socket_directories=''",
            "-w",
            "start",
        ],
        check=True,
        capture_output=True,
    )
    try:
        yield port
    finally:
        subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
            ["pg_ctl", "-D", str(root / "data"), "-m", "immediate", "-w", "stop"],  # noqa: S607
            check=True,
            capture_output=True,
        )


@pytest.fixture
def pg_url(isolated_postgres):
    name = "p14_" + uuid.uuid4().hex
    subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
        ["createdb", "-h", "127.0.0.1", "-p", str(isolated_postgres), "-U", "p14test", name],  # noqa: S607
        check=True,
        capture_output=True,
    )
    return f"postgresql+asyncpg://p14test@127.0.0.1:{isolated_postgres}/{name}"


@pytest.fixture(params=["sqlite", "postgres"])
async def api(request):
    settings = Settings(
        env="test",
        repository_mode="memory",
        dev_auth_bypass=True,
        automation_signing_public_keys={AUTOMATION_KEY_ID: automation_public_key()},
    )
    if request.param == "postgres":
        settings = settings.model_copy(
            update={
                "repository_mode": "postgresql",
                "database_url": request.getfixturevalue("pg_url"),
            }
        )
    app = create_app(settings)
    await app.state.database.create_schema()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, app


def package(version, *, commands=None, engine=1):
    value = signed_recipe_package(version=version)
    if commands:
        value["manifest"]["commandTypes"] = commands
    value["manifest"]["minEngineVersion"] = engine
    value["manifest"]["hash"] = hashlib.sha256(canonical_recipe_bytes(value)).hexdigest()
    value["signature"]["digest"] = base64.b64encode(
        AUTOMATION_PRIVATE_KEY.sign(
            package_signature_payload(
                artifact_sha256=value["manifest"]["hash"],
                manifest=value["manifest"],
                sbom_ref="recipe://local",
                sbom_sha256=value["manifest"]["hash"],
            )
        )
    ).decode()
    return value


async def register(client, version, **kwargs):
    response = await client.post(
        "/api/v1/recipes", headers=DEVELOPER, json=package(version, **kwargs)
    )
    assert response.status_code == 201, response.text
    return response.json()["versionId"]


async def change(client, version, devices, action="publish", key=None, expected=None):
    body = {"targetDeviceIds": devices, "idempotencyKey": "p14-key-" + (key or str(uuid.uuid4()))}
    if expected is not None:
        body["expectedCurrentVersionId"] = expected
    return await client.post(f"/api/v1/recipes/{version}:{action}", headers=DEVELOPER, json=body)


async def task(client, device):
    account = await create_account(client, "account-" + str(uuid.uuid4()))
    await bind(client, account, device)
    response = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": str(uuid.uuid4())},
        json={"deviceId": device, "accountId": account, **PROBE},
    )
    assert response.status_code == 201, response.text
    return response.json()["items"][0]["taskId"]


async def claim(client, auth):
    response = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_catalog_history_rollback_and_idempotency(api):
    client, app = api
    device = await create_direct_device(client, "catalog")
    commands = ["device.probe_capabilities.v1", "device.second_probe.v1"]
    old = await register(client, "1", commands=commands)
    new = await register(client, "2", commands=list(reversed(commands)))
    published = await change(client, old, [device], key="old")
    assert published.status_code == 200, published.text
    assert [d["commandType"] for d in published.json()["deployments"]] == sorted(commands)
    assert (await change(client, new, [device], key="new")).status_code == 200
    rollback = await change(client, old, [device], "rollback", "rollback", new)
    assert rollback.status_code == 200, rollback.text
    assert len(rollback.json()["deployments"]) == 2
    assert all(d["previousVersionId"] == new for d in rollback.json()["deployments"])
    assert (
        await change(client, old, [device], "rollback", "rollback", new)
    ).json() == rollback.json()
    assert (await change(client, old, [device], "revoke", "rollback")).status_code == 409
    assert (await change(client, new, [device], "publish", "rollback")).status_code == 409
    catalog = await client.get("/api/v1/recipes", headers=DEVELOPER)
    assert [r["versionId"] for r in catalog.json()["items"]] == [new, old]
    history = catalog.json()["items"][1]
    assert len(history["deployments"]) == 4
    for item in history["deployments"]:
        assert item["publishedBy"] == CREATOR
        assert datetime.fromisoformat(item["updatedAt"]) >= datetime.fromisoformat(
            item["createdAt"]
        )
    assert (await client.get(f"/api/v1/recipes/{old}", headers=DEVELOPER)).json() == history
    revoked = await change(client, old, [device], "revoke", "revoke")
    assert len(revoked.json()["deployments"]) == 2
    assert (await change(client, old, [device], "revoke", "revoke")).json() == revoked.json()
    # A replay cannot reactivate or mutate the historical snapshot.
    assert (
        await change(client, old, [device], "rollback", "rollback", new)
    ).json() == rollback.json()
    auth = await _enroll(client, device, "catalog-instance")
    assert (await client.get("/companion/v2/recipes/active", headers=auth)).json()["items"] == []
    async with app.state.database.unit_of_work() as session:
        audits = list(
            await session.scalars(
                select(AuditEventRow).where(AuditEventRow.action == "recipe.version.rolled_back")
            )
        )
        assert len(audits) == 1
        assert audits[0].actor_id == CREATOR
        assert audits[0].metadata_json["expected_current_version_id"] == new


async def test_atomic_stale_history_and_tenant_permissions(api):
    client, _ = api
    one = await create_direct_device(client, "one")
    two = await create_direct_device(client, "two")
    old, new, unused = [await register(client, v) for v in ("1", "2", "3")]
    await change(client, old, [one])
    await change(client, new, [one, two])
    assert (await change(client, old, [one, two], "rollback", expected=new)).status_code == 409
    assert (await change(client, unused, [one], "rollback", expected=new)).status_code == 409
    assert (await change(client, old, [one], "rollback", expected=unused)).status_code == 409
    assert (await change(client, old, [one, str(uuid.uuid4())])).status_code == 404
    for device in (one, two):
        auth = await _enroll(client, device, device)
        active = (await client.get("/companion/v2/recipes/active", headers=auth)).json()
        assert active["items"][0]["versionId"] == new
    other = DEVELOPER | {"X-Tenant-Id": str(uuid.uuid4())}
    assert (await client.get("/api/v1/recipes", headers=other)).json() == {"items": []}
    assert (await client.get(f"/api/v1/recipes/{old}", headers=other)).status_code == 404
    assert (
        await client.post(
            f"/api/v1/recipes/{old}:rollback",
            headers=other,
            json={
                "targetDeviceIds": [one],
                "idempotencyKey": "other-key",
                "expectedCurrentVersionId": new,
            },
        )
    ).status_code == 404
    foreign_device = await client.post(
        "/api/v1/mobile/devices",
        headers=other | {"X-Roles": "device_operator"},
        json={"logicalName": "foreign", "androidVersion": "14"},
    )
    assert foreign_device.status_code == 201, foreign_device.text
    assert (await change(client, old, [foreign_device.json()["id"]])).status_code == 404
    assert (
        await client.get("/api/v1/recipes", headers=headers(CREATOR, "publisher"))
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/recipes/{old}:rollback",
            headers=headers(CREATOR, "publisher"),
            json={
                "targetDeviceIds": [one],
                "idempotencyKey": "denied-key",
                "expectedCurrentVersionId": new,
            },
        )
    ).status_code == 403
    assert (
        await client.post(
            "/api/v1/recipes", headers=DEVELOPER, json=package("4", engine=CURRENT_ENGINE_VERSION + 1)
        )
    ).status_code == 422


@pytest.mark.parametrize("builtin", [False, True])
async def test_claim_pin_survives_revoke_retry_resume_and_restart(api, builtin):
    client, app = api
    device = await create_direct_device(client, "pin")
    other_device = await create_direct_device(client, "other")
    old = await register(client, "1")
    new = await register(client, "2")
    if not builtin:
        await change(client, old, [device])
    task_id = await task(client, device)
    auth = await _enroll(client, device, "pin-instance")
    other_auth = await _enroll(client, other_device, "other-instance")
    first = await claim(client, auth)
    pin = first["command"]["recipe"]
    assert pin["versionId"] == (
        builtin_recipe_ref(PROBE["commandType"])["versionId"] if builtin else old
    )
    await change(client, new, [device])
    async with app.state.database.unit_of_work() as session:
        stored = await session.get(MobileTaskRow, task_id)
        assert stored.recipe_pin == pin
        stored.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    # Recreate the service as on application restart: it must use the stored pin.
    from cloudctl_api.mobile_service import MobileTaskService

    app.state.mobile_task_service = MobileTaskService(app.state.database)
    retry = await claim(client, auth)
    assert retry["command"]["recipe"] == pin
    assert retry["attempt"] == 2
    if not builtin:
        assert (await change(client, old, [device], "rollback", expected=new)).status_code == 200
        assert (await change(client, old, [device], "revoke")).status_code == 200
    async with app.state.database.unit_of_work() as session:
        stored = await session.get(MobileTaskRow, task_id)
        stored.business_state = "PAUSED_WAITING_USER"
    if not builtin:
        assert (await client.get(f"/companion/v2/recipes/{old}", headers=auth)).status_code == 200
        assert (
            await client.get(f"/companion/v2/recipes/{old}", headers=other_auth)
        ).status_code == 404
    resumed = await client.post(
        f"/api/v1/platform-tasks/{task_id}:resume",
        headers=identity(),
        json={"pageVerified": True, "reason": "verified"},
    )
    assert resumed.status_code == 200, resumed.text
    async with app.state.database.unit_of_work() as session:
        stored = await session.get(MobileTaskRow, task_id)
        assert stored.recipe_pin == pin
        stored.business_state = "RECONCILING"
    if not builtin:
        assert (await client.get(f"/companion/v2/recipes/{old}", headers=auth)).status_code == 200
    async with app.state.database.unit_of_work() as session:
        stored = await session.get(MobileTaskRow, task_id)
        stored.status = "SUCCEEDED"
        stored.business_state = "SUCCEEDED"
        audits = list(
            await session.scalars(
                select(AuditEventRow).where(AuditEventRow.action == "recipe.task.pinned")
            )
        )
        assert len(audits) == 1
        assert audits[0].metadata_json["recipe"] == pin
    assert (await client.get(f"/companion/v2/recipes/{old}", headers=auth)).status_code == 404


async def test_database_rejects_second_active_command(api):
    client, app = api
    device = await create_direct_device(client, "unique")
    old = await register(client, "1")
    await change(client, old, [device])
    with pytest.raises(IntegrityError):
        async with app.state.database.unit_of_work() as session:
            session.add(
                RecipeDeploymentRow(
                    id=str(uuid.uuid4()),
                    tenant_id=TENANT,
                    version_id=old,
                    device_id=device,
                    command_type=PROBE["commandType"],
                    status="PUBLISHED",
                    idempotency_key="duplicate",
                    published_by=CREATOR,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )


async def test_postgres_concurrent_publish_rollback_and_claim(pg_url):
    settings = Settings(
        env="test",
        repository_mode="postgresql",
        database_url=pg_url,
        dev_auth_bypass=True,
        automation_signing_public_keys={AUTOMATION_KEY_ID: automation_public_key()},
    )
    app = create_app(settings)
    await app.state.database.create_schema()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            device = await create_direct_device(client, "race")
            old, new = [await register(client, v) for v in ("1", "2")]
            responses = await asyncio.gather(
                change(client, old, [device], key="same"), change(client, old, [device], key="same")
            )
            assert [r.status_code for r in responses] == [200, 200]
            assert responses[0].json() == responses[1].json()
            await change(client, new, [device])
            responses = await asyncio.gather(
                change(client, old, [device], "rollback", "r1", new),
                change(client, old, [device], "rollback", "r2", new),
            )
            assert sorted(r.status_code for r in responses) == [200, 409]
            task_id = await task(client, device)
            auth = await _enroll(client, device, "race-instance")
            published, claimed = await asyncio.gather(
                change(client, new, [device]), claim(client, auth)
            )
            assert published.status_code == 200
            pin = claimed["command"]["recipe"]
            assert pin["versionId"] in {old, new}
            async with app.state.database.unit_of_work() as session:
                stored = await session.get(MobileTaskRow, task_id)
                assert stored.recipe_pin == pin
                stored.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            responses = await asyncio.gather(
                client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}),
                client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}),
            )
            assert sorted(r.status_code for r in responses) == [200, 204]
            winner = next(r for r in responses if r.status_code == 200)
            assert winner.json()["command"]["recipe"] == pin


def test_postgres_migration_upgrade_downgrade(pg_url, monkeypatch):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    monkeypatch.delenv("CLOUDCTL_DATABASE_URL", raising=False)
    config = Config(Path(__file__).resolve().parents[2] / "services/control-api/alembic.ini")
    config.set_main_option("sqlalchemy.url", pg_url)
    command.upgrade(config, "head")
    command.downgrade(config, "20260908_0014")
    command.upgrade(config, "head")
    command.downgrade(config, "base")


def test_migration_duplicate_history_and_multicommand_downgrade(tmp_path, monkeypatch):
    import sqlite3

    from alembic import command
    from test_control_api_migrations import migration_config, table_columns

    monkeypatch.delenv("CLOUDCTL_DATABASE_URL", raising=False)
    path = tmp_path / "recipe-migration.db"
    config = migration_config(path)
    command.upgrade(config, "20260908_0014")
    with sqlite3.connect(path) as connection:
        for number in (1, 2):
            connection.execute(
                """
                INSERT INTO recipe_device_deployment
                (id, tenant_id, version_id, device_id, command_type, status,
                 idempotency_key, published_by, created_at)
                VALUES (?, 'tenant', ?, 'device', 'probe', 'PUBLISHED', ?, 'actor', ?)
            """,
                (str(number), f"version{number}", f"key{number}", f"2026-09-0{number} 00:00:00"),
            )
    command.upgrade(config, "head")
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT id, status FROM recipe_device_deployment ORDER BY id"
        ).fetchall() == [("1", "REVOKED"), ("2", "PUBLISHED")]
        assert "recipe_pin" in table_columns(connection, "mobile_task")
        connection.execute("""
            INSERT INTO recipe_device_deployment
            (id, tenant_id, version_id, device_id, command_type, status,
             idempotency_key, published_by, created_at, updated_at)
            VALUES ('3', 'tenant', 'version2', 'device', 'second', 'PUBLISHED',
                    'key2', 'actor', '2026-09-02 00:00:00', '2026-09-02 00:00:00')
        """)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE recipe_device_deployment SET status = 'PUBLISHED' WHERE id = '1'"
            )
    command.downgrade(config, "20260908_0014")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM recipe_device_deployment").fetchone() == (
            3,
        )
        assert "recipe_pin" not in table_columns(connection, "mobile_task")
    command.upgrade(config, "head")


async def test_reconciling_task_cannot_be_reclaimed_after_lease_expiry(api):
    client, app = api
    device = await create_direct_device(client, "reconcile-lock")
    task_id = await task(client, device)
    auth = await _enroll(client, device, "reconcile-lock-instance")
    first = await claim(client, auth)
    async with app.state.database.unit_of_work() as session:
        stored = await session.get(MobileTaskRow, task_id)
        stored.business_state = "RECONCILING"
        stored.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    response = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert response.status_code == 204
    async with app.state.database.unit_of_work() as session:
        stored = await session.get(MobileTaskRow, task_id)
        assert stored.business_state == "RECONCILING"
        assert stored.attempt == first["attempt"]
        assert stored.recipe_pin == first["command"]["recipe"]


async def test_legacy_attempt_without_recipe_pin_cannot_select_new_version(api):
    client, app = api
    device = await create_direct_device(client, "legacy-pin")
    task_id = await task(client, device)
    auth = await _enroll(client, device, "legacy-pin-instance")
    first = await claim(client, auth)
    newer = await register(client, "2")
    await change(client, newer, [device])
    async with app.state.database.unit_of_work() as session:
        stored = await session.get(MobileTaskRow, task_id)
        stored.recipe_pin = None
        stored.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    response = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert response.status_code == 409
    assert "no persisted recipe pin" in response.json()["detail"]
    async with app.state.database.unit_of_work() as session:
        stored = await session.get(MobileTaskRow, task_id)
        assert stored.recipe_pin is None
        assert stored.attempt == first["attempt"]
