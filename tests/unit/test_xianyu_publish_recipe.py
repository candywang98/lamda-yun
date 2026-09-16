from __future__ import annotations

import json
from pathlib import Path

import pytest
from cloudctl_api.xianyu_publish import (
    APPROVED_XIANYU_LOCATORS,
    TEXT_PUBLISH_LOCATORS,
    XIANYU_PACKAGE,
    build_text_publish_steps,
    build_text_publish_task,
)

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "xianyu-publish-text.example.json"


def test_text_publish_recipe_matches_companion_contract() -> None:
    example = json.loads(CONTRACT.read_text())
    steps = build_text_publish_steps(
        description="自用闲置，功能正常，支持当面交易",
        price="128",
    )
    assert example["targetPackage"] == XIANYU_PACKAGE
    assert example["steps"] == steps
    assert {step["stepId"] for step in steps} == {
        "find-home-sell",
        "open-sell",
        "open-publish",
        "wait-publish-page",
        "wait-description",
        "fill-description",
        "confirm-description",
        "wait-price",
        "fill-price",
        "capture-form",
        "mark-ready",
    }
    assert set(TEXT_PUBLISH_LOCATORS) <= APPROVED_XIANYU_LOCATORS
    used = {step["locatorRef"] for step in steps if "locatorRef" in step}
    assert used <= APPROVED_XIANYU_LOCATORS
    assert "xianyu_add_image" not in used
    assert "xianyu_publish_button" not in used


def test_text_publish_task_wraps_device_and_timeout() -> None:
    task = build_text_publish_task(
        "device-1",
        description="九成新桌面显示器",
        price="599",
    )
    assert task["deviceId"] == "device-1"
    assert task["targetPackage"] == XIANYU_PACKAGE
    assert task["totalTimeoutMs"] >= sum(step["timeoutMs"] for step in task["steps"])
    assert task["steps"][5]["value"] == "九成新桌面显示器"
    assert task["steps"][8]["value"] == "599"


def test_media_publish_task_adds_bounded_gallery_selection_steps() -> None:
    task = build_text_publish_task(
        "device-1",
        description="九成新桌面显示器",
        price="599",
        media_asset_ids=["asset-1", "asset-2"],
        delivery_id="delivery-1",
    )
    selection = [step for step in task["steps"] if step["stepId"].startswith("select-media-")]
    assert [step["locatorRef"] for step in selection] == [
        "xianyu_gallery_select_1",
        "xianyu_gallery_select_2",
    ]
    assert selection[0]["action"] == "ui.tap"
    assert "postconditionLocatorRef" not in selection[0]
    assert task["mediaDelivery"] == {"deliveryId": "delivery-1", "assetIds": ["asset-1", "asset-2"]}
    assert task["steps"].index(selection[0]) < task["steps"].index(
        next(step for step in task["steps"] if step["stepId"] == "fill-description")
    )
    crop = next(step for step in task["steps"] if step["stepId"] == "confirm-crop")
    assert crop["locatorRef"] == "xianyu_crop_done"
    confirm = next(step for step in task["steps"] if step["stepId"] == "confirm-media-selection")
    assert "postconditionLocatorRef" not in confirm
    assert task["steps"].index(crop) < task["steps"].index(
        next(step for step in task["steps"] if step["stepId"] == "fill-description")
    )
    assert next(step for step in task["steps"] if step["stepId"] == "mark-ready")[
        "messageCode"
    ] == "XIANYU_PUBLISH_FORM_READY"
    # Open-only default: no auto-publish tail on the built task.
    assert not any(step["stepId"] == "click-publish" for step in task["steps"])


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"description": " ", "price": "1"}, "description is required"),
        ({"description": "desk", "price": ""}, "price is required"),
        ({"description": "x" * 1025, "price": "1"}, "description exceeds"),
        ({"description": "ok\x00", "price": "1"}, "NUL"),
    ],
)
def test_text_publish_recipe_rejects_empty_or_oversized_copy(
    kwargs: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build_text_publish_steps(**kwargs)
