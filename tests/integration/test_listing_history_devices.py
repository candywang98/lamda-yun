"""Listing history never conflates identical item keys across physical devices."""

from datetime import UTC, datetime

from cloudctl_api.fleet_listings import FleetListingRow
from sqlalchemy import select
from test_fleet_listings import OTHER_TENANT, _push, _row, _screen
from test_p14_recipe_versions import api, isolated_postgres, pg_url  # noqa: F401
from test_platform_tasks import _enroll, create_direct_device, identity


async def seed_devices(client):
    devices = []
    for index in range(3):
        device = await create_direct_device(client, f"listing-source-{index}")
        auth = await _enroll(client, device, f"listing-source-instance-{index}")
        response = await _push(client, auth, _screen("same-run", 1, [_row("same-title|19900")]))
        assert response.status_code == 201, response.text
        devices.append(device)
    return devices


async def test_history_additive_source_fields_preserve_three_same_key_rows(api):  # noqa: F811
    client, _ = api
    devices = await seed_devices(client)
    response = await client.get("/api/v1/fleet/listings/history", headers=identity())
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len({item["id"] for item in body["items"]}) == 3
    assert {item["deviceId"] for item in body["items"]} == set(devices)
    assert {item["itemKey"] for item in body["items"]} == {"same-title|19900"}
    assert {item["platform"] for item in body["items"]} == {"xianyu"}
    assert all(item["dedupeMarker"] == "MISSING_ID" for item in body["items"])
    for device in devices:
        filtered = await client.get(
            "/api/v1/fleet/listings/history",
            headers=identity(),
            params={"device_id": device},
        )
        assert filtered.json()["total"] == 1
        assert filtered.json()["items"][0]["deviceId"] == device
    foreign = await client.get(
        "/api/v1/fleet/listings/history",
        headers=OTHER_TENANT,
        params={"device_id": devices[0]},
    )
    assert foreign.json() == {"items": [], "total": 0, "nextCursor": None}


async def test_equal_timestamp_and_key_have_stable_uuid_pagination(api):  # noqa: F811
    client, app = api
    await seed_devices(client)
    async with app.state.database.unit_of_work() as session:
        rows = list(await session.scalars(select(FleetListingRow)))
        for row in rows:
            row.last_seen_at = datetime(2026, 9, 26, tzinfo=UTC)
        expected = sorted(row.id for row in rows)
    found = []
    cursor = None
    for index in range(3):
        params = {"limit": 1}
        if cursor is not None:
            params["cursor"] = cursor
        response = await client.get(
            "/api/v1/fleet/listings/history", headers=identity(), params=params
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert len(body["items"]) == 1
        found.append(body["items"][0]["id"])
        cursor = body["nextCursor"]
        assert (cursor is None) == (index == 2)
    assert found == expected
