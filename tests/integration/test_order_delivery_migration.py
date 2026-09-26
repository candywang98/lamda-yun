"""Additive receipt migration, including real PostgreSQL rollback/re-upgrade."""

import asyncio
from datetime import UTC, datetime

import pytest
from alembic import command
from sqlalchemy import MetaData, Table, insert, inspect, select
from sqlalchemy.ext.asyncio import create_async_engine
from test_control_api_migrations import migration_config
from test_p14_recipe_versions import isolated_postgres, pg_url  # noqa: F401


async def _history(url, *, seed=False, receipt_table=False):
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:

            def read_schema(sync):
                metadata = MetaData()
                table = Table("operation_task", metadata, autoload_with=sync)
                names = inspect(sync).get_table_names()
                return table, names

            table, names = await connection.run_sync(read_schema)
            assert ("order_delivery_receipt" in names) is receipt_table
            if seed:
                await connection.execute(
                    insert(table).values(
                        id="00000000-0000-7000-8000-000000008001",
                        tenant_id="00000000-0000-7000-8000-000000008002",
                        operation_key="works.revision.validate",
                        module="product-management",
                        idempotency_key="legacy",
                        request_sha256="a" * 64,
                        requested_by="00000000-0000-7000-8000-000000008003",
                        status="QUEUED",
                        parameters={},
                        context={},
                        total_count=0,
                        succeeded_count=0,
                        failed_count=0,
                        blocked_count=0,
                        canceled_count=0,
                        cancel_requested=False,
                        result_summary={},
                        created_at=datetime(2026, 9, 26, tzinfo=UTC),
                    )
                )
            return [dict(row) for row in (await connection.execute(select(table))).mappings()]
    finally:
        await engine.dispose()


@pytest.mark.parametrize("dialect", ["sqlite", "postgres"])
def test_order_receipt_migration_preserves_history(dialect, tmp_path, monkeypatch, request):
    monkeypatch.delenv("CLOUDCTL_DATABASE_URL", raising=False)
    config = migration_config(tmp_path / "receipt.db")
    url = (
        request.getfixturevalue("pg_url")
        if dialect == "postgres"
        else config.get_main_option("sqlalchemy.url")
    )
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "20260926_0034")
    before = asyncio.run(_history(url, seed=True))
    command.upgrade(config, "20260926_0035")
    assert asyncio.run(_history(url, receipt_table=True)) == before
    command.downgrade(config, "20260926_0034")
    assert asyncio.run(_history(url)) == before
    command.upgrade(config, "20260926_0035")
    assert asyncio.run(_history(url, receipt_table=True)) == before
