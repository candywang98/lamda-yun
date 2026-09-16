from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
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
            "recipe_pin",
            "requested_by",
            "target_package",
            "operation_id",
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


def test_mobile_task_operation_id_updown_is_symmetric(tmp_path: Path) -> None:
    """20260916_0022 (K03 D1): nullable operation_id column + index, reversible.

    task-schedule/v1@20260916.1 §2 ruling D1 persists the field-map catalog
    identity on MobileTaskRow. Existing rows keep NULL (never retro-guessed);
    the downgrade drops the column and index without touching row data.
    """
    database_path = tmp_path / "operation-id-migrations.db"
    config = migration_config(database_path)
    command.upgrade(config, "20260915_0021")

    with sqlite3.connect(database_path) as connection:
        columns = table_columns(connection, "mobile_task")
        assert "operation_id" not in columns
        # SQLite does not enforce the device FK by default, so a legacy
        # mobile_task row can stand in without seeding device/edge_node.
        connection.execute(
            """
            INSERT INTO mobile_task (
                id, tenant_id, device_id, idempotency_key, request_sha256,
                requested_by, target_package, steps, status, attempt,
                last_sequence, result, created_at
            ) VALUES (
                '00000000-0000-7000-8000-00000000a010',
                '00000000-0000-7000-8000-00000000a002',
                '00000000-0000-7000-8000-00000000a001',
                'legacy-op-id-task', 'd' * 64, '00000000-0000-7000-8000-00000000a003',
                'com.taobao.idlefish', '[]', 'QUEUED', 0, 0, '{}',
                '2026-09-15 09:01:00+00:00'
            )
            """
        )
        connection.commit()

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        assert "operation_id" in table_columns(connection, "mobile_task")
        legacy = connection.execute(
            "SELECT operation_id FROM mobile_task WHERE id = ?",
            ("00000000-0000-7000-8000-00000000a010",),
        ).fetchone()
        assert legacy == (None,)
        indexes = {
            name
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'mobile_task'"
            ).fetchall()
        }
        assert "ix_mobile_task_operation_id" in indexes

    command.downgrade(config, "20260915_0021")
    with sqlite3.connect(database_path) as connection:
        assert "operation_id" not in table_columns(connection, "mobile_task")
        indexes = {
            name
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'mobile_task'"
            ).fetchall()
        }
        assert "ix_mobile_task_operation_id" not in indexes
        assert connection.execute("SELECT count(*) FROM mobile_task").fetchone() == (1,)

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        assert "operation_id" in table_columns(connection, "mobile_task")


def test_im_message_delivery_state_backfills_and_downgrades(tmp_path: Path) -> None:
    """20260915_0020: old im_message rows become DELIVERED; up/down is symmetric."""
    database_path = tmp_path / "im-delivery-migrations.db"
    config = migration_config(database_path)
    command.upgrade(config, "20260915_0019")

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO im_thread (
                id, tenant_id, device_id, platform, peer_key, peer_name,
                last_message_at, last_direction, unread_count, created_at, updated_at
            ) VALUES (
                '00000000-0000-7000-8000-000000009001',
                '00000000-0000-7000-8000-000000009002',
                '00000000-0000-7000-8000-000000009003',
                'xianyu', 'buyer_legacy', 'buyer_legacy',
                '2026-09-14 10:00:00+00:00', 'OUT', 0,
                '2026-09-14 10:00:00+00:00', '2026-09-14 10:00:00+00:00'
            )
            """
        )
        for number, direction in ((1, "IN"), (2, "OUT")):
            connection.execute(
                """
                INSERT INTO im_message (
                    id, tenant_id, thread_id, direction, content_type, text_content,
                    occurred_at, dedupe_key, reply_task_id, created_at
                ) VALUES (?, '00000000-0000-7000-8000-000000009002',
                          '00000000-0000-7000-8000-000000009001', ?, 'TEXT', ?,
                          '2026-09-14 10:00:00+00:00', ?, NULL,
                          '2026-09-14 10:00:00+00:00')
                """,
                (
                    f"00000000-0000-7000-8000-00000000901{number}",
                    direction,
                    f"legacy-{number}",
                    f"legacy-dedupe-{number}",
                ),
            )
        connection.commit()

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        assert "delivery_state" in table_columns(connection, "im_message")
        states = connection.execute(
            "SELECT direction, delivery_state FROM im_message ORDER BY id"
        ).fetchall()
        # Conservative backfill: pre-migration rows are treated as delivered.
        assert states == [("IN", "DELIVERED"), ("OUT", "DELIVERED")]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE im_message SET delivery_state = 'LOST' WHERE direction = 'OUT'"
            )
        indexes = {
            name
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'im_message'"
            ).fetchall()
        }
        assert "ix_im_message_reply_task_id" in indexes

    command.downgrade(config, "20260915_0019")
    with sqlite3.connect(database_path) as connection:
        assert "delivery_state" not in table_columns(connection, "im_message")
        assert connection.execute("SELECT count(*) FROM im_message").fetchone() == (2,)

    command.upgrade(config, "head")
