"""Build the allowlisted idlefish publish task for Companion."""

from __future__ import annotations

import re
from typing import Any

XIANYU_PACKAGE = "com.taobao.idlefish"
TEXT_PUBLISH_TOTAL_TIMEOUT_MS = 90_000
MAX_INPUT_LENGTH = 1024

APPROVED_XIANYU_LOCATORS = frozenset(
    {
        "xianyu_home_sell",
        "xianyu_publish_entry",
        "xianyu_publish_page",
        "xianyu_add_image",
        "xianyu_gallery_next",
        "xianyu_description",
        "xianyu_price",
        "xianyu_price_sheet",
        "xianyu_price_confirm",
        "xianyu_composer_done",
        "xianyu_shipping",
        "xianyu_location",
        "xianyu_publish_button",
    }
)

TEXT_PUBLISH_LOCATORS = (
    "xianyu_home_sell",
    "xianyu_publish_entry",
    "xianyu_publish_page",
    "xianyu_description",
    "xianyu_price",
)


def build_text_publish_steps(*, description: str, price: str, auto_publish: bool = False) -> list[dict[str, Any]]:
    """Return allowlisted steps that fill the idlefish publish form.

    Args:
        description: Product description text
        price: Product price
        auto_publish: If True, automatically click the publish button after filling the form
    """

    description = _require_input("description", description)
    price = _require_input("price", price)
    steps: list[dict[str, Any]] = [
        {
            "stepId": "find-home-sell",
            "action": "ui.find",
            "locatorRef": "xianyu_home_sell",
            "timeoutMs": 8_000,
        },
        {
            "stepId": "open-sell",
            "action": "ui.tap",
            "locatorRef": "xianyu_home_sell",
            "postconditionLocatorRef": "xianyu_publish_entry",
            "timeoutMs": 8_000,
        },
        {
            "stepId": "open-publish",
            "action": "ui.tap",
            "locatorRef": "xianyu_publish_entry",
            "postconditionLocatorRef": "xianyu_publish_page",
            "timeoutMs": 8_000,
        },
        {
            "stepId": "wait-publish-page",
            "action": "ui.wait",
            "locatorRef": "xianyu_publish_page",
            "condition": "EXISTS",
            "pollMs": 200,
            "timeoutMs": 8_000,
        },
        {
            "stepId": "fill-description",
            "action": "ui.input",
            "locatorRef": "xianyu_description",
            "value": description,
            "replace": True,
            "timeoutMs": 8_000,
        },
        {
            "stepId": "fill-price",
            "action": "ui.input",
            "locatorRef": "xianyu_price",
            "value": price,
            "replace": True,
            "timeoutMs": 8_000,
        },
        {
            "stepId": "capture-form",
            "action": "ui.screenshot",
            "label": "xianyu_publish_form",
            "timeoutMs": 15_000,
        },
    ]
    
    if auto_publish:
        # Add publish button click and confirmation
        steps.extend([
            {
                "stepId": "click-publish",
                "action": "ui.tap",
                "locatorRef": "xianyu_publish_button",
                "timeoutMs": 5_000,
            },
            {
                "stepId": "wait-publish-complete",
                "action": "ui.wait",
                "locatorRef": "xianyu_home_sell",
                "condition": "EXISTS",
                "pollMs": 500,
                "timeoutMs": 15_000,
            },
            {
                "stepId": "capture-success",
                "action": "ui.screenshot",
                "label": "xianyu_publish_success",
                "timeoutMs": 5_000,
            },
            {
                "stepId": "mark-published",
                "action": "run.log",
                "level": "INFO",
                "messageCode": "XIANYU_PUBLISH_SUCCESS",
                "timeoutMs": 1_000,
            },
        ])
    else:
        steps.append({
            "stepId": "mark-ready",
            "action": "run.log",
            "level": "INFO",
            "messageCode": "XIANYU_PUBLISH_FORM_READY",
            "timeoutMs": 1_000,
        })
    

    used = {str(step.get("locatorRef")) for step in steps if "locatorRef" in step}
    used.update(
        str(step["postconditionLocatorRef"]) for step in steps if "postconditionLocatorRef" in step
    )
    unknown = {
        locator
        for locator in used
        if locator not in APPROVED_XIANYU_LOCATORS
        and not re.fullmatch(r"xianyu_gallery_select_(?:[0-9]|[1-4][0-9])", locator)
    }
    if unknown:
        raise ValueError(f"publish recipe used unknown locators: {sorted(unknown)}")
    return steps


def listing_copy_from_parameters(parameters: dict[str, Any]) -> tuple[str, str]:
    page = parameters.get("pageParameters")
    page_values = page if isinstance(page, dict) else {}
    description = parameters.get("listingBody") or page_values.get("listingBody")
    price = parameters.get("price") or page_values.get("listingPrice") or page_values.get("price")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("listing description is required")
    if not isinstance(price, str) or not price.strip():
        raise ValueError("listing price is required")
    return description, price


def build_text_publish_task(
    device_id: str,
    *,
    description: str,
    price: str,
    media_asset_ids: list[str] | None = None,
    delivery_id: str | None = None,
    auto_publish: bool = True,
) -> dict[str, Any]:
    """Build a complete Xianyu publish task.
    
    Args:
        device_id: Target device ID
        description: Product description
        price: Product price
        media_asset_ids: List of media asset IDs to upload (optional)
        delivery_id: Media delivery ID (required if media_asset_ids provided)
        auto_publish: If True, automatically click publish button (default: True)
    """
    if media_asset_ids is not None:
        is_valid = (
            media_asset_ids
            and len(media_asset_ids) <= 50
            and len(set(media_asset_ids)) == len(media_asset_ids)
        )
        if not is_valid:
            raise ValueError("media_asset_ids must be unique and contain 1 to 50 items")
        if not delivery_id:
            raise ValueError("delivery_id is required when media assets are supplied")
    
    steps = build_text_publish_steps(description=description, price=price, auto_publish=auto_publish)
    
    # Insert media upload steps after opening publish page (before filling description)
    if media_asset_ids:
        media_steps = [
            {
                "stepId": "open-media-picker",
                "action": "ui.tap",
                "locatorRef": "xianyu_add_image",
                "postconditionLocatorRef": "xianyu_gallery_select_0",
                "timeoutMs": 8_000,
            },
            *[
                {
                    "stepId": f"select-media-{index}",
                    "action": "ui.tap",
                    "locatorRef": f"xianyu_gallery_select_{index}",
                    "timeoutMs": 5_000,
                }
                for index in range(len(media_asset_ids))
            ],
            {
                "stepId": "confirm-media-selection",
                "action": "ui.tap",
                "locatorRef": "xianyu_gallery_next",
                "postconditionLocatorRef": "xianyu_publish_page",
                "timeoutMs": 8_000,
            },
        ]
        # Insert after "wait-publish-page" step (index 4)
        steps[4:4] = media_steps
    
    total = sum(int(step["timeoutMs"]) for step in steps)
    if total > 900_000:
        raise ValueError("publish step timeouts exceed the task budget")
    
    task = {
        "deviceId": device_id,
        "targetPackage": XIANYU_PACKAGE,
        "totalTimeoutMs": max(TEXT_PUBLISH_TOTAL_TIMEOUT_MS, total),
        "steps": steps,
    }
    if media_asset_ids is not None:
        task["mediaDelivery"] = {"deliveryId": delivery_id, "assetIds": media_asset_ids}
    return task


def _require_input(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    if "\x00" in value:
        raise ValueError(f"{name} cannot contain NUL")
    if len(value) > MAX_INPUT_LENGTH:
        raise ValueError(f"{name} exceeds {MAX_INPUT_LENGTH} characters")
    return value
