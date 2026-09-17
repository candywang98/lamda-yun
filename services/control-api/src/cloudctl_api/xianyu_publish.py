"""Build the allowlisted idlefish publish task for Companion.

P10 (fleet-first-20260916.1) grows this module beyond step building: the four
completion boundaries, field-level request validation, publish-target
persistence (separate from task identity) and the serial single-item queue
live here too. Existing exports (``build_text_publish_steps`` /
``build_text_publish_task`` / ``listing_copy_from_parameters``) keep their
signatures — Q03-accepted behavior must not regress.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from cloudctl_domain import Actor
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select

from .auth import current_actor
from .db import (
    JSON,
    AuditEventRow,
    Base,
    Boolean,
    CheckConstraint,
    Database,
    DateTime,
    Integer,
    Mapped,
    MobileTaskRow,
    String,
    TimestampMixin,
    UniqueConstraint,
    mapped_column,
)

XIANYU_PACKAGE = "com.taobao.idlefish"
TEXT_PUBLISH_TOTAL_TIMEOUT_MS = 180_000
MAX_INPUT_LENGTH = 1024

APPROVED_XIANYU_LOCATORS = frozenset(
    {
        "xianyu_home_sell",
        "xianyu_publish_entry",
        "xianyu_publish_page",
        "xianyu_add_image",
        "xianyu_gallery_next",
        "xianyu_crop_done",
        "xianyu_description",
        "xianyu_price",
        "xianyu_price_sheet",
        "xianyu_price_amount",
        "xianyu_price_confirm",
        "xianyu_composer_done",
        "xianyu_shipping",
        "xianyu_location",
        "xianyu_location_page",
        "xianyu_location_saved_0",
        "xianyu_publish_blocked_ack",
        "xianyu_publish_button",
        "xianyu_publish_success",
        "xianyu_draft_discard",
        "xianyu_draft_nosave",
    }
)

TEXT_PUBLISH_LOCATORS = (
    "xianyu_home_sell",
    "xianyu_publish_entry",
    "xianyu_publish_page",
    "xianyu_description",
    "xianyu_composer_done",
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
            "stepId": "wait-description",
            "action": "ui.wait",
            "locatorRef": "xianyu_description",
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
            "timeoutMs": 20_000,
        },
        {
            "stepId": "confirm-description",
            "action": "ui.tap",
            "locatorRef": "xianyu_composer_done",
            "timeoutMs": 5_000,
        },
        {
            "stepId": "wait-price",
            "action": "ui.wait",
            "locatorRef": "xianyu_price",
            "condition": "EXISTS",
            "pollMs": 200,
            "timeoutMs": 12_000,
        },
        {
            "stepId": "fill-price",
            "action": "ui.input",
            "locatorRef": "xianyu_price",
            "value": price,
            "replace": True,
            "timeoutMs": 20_000,
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
                "stepId": "wait-location",
                "action": "ui.wait",
                "locatorRef": "xianyu_location",
                "condition": "EXISTS",
                "pollMs": 200,
                "timeoutMs": 8_000,
            },
            {
                "stepId": "open-location",
                "action": "ui.tap",
                "locatorRef": "xianyu_location",
                "postconditionLocatorRef": "xianyu_location_page",
                "timeoutMs": 8_000,
            },
            {
                "stepId": "select-location",
                "action": "ui.tap",
                "locatorRef": "xianyu_location_saved_0",
                "postconditionLocatorRef": "xianyu_publish_page",
                "timeoutMs": 8_000,
            },
            {
                "stepId": "wait-publish-button",
                "action": "ui.wait",
                "locatorRef": "xianyu_publish_button",
                "condition": "EXISTS",
                "pollMs": 200,
                "timeoutMs": 8_000,
            },
            {
                "stepId": "click-publish",
                "action": "ui.tap",
                "locatorRef": "xianyu_publish_button",
                "timeoutMs": 5_000,
            },
            {
                "stepId": "wait-publish-complete",
                "action": "ui.wait",
                "locatorRef": "xianyu_publish_success",
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
    auto_publish: bool = False,
) -> dict[str, Any]:
    """Build a complete Xianyu publish task.

    Args:
        device_id: Target device ID
        description: Product description
        price: Product price
        media_asset_ids: List of media asset IDs to upload (optional)
        delivery_id: Media delivery ID (required if media_asset_ids provided)
        auto_publish: If True, automatically click publish button. Defaults to
            False (open-only): a human operator confirms submission.
    """
    if media_asset_ids is not None:
        # Gallery tile 0 is the camera shutter, so at most 49 images are
        # selectable (device-verified 2026-09-16; executor enforces 1..49).
        is_valid = (
            media_asset_ids
            and len(media_asset_ids) <= 49
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
                "stepId": "wait-add-image",
                "action": "ui.wait",
                "locatorRef": "xianyu_add_image",
                "condition": "EXISTS",
                "pollMs": 200,
                "timeoutMs": 8_000,
            },
            {
                "stepId": "open-media-picker",
                "action": "ui.tap",
                "locatorRef": "xianyu_add_image",
                "postconditionLocatorRef": "xianyu_gallery_select_0",
                "timeoutMs": 15_000,
            },
            *[
                {
                    "stepId": f"select-media-{index}",
                    "action": "ui.tap",
                    # Idlefish gallery tile 0 is the camera shutter; CloudCtl covers start at 1.
                    "locatorRef": f"xianyu_gallery_select_{index + 1}",
                    "timeoutMs": 5_000,
                }
                for index in range(len(media_asset_ids))
            ],
            {
                "stepId": "confirm-media-selection",
                "action": "ui.tap",
                "locatorRef": "xianyu_gallery_next",
                "timeoutMs": 8_000,
            },
            {
                "stepId": "wait-crop-done",
                "action": "ui.wait",
                "locatorRef": "xianyu_crop_done",
                "condition": "EXISTS",
                "pollMs": 200,
                "timeoutMs": 8_000,
            },
            {
                "stepId": "confirm-crop",
                "action": "ui.tap",
                "locatorRef": "xianyu_crop_done",
                "timeoutMs": 8_000,
            },
        ]
        # Insert after "wait-publish-page" / before description wait.
        insert_at = next(
            index for index, step in enumerate(steps) if step["stepId"] == "wait-description"
        )
        steps[insert_at:insert_at] = media_steps
    
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


# ---------------------------------------------------------------------------
# P10 (fleet-first-20260916.1): completion boundaries — the four ways a
# Xianyu listing publish run can legally finish. The taxonomy is two manual
# bits: whether the price was entered by a human and whether the final
# publish click was done by a human. A run may never be *recorded* at a less
# manual boundary than its evidence shows (downgrade only, never upgrade) —
# that is what ``completion_boundary_envelope`` encodes and what both the
# Android model (features/xianyu/publish/PublishCompletionBoundary.kt) and
# this server side mirror.
# ---------------------------------------------------------------------------

COMPLETION_BOUNDARY_FULL_AUTO = "FULL_AUTO"
COMPLETION_BOUNDARY_AUTO_FILL_HUMAN_PRICE = "AUTO_FILL_HUMAN_PRICE"
COMPLETION_BOUNDARY_AUTO_FILL_HUMAN_COMMIT = "AUTO_FILL_HUMAN_COMMIT"
COMPLETION_BOUNDARY_HUMAN_PRICE_HUMAN_COMMIT = "HUMAN_PRICE_HUMAN_COMMIT"

#: boundary code -> manual bits. Closed vocabulary; unknown codes are
#: rejected (never silently coerced to FULL_AUTO).
COMPLETION_BOUNDARIES: dict[str, dict[str, bool]] = {
    COMPLETION_BOUNDARY_FULL_AUTO: {"humanPrice": False, "humanCommit": False},
    COMPLETION_BOUNDARY_AUTO_FILL_HUMAN_PRICE: {"humanPrice": True, "humanCommit": False},
    COMPLETION_BOUNDARY_AUTO_FILL_HUMAN_COMMIT: {"humanPrice": False, "humanCommit": True},
    COMPLETION_BOUNDARY_HUMAN_PRICE_HUMAN_COMMIT: {"humanPrice": True, "humanCommit": True},
}

#: New publish requests default to the *current production* shape (recipe
#: xianyu-publish-2: the form is machine-filled, the price is entered by a
#: human at the confirmation point). FULL_AUTO is opt-in only.
DEFAULT_COMPLETION_BOUNDARY = COMPLETION_BOUNDARY_AUTO_FILL_HUMAN_PRICE

#: Evidence flags shared with the device-side judge. Missing flags count as
#: False, i.e. the conservative (more manual) side.
EVIDENCE_FLAGS: tuple[str, ...] = (
    "descriptionProof",
    "priceEnteredByMachine",
    "priceHumanConfirmed",
    "commitClickedByMachine",
    "commitHumanConfirmed",
    "successObserved",
    "mediaComplete",
    "requiredFieldsComplete",
)


def _boundary_from_flags(human_price: bool, human_commit: bool) -> str:
    for code, bits in COMPLETION_BOUNDARIES.items():
        if bits["humanPrice"] is bool(human_price) and bits["humanCommit"] is bool(human_commit):
            return code
    raise ValueError("boundary table is not total over the manual bits")


def completion_boundary_envelope(a: str, b: str) -> str:
    """Downgrade lattice: manual bits OR-ed together, never towards automation."""
    left = COMPLETION_BOUNDARIES[a]
    right = COMPLETION_BOUNDARIES[b]
    return _boundary_from_flags(
        left["humanPrice"] or right["humanPrice"],
        left["humanCommit"] or right["humanCommit"],
    )


def required_completion_evidence(boundary: str) -> set[str]:
    """Per-boundary success criteria: which evidence flags must be True to
    record a publish as succeeded at exactly this boundary."""
    bits = COMPLETION_BOUNDARIES[boundary]
    required = {
        "descriptionProof",
        "mediaComplete",
        "requiredFieldsComplete",
        "successObserved",
    }
    required.add("priceHumanConfirmed" if bits["humanPrice"] else "priceEnteredByMachine")
    required.add("commitHumanConfirmed" if bits["humanCommit"] else "commitClickedByMachine")
    return required


def judge_completion_boundary(claimed: str, evidence: dict[str, Any]) -> dict[str, Any]:
    """Judge a finished run: the effective boundary from evidence, the recorded
    boundary (conservative envelope — downgraded only), the missing evidence
    for the recorded boundary, and whether a *success* may be recorded at all.

    Mirrors PublishBoundaryJudge on the device so both sides reach the same
    verdict for the same evidence (P10 dual-side consistency).
    """
    if claimed not in COMPLETION_BOUNDARIES:
        raise ValueError(f"unknown completion boundary: {claimed}")
    flags = {flag: bool(evidence.get(flag, False)) for flag in EVIDENCE_FLAGS}
    evidence_boundary = _boundary_from_flags(
        human_price=not flags["priceEnteredByMachine"],
        human_commit=not flags["commitClickedByMachine"],
    )
    recorded = completion_boundary_envelope(claimed, evidence_boundary)
    missing = sorted(
        flag for flag in required_completion_evidence(recorded) if not flags[flag]
    )
    return {
        "claimed": claimed,
        "evidenceBoundary": evidence_boundary,
        "recorded": recorded,
        "downgraded": recorded != claimed,
        "missingEvidence": missing,
        "successEligible": not missing,
    }


# ---------------------------------------------------------------------------
# P10: field-level request validation. Errors carry a field/loc structure and
# unknown fields are rejected (never silently dropped).
# ---------------------------------------------------------------------------

_PRICE_RE = re.compile(r"^[0-9]+(\.[0-9]{1,2})?$")

QUEUE_ITEM_FIELDS = frozenset(
    {"description", "price", "mediaAssetIds", "deliveryId", "completionBoundary"}
)
QUEUE_REQUEST_FIELDS = frozenset({"deviceId", "accountId", "queueId", "items"})
CONFIRM_REQUEST_FIELDS = frozenset({"decision", "evidence", "platformItemId", "operatorNote"})
REPORT_FAILURE_FIELDS = frozenset({"errorCode", "detail"})


def _issue(loc: list[Any], code: str, message: str) -> dict[str, Any]:
    dotted = ".".join(str(part) for part in loc)
    return {"field": dotted, "loc": loc, "code": code, "message": message}


def _check_unknown_fields(
    payload: dict[str, Any], allowed: frozenset[str], loc: list[Any]
) -> list[dict[str, Any]]:
    return [
        _issue(
            [*loc, name],
            "UNKNOWN_FIELD",
            f"unknown field {name!r}; it is rejected, not dropped",
        )
        for name in sorted(set(payload) - allowed)
    ]


def _require_string(
    value: Any, loc: list[Any], *, min_length: int, max_length: int
) -> list[dict[str, Any]]:
    if not isinstance(value, str) or not value.strip():
        return [_issue(loc, "FIELD_REQUIRED", "a non-empty string is required")]
    if len(value) > max_length:
        return [_issue(loc, "FIELD_TOO_LONG", f"must be at most {max_length} characters")]
    if len(value.strip()) < min_length:
        return [_issue(loc, "FIELD_TOO_SHORT", f"must be at least {min_length} characters")]
    if "\x00" in value:
        return [_issue(loc, "FIELD_INVALID", "must not contain NUL")]
    return []


def _validate_item(payload: Any, loc: list[Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return [_issue(loc, "FIELD_TYPE", "each queue item must be an object")]
    issues: list[dict[str, Any]] = []
    issues += _check_unknown_fields(payload, QUEUE_ITEM_FIELDS, loc)
    description = payload.get("description")
    issues += _require_string(description, [*loc, "description"], min_length=1, max_length=1024)
    price = payload.get("price")
    price_loc = [*loc, "price"]
    if not isinstance(price, str) or not _PRICE_RE.fullmatch(price or ""):
        issues.append(
            _issue(price_loc, "FIELD_PATTERN", "price must match ^[0-9]+(\\.[0-9]{1,2})?$")
        )
    boundary = payload.get("completionBoundary", DEFAULT_COMPLETION_BOUNDARY)
    if boundary not in COMPLETION_BOUNDARIES:
        issues.append(
            _issue(
                [*loc, "completionBoundary"],
                "FIELD_ENUM",
                "must be one of " + ", ".join(sorted(COMPLETION_BOUNDARIES)),
            )
        )
    media = payload.get("mediaAssetIds")
    if media is not None:
        media_loc = [*loc, "mediaAssetIds"]
        if not isinstance(media, list) or not media:
            issues.append(
                _issue(media_loc, "FIELD_MIN_ITEMS", "must be a list of 1 to 49 asset ids")
            )
        elif len(media) > 49:
            issues.append(
                _issue(
                    media_loc,
                    "FIELD_MAX_ITEMS",
                    "at most 49 assets (gallery tile 0 is the shutter)",
                )
            )
        elif any(not isinstance(asset, str) or not asset for asset in media):
            issues.append(
                _issue(
                    media_loc, "FIELD_TYPE", "every asset id must be a non-empty string"
                )
            )
        elif len(set(media)) != len(media):
            issues.append(_issue(media_loc, "FIELD_DUPLICATE", "asset ids must be unique"))
    delivery = payload.get("deliveryId")
    if delivery is not None:
        issues += _require_string(delivery, [*loc, "deliveryId"], min_length=1, max_length=64)
    elif isinstance(media, list) and media:
        issues.append(
            _issue(
                [*loc, "deliveryId"],
                "FIELD_REQUIRED_DEPENDENT",
                "deliveryId is required when mediaAssetIds is supplied",
            )
        )
    return issues


def validate_publish_queue_request(payload: Any) -> list[dict[str, Any]]:
    """Field-level validation of a publish-queue creation request."""
    if not isinstance(payload, dict):
        return [_issue(["body"], "FIELD_TYPE", "request body must be a JSON object")]
    issues: list[dict[str, Any]] = []
    issues += _check_unknown_fields(payload, QUEUE_REQUEST_FIELDS, [])
    issues += _require_string(payload.get("deviceId"), ["deviceId"], min_length=1, max_length=36)
    issues += _require_string(payload.get("accountId"), ["accountId"], min_length=1, max_length=36)
    queue_id = payload.get("queueId")
    if queue_id is not None:
        issues += _require_string(queue_id, ["queueId"], min_length=1, max_length=64)
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        issues.append(_issue(["items"], "FIELD_MIN_ITEMS", "at least one publish item is required"))
    elif len(items) > 50:
        issues.append(_issue(["items"], "FIELD_MAX_ITEMS", "at most 50 items per queue request"))
    else:
        for index, item in enumerate(items):
            issues += _validate_item(item, ["items", index])
    return issues


def validate_confirm_request(payload: Any) -> list[dict[str, Any]]:
    """Field-level validation of a result-confirmation request."""
    if not isinstance(payload, dict):
        return [_issue(["body"], "FIELD_TYPE", "request body must be a JSON object")]
    issues: list[dict[str, Any]] = []
    issues += _check_unknown_fields(payload, CONFIRM_REQUEST_FIELDS, [])
    decision = payload.get("decision")
    if decision not in {"SUCCEEDED", "FAILED"}:
        issues.append(
            _issue(["decision"], "FIELD_ENUM", "decision must be SUCCEEDED or FAILED")
        )
    evidence = payload.get("evidence")
    if evidence is not None:
        if not isinstance(evidence, dict):
            issues.append(
                _issue(
                    ["evidence"], "FIELD_TYPE", "evidence must be an object of boolean flags"
                )
            )
        else:
            issues += _check_unknown_fields(evidence, frozenset(EVIDENCE_FLAGS), ["evidence"])
            for flag in EVIDENCE_FLAGS:
                value = evidence.get(flag)
                if value is not None and not isinstance(value, bool):
                    issues.append(
                        _issue(["evidence", flag], "FIELD_TYPE", "evidence flags must be booleans")
                    )
    platform_item_id = payload.get("platformItemId")
    if platform_item_id is not None:
        issues += _require_string(
            platform_item_id, ["platformItemId"], min_length=1, max_length=64
        )
    operator_note = payload.get("operatorNote")
    if operator_note is not None:
        issues += _require_string(
            operator_note, ["operatorNote"], min_length=1, max_length=2000
        )
    return issues


def validate_report_failure_request(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return [_issue(["body"], "FIELD_TYPE", "request body must be a JSON object")]
    issues: list[dict[str, Any]] = []
    issues += _check_unknown_fields(payload, REPORT_FAILURE_FIELDS, [])
    issues += _require_string(payload.get("errorCode"), ["errorCode"], min_length=3, max_length=80)
    detail = payload.get("detail")
    if detail is not None:
        issues += _require_string(detail, ["detail"], min_length=1, max_length=2000)
    return issues


# ---------------------------------------------------------------------------
# P10: publish-target persistence. The publish target (one listing to place)
# is stored separately from the MobileTask identity: retries mint new tasks
# against the same target, and the platform's external item id lands on the
# target only when the result is confirmed.
# ---------------------------------------------------------------------------

TARGET_PENDING = "PENDING"
TARGET_IN_FLIGHT = "IN_FLIGHT"
TARGET_FAILED_UNCONFIRMED = "FAILED_UNCONFIRMED"
TARGET_SUCCEEDED_CONFIRMED = "SUCCEEDED_CONFIRMED"
TARGET_FAILED_CONFIRMED = "FAILED_CONFIRMED"
TARGET_CANCELLED = "CANCELLED"
TARGET_STATES = frozenset(
    {
        TARGET_PENDING,
        TARGET_IN_FLIGHT,
        TARGET_FAILED_UNCONFIRMED,
        TARGET_SUCCEEDED_CONFIRMED,
        TARGET_FAILED_CONFIRMED,
        TARGET_CANCELLED,
    }
)
#: terminal targets are never re-issued by the serial queue.
TARGET_TERMINAL = frozenset(
    {TARGET_SUCCEEDED_CONFIRMED, TARGET_FAILED_CONFIRMED, TARGET_CANCELLED}
)


class XianyuPublishTargetRow(Base, TimestampMixin):
    __tablename__ = "xianyu_publish_target"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    queue_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(36), nullable=False)
    account_id: Mapped[str] = mapped_column(String(36), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    item: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    claimed_boundary: Mapped[str] = mapped_column(String(48), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    task_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    external_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recorded_boundary: Mapped[str | None] = mapped_column(String(48), nullable=True)
    boundary_downgraded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    judgment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "queue_id", "position", name="uq_xianyu_publish_target_position"
        ),
        CheckConstraint(
            "state IN ('PENDING','IN_FLIGHT','FAILED_UNCONFIRMED',"
            "'SUCCEEDED_CONFIRMED','FAILED_CONFIRMED','CANCELLED')",
            name="ck_xianyu_publish_target_state",
        ),
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _audit(
    session: Any,
    *,
    tenant_id: str,
    actor_id: str,
    action: str,
    target: XianyuPublishTargetRow,
    extra: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEventRow(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            actor_type="operator",
            actor_id=actor_id[:255],
            action=f"xianyu.publish.{action}",
            resource_type="xianyu_publish_target",
            resource_id=target.id,
            request_id=str(uuid.uuid4()),
            device_id=target.device_id,
            result="SUCCEEDED",
            metadata_json={
                "targetId": target.id,
                "queueId": target.queue_id,
                "state": target.state,
                **(extra or {}),
            },
            occurred_at=_now(),
        )
    )


def _fingerprint_item(item: dict[str, Any]) -> dict[str, Any]:
    """Canonical item fields for queue replay identity (deliveryId matters
    only when media is present; the boundary default is normalized so a
    replay of an implicit-default request still matches)."""
    fields = sorted(
        QUEUE_ITEM_FIELDS if item.get("mediaAssetIds") else QUEUE_ITEM_FIELDS - {"deliveryId"}
    )
    return {
        name: item.get(
            name, DEFAULT_COMPLETION_BOUNDARY if name == "completionBoundary" else None
        )
        for name in fields
    }


class XianyuPublishQueueService:
    """Serial single-item publish queue over separately persisted targets."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def create_queue(self, actor: Any, payload: dict[str, Any]) -> dict[str, Any]:
        tenant_id = str(actor.tenant_id)
        queue_id = payload.get("queueId") or str(uuid.uuid4())
        now = _now()
        fingerprint = hashlib.sha256(
            _canonical(
                {
                    "deviceId": payload["deviceId"],
                    "accountId": payload["accountId"],
                    "items": [_fingerprint_item(item) for item in payload["items"]],
                }
            ).encode()
        ).hexdigest()
        async with self.database.unit_of_work() as session:
            existing = list(
                await session.scalars(
                    select(XianyuPublishTargetRow)
                    .where(
                        XianyuPublishTargetRow.tenant_id == tenant_id,
                        XianyuPublishTargetRow.queue_id == queue_id,
                    )
                    .order_by(XianyuPublishTargetRow.position)
                )
            )
            if existing:
                replay = hashlib.sha256(
                    _canonical(
                        {
                            "deviceId": existing[0].device_id,
                            "accountId": existing[0].account_id,
                            "items": [_fingerprint_item(dict(row.item or {})) for row in existing],
                        }
                    ).encode()
                ).hexdigest()
                if replay == fingerprint:
                    return self._queue_view(queue_id, existing, replayed=True)
                from cloudctl_domain import ConflictError

                raise ConflictError(
                    "queueId already exists with different items; pick a new queueId"
                )
            for position, item in enumerate(payload["items"]):
                session.add(
                    XianyuPublishTargetRow(
                        id=str(uuid.uuid4()),
                        tenant_id=tenant_id,
                        queue_id=queue_id,
                        device_id=payload["deviceId"],
                        account_id=payload["accountId"],
                        position=position,
                        item={
                            "description": item["description"],
                            "price": item["price"],
                            "completionBoundary": item.get(
                                "completionBoundary", DEFAULT_COMPLETION_BOUNDARY
                            ),
                            **(
                                {"mediaAssetIds": item["mediaAssetIds"]}
                                if item.get("mediaAssetIds")
                                else {}
                            ),
                            **(
                        {"deliveryId": item["deliveryId"]}
                        if item.get("deliveryId")
                        else {}
                    ),
                        },
                        claimed_boundary=item.get(
                            "completionBoundary", DEFAULT_COMPLETION_BOUNDARY
                        ),
                        state=TARGET_PENDING,
                        task_ids=[],
                        boundary_downgraded=False,
                        judgment={},
                        result={},
                        requested_by=str(actor.user_id),
                        created_at=now,
                    )
                )
        return await self.get_queue(actor, queue_id)

    async def get_queue(self, actor: Any, queue_id: str) -> dict[str, Any]:
        rows = await self._queue_rows(str(actor.tenant_id), queue_id)
        if not rows:
            from cloudctl_domain import NotFoundError

            raise NotFoundError("publish queue was not found")
        return self._queue_view(queue_id, rows)

    async def _queue_rows(self, tenant_id: str, queue_id: str) -> list[XianyuPublishTargetRow]:
        async with self.database.unit_of_work() as session:
            rows = list(
                await session.scalars(
                    select(XianyuPublishTargetRow)
                    .where(
                        XianyuPublishTargetRow.tenant_id == tenant_id,
                        XianyuPublishTargetRow.queue_id == queue_id,
                    )
                    .order_by(XianyuPublishTargetRow.position)
                )
            )
        return rows

    async def next_target(self, actor: Any, queue_id: str) -> dict[str, Any] | None:
        """Serial single-item advance: nothing new is issued while a target is
        IN_FLIGHT; only PENDING (未开始) or FAILED_UNCONFIRMED (未确认失败)
        targets are eligible; confirmed-success targets are never redone."""
        rows = await self._queue_rows(str(actor.tenant_id), queue_id)
        if not rows:
            from cloudctl_domain import NotFoundError

            raise NotFoundError("publish queue was not found")
        if any(row.state == TARGET_IN_FLIGHT for row in rows):
            return None
        for row in rows:
            if row.state in {TARGET_PENDING, TARGET_FAILED_UNCONFIRMED}:
                return self._target_view(row)
        return None

    async def dispatch(
        self, actor: Any, queue_id: str, target_id: str, platform_task_service: Any
    ) -> dict[str, Any]:
        """Mint the MobileTask for a target (publish-target identity is stamped
        into the frozen command payload so device side and server side agree
        on which target this execution belongs to)."""
        # Late import: platform_tasks imports this module (no import cycle).
        from .platform_tasks import PlatformTaskCreate

        async with self.database.unit_of_work() as session:
            row = await self._locked_target(session, str(actor.tenant_id), queue_id, target_id)
            if row.state not in {TARGET_PENDING, TARGET_FAILED_UNCONFIRMED}:
                from cloudctl_domain import ConflictError

                raise ConflictError(
                    f"target is {row.state}; only PENDING or FAILED_UNCONFIRMED can be dispatched"
                )
            item = dict(row.item)
            parameters: dict[str, Any] = {
                "listingBody": item["description"],
                "price": item["price"],
            }
            if item.get("mediaAssetIds"):
                parameters["mediaAssetIds"] = item["mediaAssetIds"]
            body = PlatformTaskCreate.model_validate(
                {
                    "deviceId": row.device_id,
                    "accountId": row.account_id,
                    "commandType": "xianyu.publish_listing.v1",
                    "parameters": parameters,
                    "publishTargetId": row.id,
                    "batchId": row.queue_id,
                    **({"mediaDeliveryId": item["deliveryId"]} if item.get("deliveryId") else {}),
                }
            )
            attempt = len(row.task_ids) + 1
            dispatch_key = f"xianyu-publish:{row.id}:{attempt}"
        views, _created = await platform_task_service.create(actor, dispatch_key, body)
        task_id = str(views[0]["taskId"])
        async with self.database.unit_of_work() as session:
            row = await self._locked_target(session, str(actor.tenant_id), queue_id, target_id)
            task = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if task is not None:
                payload = dict(task.command_payload or {})
                # P10: freeze the claimed completion boundary into the task
                # snapshot so the confirm-time judgment is judged against what
                # was requested, not what is convenient.
                payload["completionBoundary"] = row.claimed_boundary
                payload["snapshotSha256"] = hashlib.sha256(_canonical(payload).encode()).hexdigest()
                task.command_payload = payload
            row.state = TARGET_IN_FLIGHT
            row.task_ids = [*list(row.task_ids), task_id]
            _audit(
                session,
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.user_id),
                action="dispatched",
                target=row,
                extra={"taskId": task_id, "attempt": attempt},
            )
            view = self._target_view(row)
        view["taskId"] = task_id
        return view

    async def report_failure(
        self, actor: Any, queue_id: str, target_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Executor-side failure report: the result is NOT confirmed — the
        target becomes re-issuable (未确认失败) until a confirm settles it."""
        async with self.database.unit_of_work() as session:
            row = await self._locked_target(session, str(actor.tenant_id), queue_id, target_id)
            if row.state != TARGET_IN_FLIGHT:
                from cloudctl_domain import ConflictError

                raise ConflictError("only an IN_FLIGHT target can report a failure")
            row.state = TARGET_FAILED_UNCONFIRMED
            row.result = {
                **dict(row.result or {}),
                "lastFailure": {
                    "errorCode": payload["errorCode"],
                    "detail": payload.get("detail", ""),
                    "taskId": row.task_ids[-1] if row.task_ids else None,
                    "occurredAt": _now().isoformat(),
                },
            }
            _audit(
                session,
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.user_id),
                action="failure_reported",
                target=row,
                extra={"errorCode": payload["errorCode"]},
            )
            return self._target_view(row)

    async def confirm(
        self, actor: Any, queue_id: str, target_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Confirm the result (single source of truth for queue advance).

        The server judges the completion boundary from the claimed boundary +
        evidence envelope: a lower-completion run is recorded at its downgraded
        boundary (never as FULL_AUTO); if even the recorded boundary's success
        criteria are not met, a SUCCEEDED confirmation is refused outright.
        """
        from cloudctl_domain import ConflictError, ValidationError

        decision = payload["decision"]
        evidence = payload.get("evidence") or {}
        platform_item_id = payload.get("platformItemId")
        now = _now()
        async with self.database.unit_of_work() as session:
            row = await self._locked_target(session, str(actor.tenant_id), queue_id, target_id)
            if row.state not in {TARGET_IN_FLIGHT, TARGET_FAILED_UNCONFIRMED}:
                raise ConflictError(
                    f"target is {row.state}; only IN_FLIGHT or FAILED_UNCONFIRMED can be confirmed"
                )
            judgment = judge_completion_boundary(row.claimed_boundary, evidence)
            if decision == "SUCCEEDED":
                if not judgment["successEligible"]:
                    missing = ", ".join(judgment["missingEvidence"])
                    raise ValidationError(
                        "publish success evidence is incomplete for the recorded "
                        f"boundary {judgment['recorded']}; missing: {missing}",
                        fields={
                            flag: "evidence flag required for the recorded boundary"
                            for flag in judgment["missingEvidence"]
                        },
                    )
                if not platform_item_id:
                    raise ValidationError(
                        "confirming a succeeded publish requires platformItemId "
                        "(the platform's external item identity)",
                        fields={"platformItemId": "required when decision is SUCCEEDED"},
                    )
                row.state = TARGET_SUCCEEDED_CONFIRMED
                row.external_item_id = platform_item_id
                row.recorded_boundary = judgment["recorded"]
                row.boundary_downgraded = judgment["downgraded"]
                row.judgment = judgment
                row.result = {
                    **dict(row.result or {}),
                    "outcome": "succeeded",
                    "platformItemId": platform_item_id,
                    "taskId": row.task_ids[-1] if row.task_ids else None,
                    "judgment": judgment,
                }
                row.confirmed_at = now
                task_settle = (
                    "SUCCEEDED",
                    {"outcome": "succeeded", "platformItemId": platform_item_id},
                )
            else:
                row.state = TARGET_FAILED_CONFIRMED
                row.recorded_boundary = judgment["recorded"]
                row.boundary_downgraded = judgment["downgraded"]
                row.judgment = judgment
                row.result = {
                    **dict(row.result or {}),
                    "outcome": "failed",
                    "operatorNote": payload.get("operatorNote", ""),
                    "taskId": row.task_ids[-1] if row.task_ids else None,
                    "judgment": judgment,
                }
                row.confirmed_at = now
                task_settle = (
                    "FAILED",
                    {"outcome": "failed", "operatorNote": payload.get("operatorNote", "")},
                )
            last_task_id = row.task_ids[-1] if row.task_ids else None
            if last_task_id:
                task = await session.get(MobileTaskRow, last_task_id, with_for_update=True)
                if task is not None:
                    # Dual-side consistency: the same target, the same result,
                    # the same recorded boundary land on the MobileTask too.
                    settle_status, settle_result = task_settle
                    task.result = {
                        **dict(task.result or {}),
                        "publishTargetId": row.id,
                        "completionBoundary": judgment["recorded"],
                        "completionBoundaryClaimed": judgment["claimed"],
                        "completionBoundaryDowngraded": judgment["downgraded"],
                        **settle_result,
                    }
                    if task.status not in {"SUCCEEDED", "FAILED"}:
                        task.status = settle_status
                        task.business_state = settle_status
                        task.completed_at = now
            _audit(
                session,
                tenant_id=str(actor.tenant_id),
                actor_id=str(actor.user_id),
                action="confirmed",
                target=row,
                extra={
                    "decision": decision,
                    "recordedBoundary": judgment["recorded"],
                    "downgraded": judgment["downgraded"],
                    "platformItemId": platform_item_id,
                },
            )
            return self._target_view(row)

    async def _locked_target(
        self, session: Any, tenant_id: str, queue_id: str, target_id: str
    ) -> XianyuPublishTargetRow:
        from cloudctl_domain import NotFoundError

        row = await session.get(XianyuPublishTargetRow, target_id, with_for_update=True)
        if row is None or row.tenant_id != tenant_id or row.queue_id != queue_id:
            raise NotFoundError("publish target was not found in this queue")
        return row

    @staticmethod
    def _target_view(row: XianyuPublishTargetRow) -> dict[str, Any]:
        return {
            "targetId": row.id,
            "queueId": row.queue_id,
            "position": row.position,
            "deviceId": row.device_id,
            "accountId": row.account_id,
            "item": dict(row.item or {}),
            "claimedBoundary": row.claimed_boundary,
            "state": row.state,
            "taskIds": list(row.task_ids or []),
            "externalItemId": row.external_item_id,
            "recordedBoundary": row.recorded_boundary,
            "boundaryDowngraded": bool(row.boundary_downgraded),
            "judgment": dict(row.judgment or {}),
            "result": dict(row.result or {}),
            "confirmedAt": row.confirmed_at.isoformat() if row.confirmed_at else None,
        }

    @staticmethod
    def _queue_view(
        queue_id: str, rows: list[XianyuPublishTargetRow], replayed: bool = False
    ) -> dict[str, Any]:
        states = [row.state for row in rows]
        return {
            "queueId": queue_id,
            "deviceId": rows[0].device_id,
            "accountId": rows[0].account_id,
            "replayed": replayed,
            "serialAdvanceBlocked": TARGET_IN_FLIGHT in states,
            "targets": [XianyuPublishQueueService._target_view(row) for row in rows],
        }


# ---------------------------------------------------------------------------
# P10 HTTP surface. Registered in app.py (minimal diff: import + include).
# ---------------------------------------------------------------------------

xianyu_publish_router = APIRouter(prefix="/api/v1/xianyu/publish", tags=["xianyu-publish"])

ActorDep = Annotated[Actor, Depends(current_actor)]


def _queue_service(request: Request) -> XianyuPublishQueueService:
    return XianyuPublishQueueService(request.app.state.database)


def _platform_tasks(request: Request) -> Any:
    return request.app.state.platform_task_service


def _field_problem(request: Request, issues: list[dict[str, Any]]) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "type": "urn:cloudctl:problem:publish_field_validation",
            "title": "Publish request validation failed",
            "status": 422,
            "code": "PUBLISH_FIELD_VALIDATION",
            "correlation_id": getattr(request.state, "request_id", str(uuid.uuid4())),
            "retryable": False,
            # field/loc structure: [{field, loc, code, message}, ...]
            "errors": issues,
        },
        media_type="application/problem+json",
    )


@xianyu_publish_router.post("/queues", status_code=201)
async def create_publish_queue(
    request: Request,
    actor: ActorDep,
    body: dict[str, Any],
) -> Any:
    issues = validate_publish_queue_request(body)
    if issues:
        return _field_problem(request, issues)
    service = _queue_service(request)
    return await service.create_queue(actor, body)


@xianyu_publish_router.get("/queues/{queue_id}")
async def get_publish_queue(request: Request, actor: ActorDep, queue_id: str) -> Any:
    return await _queue_service(request).get_queue(actor, queue_id)


@xianyu_publish_router.post("/queues/{queue_id}/next")
async def next_publish_target(request: Request, actor: ActorDep, queue_id: str) -> Response:
    view = await _queue_service(request).next_target(actor, queue_id)
    if view is None:
        return Response(status_code=204)
    return view


@xianyu_publish_router.post("/queues/{queue_id}/targets/{target_id}/dispatch")
async def dispatch_publish_target(
    request: Request, actor: ActorDep, queue_id: str, target_id: str
) -> Any:
    return await _queue_service(request).dispatch(
        actor, queue_id, target_id, _platform_tasks(request)
    )


@xianyu_publish_router.post("/queues/{queue_id}/targets/{target_id}/report-failure")
async def report_publish_failure(
    request: Request, actor: ActorDep, queue_id: str, target_id: str, body: dict[str, Any]
) -> Any:
    issues = validate_report_failure_request(body)
    if issues:
        return _field_problem(request, issues)
    return await _queue_service(request).report_failure(actor, queue_id, target_id, body)


@xianyu_publish_router.post("/queues/{queue_id}/targets/{target_id}/confirm")
async def confirm_publish_result(
    request: Request, actor: ActorDep, queue_id: str, target_id: str, body: dict[str, Any]
) -> Any:
    issues = validate_confirm_request(body)
    if issues:
        return _field_problem(request, issues)
    return await _queue_service(request).confirm(actor, queue_id, target_id, body)
