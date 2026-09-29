"""Owned PostgreSQL must fail closed and release resources at every boundary."""

from __future__ import annotations

import asyncio
import shutil
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from cloudctl_api import create_app
from cloudctl_api.db import Database
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import make_url

from . import harness as fleet
from .postgres import FleetPostgres


def assert_cluster_removed(cluster: FleetPostgres) -> None:
    assert cluster.root is not None
    assert not cluster.root.exists()
    with socket.socket() as sock:
        sock.settimeout(1)
        assert sock.connect_ex(("127.0.0.1", cluster.port)) != 0


@pytest.fixture
def cleanup_order(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    events: list[str] = []
    original_dispose = Database.dispose
    original_close = FleetPostgres.close

    async def dispose(database: Database) -> None:
        await original_dispose(database)
        events.append("engine-disposed")

    def close(cluster: FleetPostgres) -> None:
        events.append("cluster-stop")
        original_close(cluster)

    monkeypatch.setattr(Database, "dispose", dispose)
    monkeypatch.setattr(FleetPostgres, "close", close)
    return events


@pytest.mark.parametrize("missing", ["initdb", "pg_ctl", "createdb"])
def test_missing_postgres_binary_is_required_failure(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    original_which = shutil.which
    monkeypatch.setattr(
        shutil, "which", lambda name: None if name == missing else original_which(name)
    )
    cluster = FleetPostgres()
    with pytest.raises(RuntimeError, match=f"requires local PostgreSQL binary on PATH: {missing}"):
        with cluster:
            pytest.fail("missing PostgreSQL must not skip or use another backend")
    assert cluster.root is None


@pytest.mark.parametrize("phase", ["initdb", "start", "createdb"])
def test_cluster_startup_failure_cleans_even_after_server_started(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    original_run = FleetPostgres._run
    failure = RuntimeError(f"injected {phase} failure")
    cluster = FleetPostgres()

    def fail_after_command(cluster: FleetPostgres, tool: str, *arguments: str) -> None:
        original_run(cluster, tool, *arguments)
        if (tool == phase) or (phase == "start" and tool == "pg_ctl" and arguments[-1] == "start"):
            raise failure

    monkeypatch.setattr(FleetPostgres, "_run", fail_after_command)
    with pytest.raises(RuntimeError) as caught:
        with cluster:
            pytest.fail("injected startup failure must propagate")
    assert caught.value is failure
    assert_cluster_removed(cluster)


@pytest.mark.asyncio
async def test_ambient_external_database_configuration_is_never_used(
    monkeypatch: pytest.MonkeyPatch, cleanup_order: list[str]
) -> None:
    def only_loopback_app(settings: Settings) -> FastAPI:
        assert settings.database_url is not None
        url = make_url(settings.database_url)
        assert url.host == "127.0.0.1", "reject an external URL before creating any engine"
        assert url.database is not None and url.database.startswith("fleet_")
        return create_app(settings)

    monkeypatch.setattr(fleet, "create_app", only_loopback_app)
    for key in ("DATABASE_URL", "CLOUDCTL_DATABASE_URL"):
        monkeypatch.setenv(key, "postgresql+asyncpg://do-not-connect.invalid/production")
    for key, value in {
        "PGHOST": "do-not-connect.invalid",
        "PGPORT": "1",
        "PGDATABASE": "production",
        "PGUSER": "production",
        "PGSERVICE": "do-not-use",
    }.items():
        monkeypatch.setenv(key, value)
    async with fleet.FleetLoadApp() as harness:
        cluster = harness.postgres
        database: Database = harness.app.state.database
        assert database.engine.url.host == "127.0.0.1"
        assert database.engine.url.port == cluster.port
        assert database.engine.url.database == cluster.name
        assert database.engine.url.drivername == "postgresql+asyncpg"
        assert not any(key.startswith("PG") for key in cluster.environment)
        assert "DATABASE_URL" not in cluster.environment
        assert "CLOUDCTL_DATABASE_URL" not in cluster.environment
        async with database.unit_of_work() as session:
            assert await session.scalar(text("SELECT current_database()")) == cluster.name
            assert await session.scalar(text("SHOW listen_addresses")) == "127.0.0.1"
            assert await session.scalar(text("SHOW unix_socket_directories")) == ""
            directory = await session.scalar(text("SHOW data_directory"))
            assert cluster.root is not None
            actual = await asyncio.to_thread(Path(str(directory)).resolve)
            expected = await asyncio.to_thread((cluster.root / "data").resolve)
            assert actual == expected
    assert cleanup_order == ["engine-disposed", "cluster-stop"]
    assert harness.client.is_closed
    assert_cluster_removed(cluster)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["schema", "lifespan", "schema-cancellation"])
async def test_failed_app_entry_disposes_engine_before_stopping_cluster(
    monkeypatch: pytest.MonkeyPatch, cleanup_order: list[str], phase: str
) -> None:
    original_schema = Database.create_schema
    ready = asyncio.Event()
    failure = RuntimeError(f"injected {phase} failure")

    async def schema(database: Database) -> None:
        await original_schema(database)
        if phase == "schema-cancellation":
            ready.set()
            await asyncio.Event().wait()
        if phase == "schema":
            raise failure

    @asynccontextmanager
    async def failed_lifespan(app: FastAPI) -> AsyncIterator[None]:
        await app.state.database.ping()
        if phase == "lifespan":
            raise failure
        yield

    def starting_app(settings: Settings) -> FastAPI:
        app = create_app(settings)
        if phase == "lifespan":
            app.router.lifespan_context = failed_lifespan
        return app

    monkeypatch.setattr(Database, "create_schema", schema)
    monkeypatch.setattr(fleet, "create_app", starting_app)
    harness = fleet.FleetLoadApp()
    if phase == "schema-cancellation":
        entry = asyncio.create_task(harness.__aenter__())
        try:
            await asyncio.wait_for(ready.wait(), timeout=10)
        finally:
            entry.cancel()
            with pytest.raises(asyncio.CancelledError):
                await entry
    else:
        with pytest.raises(RuntimeError) as caught:
            async with harness:
                pytest.fail("failed startup must not enter the harness body")
        assert caught.value is failure
    assert cleanup_order == ["engine-disposed", "cluster-stop"]
    assert_cluster_removed(harness.postgres)


@pytest.mark.asyncio
async def test_body_exception_closes_client_engine_and_cluster(cleanup_order: list[str]) -> None:
    failure = RuntimeError("injected test body failure")
    harness = fleet.FleetLoadApp()
    with pytest.raises(RuntimeError) as caught:
        async with harness:
            await harness.app.state.database.ping()
            raise failure
    assert caught.value is failure
    assert harness.client.is_closed
    assert cleanup_order == ["engine-disposed", "cluster-stop"]
    assert_cluster_removed(harness.postgres)


@pytest.mark.parametrize("phase", ["startup", "body"])
def test_failed_stop_retains_data_and_original_failure_context(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    original_run = FleetPostgres._run
    failure = RuntimeError("original test failure")
    cleanup_failure = RuntimeError("injected cluster stop failure")
    cluster = FleetPostgres()

    def failed_cleanup(cluster: FleetPostgres, tool: str, *arguments: str) -> None:
        if tool == "pg_ctl" and arguments[-1] == "stop":
            raise cleanup_failure
        original_run(cluster, tool, *arguments)
        if phase == "startup" and tool == "createdb":
            raise failure

    try:
        with monkeypatch.context() as patch:
            patch.setattr(FleetPostgres, "_run", failed_cleanup)
            with pytest.raises(RuntimeError) as caught:
                with cluster:
                    raise failure
            assert caught.value is cleanup_failure
            assert caught.value.__context__ is failure
            assert cluster.root is not None
            assert (cluster.root / "data" / "postmaster.pid").exists()
            with socket.socket() as sock:
                sock.settimeout(1)
                assert sock.connect_ex(("127.0.0.1", cluster.port)) == 0
    finally:
        # Restore real stopping before draining the deliberately retained test cluster.
        cluster.close()
    assert_cluster_removed(cluster)
