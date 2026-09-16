"""Frozen APK-local Recipe packages referenced by CommandV1.

These are not a published catalog. P14 still owns signed rollout. Claim and
Companion both pin the same versionId+sha256 so a phone can load the matching
local graph without turning signature verification off.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

_ENGINE_MIN_VERSION = 1


def _canonical_recipe_bytes(package: dict[str, Any]) -> bytes:
    body = {
        "apiVersion": package["apiVersion"],
        "kind": package["kind"],
        "manifest": {key: value for key, value in package["manifest"].items() if key != "hash"},
        "graph": package["graph"],
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _freeze(package: dict[str, Any]) -> dict[str, Any]:
    frozen = json.loads(json.dumps(package))
    frozen["manifest"]["hash"] = hashlib.sha256(_canonical_recipe_bytes(frozen)).hexdigest()
    return frozen


def _package(
    *,
    recipe_id: str,
    platform: str,
    app: str,
    command_type: str,
    states: list[dict[str, Any]],
    start_state_id: str,
    commit_action_id: str | None = None,
) -> dict[str, Any]:
    graph: dict[str, Any] = {
        "startStateId": start_state_id,
        "maxIterations": 8,
        "maxDurationMs": 30_000,
        "states": states,
    }
    if commit_action_id:
        graph["commitActionId"] = commit_action_id
    return _freeze(
        {
            "apiVersion": "cloudctl.recipe/v1",
            "kind": "LocalRecipePackage",
            "manifest": {
                "id": recipe_id,
                "version": "1.0.0",
                "hash": "0" * 64,
                "signingKeyId": "builtin-phase1",
                "minEngineVersion": _ENGINE_MIN_VERSION,
                "platform": platform,
                "app": app,
                "commandTypes": [command_type],
            },
            "graph": graph,
            "signature": {
                "algorithm": "Ed25519",
                "keyId": "builtin-phase1",
                "digest": "hash-pinned-builtin",
            },
        }
    )


# B05 (K05 platform-recipe/v1 §4 open-only): the minimal xianyu publish graph.
# Flow mirrors the frozen dispatch-xianyu steps family (tapsPublish=false) and
# stops at the confirm point — the checkpoint state is terminal WAITING_USER and
# the graph contains no publish/submit action of any kind (xianyu_publish_button
# is never referenced; real submission stays behind Q02 pre-protection +
# per-object authorization). Media selection is expressed by the single "media"
# state: the companion engine expands it to the ordered tile taps
# xianyu_gallery_select_1..N (tile 0 is the camera shutter and is never
# referenced; mediaDelivery item order == download/export order == tile order).
# Task values are bound at execution time from CommandV1 parameters
# (xianyu_description <- listingBody, xianyu_price <- price); the graph bytes
# stay parameter-free so the hash is stable.
_XIANYU_PUBLISH_OPEN_ONLY_STATES: list[dict[str, Any]] = [
    {
        "stateId": "wait-home",
        "action": "wait",
        "locatorRef": "xianyu_home_sell",
        "onSuccess": "open-sell",
        "onFailure": "FAILED",
    },
    {
        "stateId": "open-sell",
        "action": "tap",
        "locatorRef": "xianyu_home_sell",
        "postcondition": "xianyu_publish_entry",
        "onSuccess": "open-publish",
        "onFailure": "FAILED",
    },
    {
        "stateId": "open-publish",
        "action": "tap",
        "locatorRef": "xianyu_publish_entry",
        "postcondition": "xianyu_publish_page",
        "onSuccess": "await-form",
        "onFailure": "FAILED",
    },
    {
        "stateId": "await-form",
        "action": "wait",
        "locatorRef": "xianyu_publish_page",
        "onSuccess": "select-media",
        "onFailure": "FAILED",
    },
    {
        "stateId": "select-media",
        "action": "media",
        "locatorRef": "xianyu_add_image",
        "onSuccess": "fill-description",
        "onFailure": "FAILED",
    },
    {
        "stateId": "fill-description",
        "action": "input",
        "locatorRef": "xianyu_description",
        "valueRef": "listingBody",
        "onSuccess": "confirm-description",
        "onFailure": "FAILED",
    },
    {
        "stateId": "confirm-description",
        "action": "tap",
        "locatorRef": "xianyu_composer_done",
        "onSuccess": "await-price",
        "onFailure": "FAILED",
    },
    {
        "stateId": "await-price",
        "action": "wait",
        "locatorRef": "xianyu_price",
        "onSuccess": "fill-price",
        "onFailure": "FAILED",
    },
    {
        "stateId": "fill-price",
        "action": "input",
        "locatorRef": "xianyu_price",
        "valueRef": "price",
        "onSuccess": "capture-confirm-point",
        "onFailure": "FAILED",
    },
    {
        "stateId": "capture-confirm-point",
        "action": "extract",
        "onSuccess": "await-confirm",
        "onFailure": "FAILED",
    },
    {
        "stateId": "await-confirm",
        "action": "checkpoint",
        "onSuccess": "WAITING_USER",
        "onPause": "WAITING_USER",
        "terminal": True,
    },
]

_XIANYU_PUBLISH_OPEN_ONLY = _package(
    recipe_id="recipe-xianyu-publish-2",
    platform="xianyu",
    app="com.taobao.idlefish",
    command_type="xianyu.publish_listing.v1",
    start_state_id="wait-home",
    states=_XIANYU_PUBLISH_OPEN_ONLY_STATES,
)
_XIANYU_PUBLISH_OPEN_ONLY["graph"]["maxIterations"] = 40
_XIANYU_PUBLISH_OPEN_ONLY["graph"]["maxDurationMs"] = 600_000
_XIANYU_PUBLISH_OPEN_ONLY = _freeze(_XIANYU_PUBLISH_OPEN_ONLY)

# Byte-frozen v1 open-only stub (hash a2331b80…). Tasks claimed before the v2
# graph pinned this exact package; their pins resolve on the phone from the
# APK-local literal, and the server keeps the frozen bytes here for hash
# audit/verification. New claims of xianyu.publish_listing.v1 resolve the v2
# graph above (family-A first-claim pin, K05 §3).
_LEGACY_XIANYU_PUBLISH_OPEN_ONLY = _package(
    recipe_id="recipe-xianyu-publish-1",
    platform="xianyu",
    app="com.taobao.idlefish",
    command_type="xianyu.publish_listing.v1",
    start_state_id="open-only",
    states=[
        {
            "stateId": "open-only",
            "action": "checkpoint",
            "onSuccess": "WAITING_USER",
            "onPause": "WAITING_USER",
            "terminal": True,
        }
    ],
)

LEGACY_BUILTIN_PACKAGES: dict[str, dict[str, Any]] = {
    "recipe-xianyu-publish-1": _LEGACY_XIANYU_PUBLISH_OPEN_ONLY,
}

BUILTIN_RECIPES: dict[str, dict[str, Any]] = {
    "device.probe_capabilities.v1": _package(
        recipe_id="recipe-device-probe-1",
        platform="companion",
        app="com.company.cloudctl.companion",
        command_type="device.probe_capabilities.v1",
        start_state_id="probe",
        states=[
            {
                "stateId": "probe",
                "action": "log",
                "onSuccess": "SUCCEEDED",
                "terminal": True,
            }
        ],
    ),
    "xianyu.collect_orders.v1": _package(
        recipe_id="recipe-xianyu-collect-1",
        platform="xianyu",
        app="com.taobao.idlefish",
        command_type="xianyu.collect_orders.v1",
        start_state_id="collect",
        states=[
            {
                "stateId": "collect",
                "action": "log",
                "onSuccess": "SUCCEEDED",
                "terminal": True,
            }
        ],
    ),
    "xianyu.publish_listing.v1": _XIANYU_PUBLISH_OPEN_ONLY,
    "xiaohongshu.publish_note.v1": _package(
        recipe_id="recipe-xhs-note-1",
        platform="xiaohongshu",
        app="com.xingin.xhs",
        command_type="xiaohongshu.publish_note.v1",
        start_state_id="open-only",
        states=[
            {
                "stateId": "open-only",
                "action": "checkpoint",
                "onSuccess": "WAITING_USER",
                "onPause": "WAITING_USER",
                "terminal": True,
            }
        ],
    ),
}

OPEN_ONLY_COMMAND_TYPES = frozenset(
    {
        "xianyu.publish_listing.v1",
        "xiaohongshu.publish_note.v1",
    }
)


def builtin_recipe_ref(command_type: str) -> dict[str, Any]:
    package = BUILTIN_RECIPES[command_type]
    return {
        "versionId": package["manifest"]["id"],
        "sha256": package["manifest"]["hash"],
        "engineMinVersion": package["manifest"]["minEngineVersion"],
    }


def builtin_recipe_package(command_type: str) -> dict[str, Any]:
    return json.loads(json.dumps(BUILTIN_RECIPES[command_type]))
