from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.settings import Settings
from fastapi import FastAPI

TENANT = "00000000-0000-7000-8000-000000000111"
FOREIGN_TENANT = "00000000-0000-7000-8000-000000000999"
USER = "00000000-0000-7000-8000-000000000222"


def headers(roles: str, *, tenant: str = TENANT) -> dict[str, str]:
    return {
        "X-Tenant-Id": tenant,
        "X-User-Id": USER,
        "X-Roles": roles,
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }


def item(spu: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "spuCode": spu,
        "title": f"商品 {spu}",
        "description": "F11 导入测试说明",
        "category": "home",
        "price": "19.90",
        "stock": 3,
        "imageUrls": [],
    }
    row.update(overrides)
    return row


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


@pytest.mark.asyncio
async def test_import_dry_run_reports_rows_without_mutating_then_apply_is_idempotent(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    seed = await client.post(
        "/api/v1/products:import",
        headers=headers("content_editor"),
        json={"items": [item("F11-SEED")]},
    )
    assert seed.status_code == 201, seed.text

    body = {
        "items": [
            item("F11-OK-1"),
            item("F11-SEED"),
            item("F11-DUP"),
            item("F11-DUP", title="重复键第二行"),
        ]
    }
    dry = await client.post(
        "/api/v1/content-io/products:import",
        headers=headers("content_editor"),
        json=body,
    )
    assert dry.status_code == 200, dry.text
    dry_body = dry.json()
    assert dry_body["mode"] == "DRY_RUN"
    assert dry_body["apply"] is False
    assert dry_body["summary"] == {
        "total": 4,
        "importCount": 1,
        "skipExistingCount": 1,
        "errorCount": 2,
    }
    rows = {row["spuCode"]: row for row in dry_body["rows"]}
    assert rows["F11-OK-1"]["status"] == "IMPORT"
    assert rows["F11-SEED"]["status"] == "SKIP_EXISTING"
    assert rows["F11-DUP"]["status"] == "ERROR"
    assert rows["F11-DUP"]["errors"][0]["code"] == "DUPLICATE_IN_FILE"
    assert "importKey" in dry_body

    listing = await client.post(
        "/api/v1/products:filter",
        headers=headers("viewer"),
        json={},
    )
    before_codes = {row["spuCode"] for row in listing.json()}
    assert "F11-OK-1" not in before_codes

    applied = await client.post(
        "/api/v1/content-io/products:import",
        headers=headers("content_editor"),
        json={**body, "apply": True, "importKey": "f11-import-key-1"},
    )
    assert applied.status_code == 200, applied.text
    applied_body = applied.json()
    assert applied_body["mode"] == "APPLY"
    assert applied_body["replayed"] is False
    assert applied_body["summary"]["importCount"] == 1
    imported_id = applied_body["rows"][0]["productId"]
    assert imported_id

    replay = await client.post(
        "/api/v1/content-io/products:import",
        headers=headers("content_editor"),
        json={**body, "apply": True, "importKey": "f11-import-key-1"},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["summary"] == applied_body["summary"]

    again = await client.post(
        "/api/v1/content-io/products:import",
        headers=headers("content_editor"),
        json={**body, "apply": True},
    )
    assert again.status_code == 200, again.text
    assert again.json()["summary"]["importCount"] == 0
    assert again.json()["summary"]["skipExistingCount"] == 2
    assert again.json()["summary"]["errorCount"] == 2

    foreign = await client.post(
        "/api/v1/content-io/products:import",
        headers=headers("content_editor", tenant=FOREIGN_TENANT),
        json={"items": [item("F11-OK-1")]},
    )
    assert foreign.status_code == 200
    assert foreign.json()["summary"]["importCount"] == 1


@pytest.mark.asyncio
async def test_export_is_formula_safe_tenant_scoped_and_round_trips(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    applied = await client.post(
        "/api/v1/content-io/products:import",
        headers=headers("content_editor"),
        json={
            "items": [
                item("F11-EXP-1", title="=SUM(A1:A9)", description="正常说明"),
                item("F11-EXP-2", title="+CMD()", description="@hypermagic\rformula"),
            ],
            "apply": True,
        },
    )
    assert applied.status_code == 200, applied.text

    exported = await client.get("/api/v1/content-io/products:export", headers=headers("viewer"))
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith("text/csv")
    assert "attachment" in exported.headers["content-disposition"]

    parsed = list(csv.reader(io.StringIO(exported.text)))
    assert parsed[0] == [
        "spuCode",
        "title",
        "description",
        "category",
        "price",
        "stock",
        "status",
        "revision",
        "createdAt",
    ]
    by_code = {row[0]: row for row in parsed[1:]}
    assert by_code["F11-EXP-1"][1] == "'=SUM(A1:A9)"
    assert by_code["F11-EXP-2"][1] == "'+CMD()"
    assert "\r" not in by_code["F11-EXP-2"][2]
    assert set(by_code) == {"F11-EXP-1", "F11-EXP-2"}

    foreign_export = await client.get(
        "/api/v1/content-io/products:export",
        headers=headers("viewer", tenant=FOREIGN_TENANT),
    )
    assert foreign_export.status_code == 200
    assert [row for row in csv.reader(io.StringIO(foreign_export.text))][1:] == []

    round_trip = await client.post(
        "/api/v1/content-io/products:import",
        headers=headers("content_editor"),
        json={
            "items": [
                {
                    "spuCode": code,
                    "title": row[1].lstrip("'"),
                    "description": row[2],
                    "category": row[3],
                    "price": row[4],
                    "stock": int(row[5]),
                }
                for code, row in by_code.items()
            ],
            "apply": True,
        },
    )
    assert round_trip.status_code == 200, round_trip.text
    assert round_trip.json()["summary"]["importCount"] == 0
    assert round_trip.json()["summary"]["skipExistingCount"] == 2


@pytest.mark.asyncio
async def test_revision_history_is_immutable_paginated_and_tenant_scoped(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    applied = await client.post(
        "/api/v1/content-io/products:import",
        headers=headers("content_editor"),
        json={"items": [item("F11-REV-1")], "apply": True},
    )
    assert applied.status_code == 200, applied.text
    product_id = applied.json()["rows"][0]["productId"]

    first_page = await client.get(
        f"/api/v1/content-io/products/{product_id}/revisions",
        headers=headers("viewer"),
        params={"limit": 1, "offset": 0},
    )
    assert first_page.status_code == 200, first_page.text
    page = first_page.json()
    assert page["total"] == 1
    assert page["currentRevision"] == 1
    assert page["items"][0]["action"] == "product.imported"
    assert page["items"][0]["revision"] == 1
    assert page["items"][0]["snapshot"]["spuCode"] == "F11-REV-1"
    frozen = page["items"][0]

    updated = await client.put(
        f"/api/v1/products/{product_id}",
        headers=headers("content_editor"),
        json={
            "spuCode": "F11-REV-1",
            "title": "商品 F11-REV-1 改",
            "description": "编辑后说明",
            "category": "home",
            "price": "29.90",
            "stock": 5,
            "mediaAssetIds": [],
            "expectedRevision": 1,
        },
    )
    assert updated.status_code == 200, updated.text

    second_page = await client.get(
        f"/api/v1/content-io/products/{product_id}/revisions",
        headers=headers("viewer"),
        params={"limit": 1, "offset": 0},
    )
    assert second_page.status_code == 200, second_page.text
    history = second_page.json()
    assert history["total"] == 2
    assert history["currentRevision"] == 2
    assert history["items"][0]["action"] == "product.updated"

    older_page = await client.get(
        f"/api/v1/content-io/products/{product_id}/revisions",
        headers=headers("viewer"),
        params={"limit": 1, "offset": 1},
    )
    assert older_page.status_code == 200, older_page.text
    assert older_page.json()["items"][0] == frozen

    forbidden = await client.get(
        f"/api/v1/content-io/products/{product_id}/revisions",
        headers=headers("viewer", tenant=FOREIGN_TENANT),
    )
    assert forbidden.status_code == 404
