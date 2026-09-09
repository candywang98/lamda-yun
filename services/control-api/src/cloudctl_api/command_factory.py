"""T077 catalog factory: page fields → typed CommandV1 parameters.

Recipes are not required. Only production-enabled command types can be minted
for claim. Catalogued but unwired operations fail closed instead of emitting
legacy steps or unknown CommandV1 types.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .builtin_recipes import OPEN_ONLY_COMMAND_TYPES
from .command_v1 import (
    COMMAND_PACKAGES,
    CommandType,
    EmptyParams,
    XianyuCollectOrdersParams,
    XianyuPublishListingParams,
    XiaohongshuPublishNoteParams,
    _typed_parameters,
)

PARAMETER_MODELS = {
    "xianyu.publish_listing.v1": XianyuPublishListingParams,
    "xianyu.collect_orders.v1": XianyuCollectOrdersParams,
    "xiaohongshu.publish_note.v1": XiaohongshuPublishNoteParams,
    "device.probe_capabilities.v1": EmptyParams,
}

FIELD_MAP_CANDIDATES = (
    Path(__file__).resolve().with_name("field-map.json"),
    Path(__file__).resolve().parents[4] / "docs" / "phase1" / "field-map.json",
)
CONSTRAINT_FIELDS = frozenset({"app=main"})
COMMON_TASK_FIELDS = frozenset(
    {
        "deviceIds",
        "deviceId",
        "accountId",
        "expectedBindingVersion",
        "schedule",
        "intervalSeconds",
        "allocation",
        "formMode",
        "addressMode",
        "descPool",
        "watermark",
        "productIds",
        "productId",
        "mediaAssetIds",
        "listingBody",
        "price",
        "title",
        "body",
        "tags",
        "role",
        "limit",
    }
)

PRODUCTION_ALIASES: dict[str, CommandType] = {
    "xianyu.publish_goods": "xianyu.publish_listing.v1",
    "xianyu.publish_listing.v1": "xianyu.publish_listing.v1",
    "xianyu.collect_orders.v1": "xianyu.collect_orders.v1",
    "xiaohongshu.publish_note.v1": "xiaohongshu.publish_note.v1",
    "xiaohongshu.publish_note": "xiaohongshu.publish_note.v1",
    "device.probe_capabilities.v1": "device.probe_capabilities.v1",
}

EXTRA_OPERATIONS = {
    "red-tasks-01": {
        "id": "red-tasks-01",
        "title": "发布笔记",
        "page": "XiaohongshuPublishNoteView",
        "commandType": "xiaohongshu.publish_note.v1",
        "status": "mapped",
        "fields": ["deviceIds", "title", "body", "tags", "mediaAssetIds"],
    },
    "device-probe": {
        "id": "device-probe",
        "title": "设备能力探测",
        "page": "DeviceProbeView",
        "commandType": "device.probe_capabilities.v1",
        "status": "mapped",
        "fields": ["deviceIds"],
    },
}


def _load_field_map() -> dict[str, Any]:
    for path in FIELD_MAP_CANDIDATES:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError("field-map.json was not found next to the factory or under docs/phase1")


def xianyu_operations() -> list[dict[str, Any]]:
    operations = list(_load_field_map()["operations"])
    if len(operations) != 31:
        raise ValueError("field-map must contain exactly 31 xianyu operations")
    ids = [item["id"] for item in operations]
    if ids != [f"xy-tasks-{index:02d}" for index in range(1, 32)]:
        raise ValueError("xianyu operation ids drifted from xy-tasks-01..31")
    return operations


def operation_spec(operation_id: str) -> dict[str, Any]:
    extras = EXTRA_OPERATIONS.get(operation_id)
    if extras:
        return extras
    for item in xianyu_operations():
        if item["id"] == operation_id:
            return item
    raise ValueError(f"unknown operationId: {operation_id}")


def production_command_type(catalog_command_type: str | None) -> CommandType | None:
    if not catalog_command_type:
        return None
    return PRODUCTION_ALIASES.get(catalog_command_type)


def _allowed_fields(spec: dict[str, Any]) -> set[str]:
    declared = {field for field in (spec.get("fields") or []) if field not in CONSTRAINT_FIELDS}
    return declared | COMMON_TASK_FIELDS


def _reject_unknown_and_forbidden(spec: dict[str, Any], parameters: dict[str, Any]) -> None:
    from .command_v1 import FORBIDDEN_KEYS

    for key in parameters:
        lowered = key.lower()
        if any(fragment in lowered for fragment in FORBIDDEN_KEYS):
            raise ValueError("command contains unauthorized execution fields")
    allowed = _allowed_fields(spec)
    unknown = sorted(key for key in parameters if key not in allowed)
    if unknown:
        raise ValueError(f"unknown operation fields: {', '.join(unknown)}")


def mint_operation_command(operation_id: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = operation_spec(operation_id)
    payload = dict(parameters or {})
    _reject_unknown_and_forbidden(spec, payload)
    if spec.get("status") != "mapped":
        raise ValueError(
            spec.get("reason") or f"{operation_id} is {spec.get('status')} and cannot mint a production command"
        )
    catalog_type = spec.get("commandType")
    command_type = production_command_type(catalog_type if isinstance(catalog_type, str) else None)
    if command_type is None:
        raise ValueError(
            f"{operation_id} is catalogued but not enabled for production CommandV1 claim"
        )
    model = PARAMETER_MODELS[command_type]
    aliases = {(field.alias or name) for name, field in model.model_fields.items()}
    filtered = {key: value for key, value in payload.items() if key in aliases}
    typed = _typed_parameters(command_type, filtered)
    package = COMMAND_PACKAGES[command_type]
    return {
        "operationId": operation_id,
        "commandType": command_type,
        "parameters": typed,
        "targetPackage": package,
        "openOnly": command_type in OPEN_ONLY_COMMAND_TYPES,
        "catalogCommandType": catalog_type,
    }
