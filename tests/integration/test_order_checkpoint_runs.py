"""Checkpoint counters belong to one collection run, not the device lifetime."""

from test_fleet_orders_pagination import _count_pages, _order, _screens, _setup_device
from test_p14_recipe_versions import api, isolated_postgres, pg_url  # noqa: F401


async def test_first_screen_gap_is_rejected_without_creating_checkpoint(api):  # noqa: F811
    client, app = api
    _, auth = await _setup_device(client, "first-run-gap")
    response = await _screens(client, auth, screen=3, rows=[_order("gap")])
    assert response.status_code == 409, response.text
    assert await _count_pages(app) == 0
    checkpoint = await client.get(
        "/companion/v2/orders/checkpoint", headers=auth, params={"direction": "SOLD"}
    )
    assert checkpoint.status_code == 404
    first = await _screens(client, auth, rows=[_order("first")])
    assert first.status_code == 201
    assert first.json()["accepted"] == 1


async def test_new_run_resets_progress_and_rejects_skipping_its_second_screen(api):  # noqa: F811
    client, app = api
    _, auth = await _setup_device(client, "new-run-gap")
    for screen in range(1, 4):
        response = await _screens(
            client, auth, run="run-A", screen=screen, rows=[_order(f"old-{screen}")]
        )
        assert response.status_code == 201
    assert response.json()["checkpoint"]["seenKeys"] == 3

    first = await _screens(client, auth, run="run-B", rows=[_order("old-1"), _order("new-1")])
    assert first.status_code == 201
    checkpoint = first.json()["checkpoint"]
    assert checkpoint["runKey"] == "run-B"
    assert checkpoint["lastScreen"] == 1
    assert checkpoint["seenKeys"] == 1

    gap = await _screens(client, auth, run="run-B", screen=3, rows=[_order("new-3")])
    assert gap.status_code == 409, gap.text
    assert await _count_pages(app) == 4

    second = await _screens(client, auth, run="run-B", screen=2, rows=[_order("new-2")])
    assert second.status_code == 201
    assert second.json()["checkpoint"]["lastScreen"] == 2
    assert second.json()["checkpoint"]["seenKeys"] == 2


async def test_historical_first_page_replay_does_not_reset_current_run(api):  # noqa: F811
    client, app = api
    _, auth = await _setup_device(client, "historical-run-replay")
    for run in ("run-A", "run-B"):
        for screen in (1, 2):
            response = await _screens(
                client, auth, run=run, screen=screen, rows=[_order(f"{run}-{screen}")]
            )
            assert response.status_code == 201
    stored = await client.get(
        "/companion/v2/orders/checkpoint", headers=auth, params={"direction": "SOLD"}
    )
    assert stored.status_code == 200
    expected = stored.json()
    for run in ("run-A", "run-B"):
        replay = await _screens(client, auth, run=run, rows=[_order(f"{run}-1")])
        assert replay.status_code == 200
        assert replay.json()["replayed"] is True
        assert replay.json()["checkpoint"] == expected
    assert await _count_pages(app) == 4
