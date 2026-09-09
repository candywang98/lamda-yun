"""Exercise the deployed Alembic ledger schema, not metadata.create_all."""

from __future__ import annotations

import sqlite3

from alembic import command
from test_control_api_migrations import (
    insert_legacy_operation,
    migration_config,
    table_columns,
    tables,
)


def test_mobile_action_ledger_migration_round_trip(tmp_path):
    path = tmp_path / "action-ledger.db"
    config = migration_config(path)
    command.upgrade(config, "20260831_0001")
    with sqlite3.connect(path) as connection:
        insert_legacy_operation(connection)
        assert "mobile_action_commit" not in tables(connection)
    command.upgrade(config, "20260909_0015")
    command.upgrade(config, "20260910_0016")
    with sqlite3.connect(path) as connection:
        assert {
            "action_key",
            "task_id",
            "device_id",
            "parameter_hash",
            "recipe_sha256",
            "snapshot_sha256",
            "before_evidence",
            "reported_evidence",
            "resolution_revision",
            "resolution_evidence",
            "resolved_at",
        } <= table_columns(connection, "mobile_action_commit")
        foreign_keys = list(connection.execute("PRAGMA foreign_key_list(mobile_action_commit)"))
        assert any(row[2:5] == ("mobile_task", "task_id", "id") for row in foreign_keys)
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='mobile_action_commit'"
        ).fetchone()[0]
        assert "uq_mobile_action_task_state" in schema
        assert "ck_mobile_action_status" in schema
        assert "ck_mobile_action_revision" in schema
        assert connection.execute("SELECT count(*) FROM operation_task").fetchone()[0] == 1
    command.downgrade(config, "20260909_0015")
    with sqlite3.connect(path) as connection:
        assert "mobile_action_commit" not in tables(connection)
        assert connection.execute("SELECT count(*) FROM operation_task").fetchone()[0] == 1
    command.upgrade(config, "20260910_0016")
    with sqlite3.connect(path) as connection:
        assert "mobile_action_commit" in tables(connection)
