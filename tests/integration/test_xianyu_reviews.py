"""P34 auto-review (xy-review/20260921): the frozen xianyu.review_orders.steps.v1
task shape gate — navigation taps -> one xianyu.reviewOrders loop -> screenshot
-> closing run.log — plus the dryRun/maxOrders/comment schema bounds."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.db import MobileTaskRow
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from test_platform_tasks import create_direct_device, identity

XIANYU = "com.taobao.idlefish"
REVIEW_COMMAND = "xianyu.review_orders.steps.v1"


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


def _review_steps(
    *,
    max_orders: int = 10,
    comment: str = "宝贝很好，交易愉快！",
    dry_run: bool = True,
) -> list[dict[str, Any]]:
    return [
        {
            "stepId": "open-profile",
            "action": "ui.tap",
            "locatorRef": "xianyu_profile_tab",
            "timeoutMs": 30_000,
        },
        {
            "stepId": "open-sold",
            "action": "ui.tap",
            "locatorRef": "xianyu_order_list_sold",
            "timeoutMs": 30_000,
        },
        {
            "stepId": "open-pending",
            "action": "ui.tap",
            "locatorRef": "xianyu_orders_tab_pending",
            "timeoutMs": 30_000,
        },
        {
            "stepId": "review-all",
            "action": "xianyu.reviewOrders",
            "timeoutMs": 300_000,
            "maxOrders": max_orders,
            "comment": comment,
            "dryRun": dry_run,
        },
        {
            "stepId": "shot",
            "action": "ui.screenshot",
            "timeoutMs": 15_000,
            "label": "xianyu_review",
        },
        {
            "stepId": "done",
            "action": "run.log",
            "timeoutMs": 1_000,
            "level": "INFO",
            "messageCode": "XIANYU_REVIEW_DONE",
        },
    ]


async def _create_raw_task(
    client: httpx.AsyncClient, device: str, steps: list[dict[str, Any]], key: str
) -> httpx.Response:
    return await client.post(
        "/api/v1/mobile/tasks",
        headers={**identity(), "Idempotency-Key": key},
        json={
            "deviceId": device,
            "targetPackage": XIANYU,
            "totalTimeoutMs": 500_000,
            "steps": steps,
        },
    )


async def test_review_shape_gate(api):
    client, app = api
    device = await create_direct_device(client, "review-shape-gate")
    valid = await _create_raw_task(client, device, _review_steps(), "review-shape-ok")
    assert valid.status_code == 201, valid.text
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, valid.json()["taskId"])
        assert row.command_type == REVIEW_COMMAND

    mutations: dict[str, Callable[[], list[dict[str, Any]]]] = {
        "review_twice": lambda: [
            *_review_steps()[:4],
            {**_review_steps()[3], "stepId": "review-again"},
            *_review_steps()[4:],
        ],
        "missing_screenshot": lambda: _review_steps()[:4] + [_review_steps()[5]],
        "wrong_pending_nav": lambda: [
            *_review_steps()[:2],
            {**_review_steps()[2], "locatorRef": "xianyu_messages_tab"},
            *_review_steps()[3:],
        ],
        "extra_tap": lambda: [
            *_review_steps()[:3],
            {
                "stepId": "detour",
                "action": "ui.tap",
                "locatorRef": "xianyu_messages_tab",
                "timeoutMs": 8_000,
            },
            *_review_steps()[3:],
        ],
        "wrong_log_code": lambda: [
            *_review_steps()[:5],
            {**_review_steps()[5], "messageCode": "XIANYU_COLLECT_ORDERS_DONE"},
        ],
        "max_orders_over": lambda: [
            *_review_steps()[:3],
            {**_review_steps()[3], "maxOrders": 51},
            *_review_steps()[4:],
        ],
        "comment_empty": lambda: [
            *_review_steps()[:3],
            {**_review_steps()[3], "comment": ""},
            *_review_steps()[4:],
        ],
        "screenshot_before_review": lambda: [
            _review_steps()[0],
            _review_steps()[1],
            _review_steps()[2],
            _review_steps()[4],
            _review_steps()[3],
            _review_steps()[5],
        ],
    }
    for name, build in mutations.items():
        response = await _create_raw_task(client, device, build(), f"review-shape-bad-{name}")
        assert response.status_code == 422, f"{name}: {response.text}"


async def test_review_schema_bounds(api):
    client, _app = api
    device = await create_direct_device(client, "review-schema-bounds")
    # timeoutMs over the 900s loop-scale cap is rejected by the schema.
    over = await _create_raw_task(
        client,
        device,
        [
            *_review_steps()[:3],
            {**_review_steps()[3], "timeoutMs": 900_001},
            *_review_steps()[4:],
        ],
        "review-timeout-over",
    )
    assert over.status_code == 422, over.text
    # comment over 200 characters is rejected by the schema.
    long_comment = await _create_raw_task(
        client,
        device,
        [
            *_review_steps()[:3],
            {**_review_steps()[3], "comment": "赞" * 201},
            *_review_steps()[4:],
        ],
        "review-comment-long",
    )
    assert long_comment.status_code == 422, long_comment.text


async def test_review_dry_run_real_mode_both_accepted(api):
    client, app = api
    device = await create_direct_device(client, "review-dryrun-modes")
    dry = await _create_raw_task(client, device, _review_steps(dry_run=True), "review-dry-true")
    assert dry.status_code == 201, dry.text
    real = await _create_raw_task(
        client, device, _review_steps(dry_run=False, max_orders=3), "review-dry-false"
    )
    assert real.status_code == 201, real.text
    async with app.state.database.unit_of_work() as session:
        for task_id in (dry.json()["taskId"], real.json()["taskId"]):
            row = await session.get(MobileTaskRow, task_id)
            assert row.command_type == REVIEW_COMMAND
