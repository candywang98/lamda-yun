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
    "xianyu.publish_listing.v1": _package(
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
    ),
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
