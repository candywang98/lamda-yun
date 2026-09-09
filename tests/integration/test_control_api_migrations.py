from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPOSITORY_ROOT / "services" / "control-api" / "alembic.ini"


def migration_config(database_path: Path) -> Config:
    config = Config(ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    return config


def operation_columns(connection: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in connection.execute("PRAGMA table_info(operation_task)")}


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def insert_legacy_operation(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO operation_task (
            id, tenant_id, operation_key, module, idempotency_key, request_sha256,
            requested_by, status, parameters, total_count, succeeded_count,
            failed_count, blocked_count, canceled_count, cancel_requested,
            result_summary, started_at, completed_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "00000000-0000-7000-8000-000000008001",
            "00000000-0000-7000-8000-000000008002",
            "works.revision.validate",
            "product-management",
            "legacy-task-1",
            "a" * 64,
            "00000000-0000-7000-8000-000000008003",
            "QUEUED",
            "{}",
            1,
            0,
            0,
            0,
            0,
            0,
            "{}",
            None,
            None,
            "2026-08-31 09:00:00+00:00",
        ),
    )
    connection.commit()


def insert_unfenced_debug_session(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO debug_session (
            id, tenant_id, edge_id, device_id, created_by, purpose, capabilities,
            status, expires_at, launch_code_hash, launch_code_used_at,
            relay_token_hash, relay_token_expires_at, exchanged_at,
            last_heartbeat_at, stage, last_event, detail, return_url, revoked_at,
            revoked_by, revoke_reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "00000000-0000-7000-8000-000000008101",
            "00000000-0000-7000-8000-000000008102",
            "00000000-0000-7000-8000-000000008103",
            "00000000-0000-7000-8000-000000008104",
            "00000000-0000-7000-8000-000000008105",
            "legacy unfenced debug session",
            '["view.frame"]',
            "ACTIVE",
            "2026-09-01 09:00:00+00:00",
            "b" * 64,
            "2026-08-31 09:00:01+00:00",
            "c" * 64,
            "2026-09-01 09:00:00+00:00",
            "2026-08-31 09:00:01+00:00",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "2026-08-31 09:00:00+00:00",
        ),
    )
    connection.commit()


def test_upgrade_and_downgrade_preserve_legacy_operation_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "control-api-migrations.db"
    config = migration_config(database_path)
    command.upgrade(config, "20260831_0001")

    with sqlite3.connect(database_path) as connection:
        insert_legacy_operation(connection)
        assert "feature_id" not in operation_columns(connection)
        assert "debug_session" not in tables(connection)

    command.upgrade(config, "20260831_0002")
    with sqlite3.connect(database_path) as connection:
        insert_unfenced_debug_session(connection)

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        columns = operation_columns(connection)
        assert {
            "feature_id",
            "context",
            "approval_decision",
            "approval_reason",
            "approved_by",
            "decided_at",
        } <= columns
        assert {"debug_session", "debug_evidence"} <= tables(connection)
        assert "operation_feature_config_draft" in tables(connection)
        assert {
            "media_tag",
            "media_group",
            "media_group_membership",
            "content_revision_media",
        } <= tables(connection)
        assert {"media_asset_id", "tag"} <= table_columns(connection, "media_tag")
        assert {
            "mobile_enrollment",
            "mobile_binding",
            "mobile_task",
            "mobile_task_event",
            "device_preview",
            "recipe_device_deployment",
        } <= tables(connection)
        device_edge = {
            str(row[1]): int(row[3]) for row in connection.execute("PRAGMA table_info(device)")
        }
        assert device_edge["edge_id"] == 0
        assert {
            "id",
            "tenant_id",
            "device_id",
            "idempotency_key",
            "request_sha256",
            "requested_by",
            "target_package",
            "steps",
            "status",
            "lease_id",
            "lease_expires_at",
            "attempt",
            "last_sequence",
            "current_step",
            "result",
            "error_code",
            "detail",
            "started_at",
            "completed_at",
            "created_at",
        } == table_columns(connection, "mobile_task")
        assert {
            "id",
            "tenant_id",
            "feature_id",
            "configuration_json",
            "configuration_sha256",
            "version",
            "updated_by",
            "updated_at",
            "created_at",
        } == table_columns(connection, "operation_feature_config_draft")
        assert {
            "device_id",
            "tenant_id",
            "session_id",
            "session_expires_at",
            "requested_by",
            "capture_interval_ms",
            "frame_session_id",
            "content_type",
            "sha256",
            "width",
            "height",
            "image_bytes",
            "captured_at",
            "updated_at",
            "created_at",
        } == table_columns(connection, "device_preview")
        legacy_debug = connection.execute(
            "SELECT status, lease_id, fencing_token, revoke_reason FROM debug_session WHERE id = ?",
            ("00000000-0000-7000-8000-000000008101",),
        ).fetchone()
        assert legacy_debug == (
            "REVOKED",
            None,
            None,
            "migration: fencing lease required",
        )
        context = connection.execute(
            "SELECT context FROM operation_task WHERE id = ?",
            ("00000000-0000-7000-8000-000000008001",),
        ).fetchone()
        assert context == ("{}",)

    command.downgrade(config, "20260831_0001")
    with sqlite3.connect(database_path) as connection:
        columns = operation_columns(connection)
        assert "feature_id" not in columns
        assert "context" not in columns
        assert "debug_session" not in tables(connection)
        assert "operation_feature_config_draft" not in tables(connection)
        assert connection.execute("SELECT count(*) FROM operation_task").fetchone() == (1,)

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    with sqlite3.connect(database_path) as connection:
        assert tables(connection) <= {"alembic_version"}
