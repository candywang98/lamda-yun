"""Deterministic local-only data for the development Web and Studio loop."""

from __future__ import annotations

from datetime import UTC, datetime

from cloudctl_domain import Role

from .db import Database, DeviceRow, EdgeRow, TenantRow, UserRow

DEVELOPMENT_TENANT_ID = "00000000-0000-7000-8000-000000001111"
DEVELOPMENT_USER_ID = "00000000-0000-7000-8000-000000002206"
DEVELOPMENT_EDGE_ID = "edge-bj-lab"
DEVELOPMENT_DEVICE_ID = "dev-bj-008"


async def seed_development_data(database: Database) -> None:
    """Seed the authorized lab path used by the local Web and Studio clients."""
    now = datetime.now(UTC)
    async with database.unit_of_work() as session:
        if await session.get(TenantRow, DEVELOPMENT_TENANT_ID) is None:
            session.add(
                TenantRow(
                    id=DEVELOPMENT_TENANT_ID,
                    name="CloudCtl Development Demo",
                    created_at=now,
                )
            )
        if await session.get(UserRow, DEVELOPMENT_USER_ID) is None:
            session.add(
                UserRow(
                    id=DEVELOPMENT_USER_ID,
                    tenant_id=DEVELOPMENT_TENANT_ID,
                    oidc_subject="development:device-operator",
                    roles=[Role.DEVICE_OPERATOR.value],
                    disabled=False,
                    created_at=now,
                )
            )
        if await session.get(EdgeRow, DEVELOPMENT_EDGE_ID) is None:
            session.add(
                EdgeRow(
                    id=DEVELOPMENT_EDGE_ID,
                    tenant_id=DEVELOPMENT_TENANT_ID,
                    logical_name=DEVELOPMENT_EDGE_ID,
                    certificate_fingerprint="0" * 64,
                    state="ONLINE",
                    last_seen_at=now,
                    created_at=now,
                )
            )
        if await session.get(DeviceRow, DEVELOPMENT_DEVICE_ID) is None:
            session.add(
                DeviceRow(
                    id=DEVELOPMENT_DEVICE_ID,
                    tenant_id=DEVELOPMENT_TENANT_ID,
                    edge_id=DEVELOPMENT_EDGE_ID,
                    logical_name="beijing-lab-008",
                    android_version="17",
                    lamda_version="10.8",
                    target_app_versions={"com.target": "8.32.1"},
                    capabilities={
                        "debug": [
                            "view.frame",
                            "view.layout",
                            "input.tap",
                            "input.swipe",
                            "input.text",
                            "evidence.capture",
                        ]
                    },
                    labels=["lab", "authorized-debug"],
                    state="MAINTENANCE",
                    maintenance=True,
                    last_seen_at=now,
                    version=1,
                    fencing_counter=0,
                    created_at=now,
                )
            )
