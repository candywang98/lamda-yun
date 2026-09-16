"""T077 catalog factory: page fields → typed CommandV1 parameters.

Recipes are not required. Only production-enabled command types can be minted
for claim. Catalogued but unwired operations fail closed instead of emitting
legacy steps or unknown CommandV1 types.

A05 (platform-recipe/v1 §4/§6/§7) adds the web business-object minting lane:
Product → xianyu.publish_listing.v1 and ContentRevision →
xiaohongshu.publish_note.v1, each with a stable publishTargetId derived from
the frozen target identity and a fail-closed pre-mint validation matrix.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from .builtin_recipes import OPEN_ONLY_COMMAND_TYPES
from .command_v1 import (
    COMMAND_PACKAGES,
    CommandType,
    EmptyParams,
    RecipeRef,
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


# ---------------------------------------------------------------------------
# A05: web business objects → CommandV1 mint with a stable publishTargetId.
# Frozen refs: contracts/parallel/K05/platform-recipe-v1.md §4 (open-only tier,
# result identity), §6 (media caps/order, deliveryId convention), §7
# (publishTargetId stamped into command_payload).
# ---------------------------------------------------------------------------

# Frozen uuid5 namespace for publish target identity. Never regenerate: two
# independently deployed mints must derive the same id for the same target.
PUBLISH_TARGET_NAMESPACE = uuid.UUID("2b3a7893-01af-4137-8d07-7459ef8785c8")

# The only CommandV1 types web business objects may mint (both are open-only
# in V1; douyin is not opened, wechat runs the server-side publisher lane).
PUBLISH_COMMAND_PLATFORMS: dict[str, str] = {
    "xianyu.publish_listing.v1": "xianyu",
    "xiaohongshu.publish_note.v1": "xiaohongshu",
}

# Platform media caps (K05 §6): xianyu gallery covers tiles 1..50, xhs 18.
PUBLISH_MEDIA_LIMITS: dict[str, int] = {
    # xianyu gallery tiles resolve xianyu_gallery_select_0..49 (tile 0 is the
    # camera shutter), so at most 49 covers are selectable per listing; the
    # companion MediaDelivery transport cap (50) stays above this.
    "xianyu": 49,
    "xiaohongshu": 18,
}

# Catalog operations the publish mint is routed through (task-schedule/v1 §2
# identity chain: operationId → commandType → taskId).
PUBLISH_OPERATION_IDS: dict[str, str] = {
    "xianyu.publish_listing.v1": "xy-tasks-01",
    "xiaohongshu.publish_note.v1": "red-tasks-01",
}

# K05 §4/§7: the open-only terminal result identity is exactly
# "reached the confirmation checkpoint + an evidence reference". It must never
# be phrased as a completed publish.
OPEN_ONLY_RESULT_OUTCOME = "reached_confirmation_point"
OPEN_ONLY_RESULT_EVIDENCE_KEY = "evidenceRef"

# Normalized fragments that claim publish completion. Matched against result
# keys and string values (lowercase, "_" / "-" stripped) so "publish_success",
# "publishSuccess", and "已发布" all fail closed.
_OPEN_ONLY_FORBIDDEN_RESULT_FRAGMENTS = (
    "published",
    "publishsuccess",
    "succeeded",
    "success",
    "已发布",
    "发布成功",
    "成功",
)


def derive_publish_target_id(
    *,
    content_id: str,
    revision_no: int,
    platform: str,
    account_id: str,
    device_id: str,
) -> str:
    """Deterministically derive the stable publishTargetId for one target.

    Rule (frozen with A05): uuid5 over the PUBLISH_TARGET_NAMESPACE of the
    canonical string ``content_id|revision_no|platform|account_id|device_id``.
    Re-minting the same target yields the same id; changing any member of the
    tuple yields a different id. The id is stamped into command_payload
    publishTargetId (existing channel) so retries and replays reuse it.
    """
    if not isinstance(content_id, str) or not content_id:
        raise ValueError("content_id is required")
    if platform not in PUBLISH_MEDIA_LIMITS:
        raise ValueError("platform is not a publish platform")
    if not isinstance(revision_no, int) or isinstance(revision_no, bool) or revision_no < 1:
        raise ValueError("revision_no must be a positive integer")
    canonical = "|".join(
        (content_id, str(revision_no), platform, str(account_id), str(device_id))
    )
    return str(uuid.uuid5(PUBLISH_TARGET_NAMESPACE, canonical))


def _reject_publish_success_claims(value: Any, path: str) -> None:
    from cloudctl_domain import ValidationError

    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower().replace("_", "").replace("-", "")
            if any(fragment in key_text for fragment in _OPEN_ONLY_FORBIDDEN_RESULT_FRAGMENTS):
                raise ValidationError(
                    "open-only publish results must not claim publish completion",
                    fields={str(key): f"forbidden result field at {path or 'result'}"},
                )
            _reject_publish_success_claims(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_publish_success_claims(item, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower().replace("_", "").replace("-", "")
        if any(fragment in lowered for fragment in _OPEN_ONLY_FORBIDDEN_RESULT_FRAGMENTS):
            raise ValidationError(
                "open-only publish results must not claim publish completion",
                fields={path or "result": "forbidden publish-completion wording"},
            )


def validate_open_only_task_result(command_type: str, result: Any) -> None:
    """Enforce the K05 §7 open-only result identity on a task result.

    Only applies to the open-only command family. The result may never claim
    that the publish completed (probes, page opens, and filled forms are not
    publishes). When a result carries an ``outcome``, it must be
    ``reached_confirmation_point`` and it must reference evidence. Intended
    hook point: MobileTaskService.finish before persisting a terminal result
    (integration handoff noted in the A05 report).
    """
    from cloudctl_domain import ValidationError

    if command_type not in OPEN_ONLY_COMMAND_TYPES:
        return
    if not isinstance(result, dict):
        return
    _reject_publish_success_claims(result, "")
    if "outcome" in result:
        if result["outcome"] != OPEN_ONLY_RESULT_OUTCOME:
            raise ValidationError(
                "open-only publish outcome must be reached_confirmation_point",
                fields={"outcome": str(result["outcome"])},
            )
        evidence = result.get(OPEN_ONLY_RESULT_EVIDENCE_KEY)
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValidationError(
                "open-only publish result requires an evidence reference",
                fields={OPEN_ONLY_RESULT_EVIDENCE_KEY: "evidence ref is required"},
            )


def _validated_builtin_recipe_ref(command_type: str) -> dict[str, Any]:
    """builtin_recipe_ref plus a fail-closed open-only graph check (K05 §4)."""
    from cloudctl_domain import ValidationError

    from .builtin_recipes import BUILTIN_RECIPES, builtin_recipe_ref

    try:
        recipe_ref = builtin_recipe_ref(command_type)
        RecipeRef.model_validate(recipe_ref)
        package = BUILTIN_RECIPES[command_type]
    except (KeyError, PydanticValidationError) as exc:
        raise ValidationError("builtin recipe ref is invalid for this command") from exc
    graph = package.get("graph") or {}
    if graph.get("commitActionId"):
        raise ValidationError("builtin publish recipe must not carry a commit action")
    for state in graph.get("states") or []:
        if state.get("terminal") and state.get("action") != "checkpoint":
            raise ValidationError("builtin publish recipe terminal must be a checkpoint")
        if state.get("action") == "commit" or str(state.get("onSuccess", "")).startswith("COMMIT"):
            raise ValidationError("builtin publish recipe must not commit")
    return recipe_ref


async def _load_bound_account_and_binding(
    session: Any, *, tenant_id: str, account_id: str, device_id: str, platform: str
) -> None:
    """Fail closed unless the account exists, matches the platform, and is
    BOUND to exactly this device (A05 pre-mint validation)."""
    from cloudctl_domain import ForbiddenError, NotFoundError

    from .db import AccountDeviceBindingRow, PlatformAccountRow

    account = await session.scalar(
        select(PlatformAccountRow).where(
            PlatformAccountRow.id == account_id,
            PlatformAccountRow.tenant_id == tenant_id,
        )
    )
    if account is None:
        raise NotFoundError("account was not found")
    if account.platform != platform:
        raise ForbiddenError("account platform does not match the publish command")
    binding = await session.scalar(
        select(AccountDeviceBindingRow).where(
            AccountDeviceBindingRow.tenant_id == tenant_id,
            AccountDeviceBindingRow.account_id == account_id,
            AccountDeviceBindingRow.device_id == device_id,
            AccountDeviceBindingRow.status == "BOUND",
        )
    )
    if binding is None:
        raise ForbiddenError("account is not bound to the selected device")
    if binding.platform and binding.platform != platform:
        raise ForbiddenError("account binding platform does not match the publish command")


async def _validate_publish_media(
    session: Any,
    *,
    tenant_id: str,
    platform: str,
    media_asset_ids: list[str],
    require_at_least_one: bool,
) -> list[str]:
    """Existence, tenant scope, duplicate-free order, and platform caps."""
    from cloudctl_domain import NotFoundError, ValidationError

    from .db import MediaAssetRow

    limit = PUBLISH_MEDIA_LIMITS[platform]
    if len(set(media_asset_ids)) != len(media_asset_ids):
        raise ValidationError("mediaAssetIds must preserve a duplicate-free order")
    if len(media_asset_ids) > limit:
        raise ValidationError(
            f"media count exceeds the {platform} platform limit of {limit}"
        )
    if require_at_least_one and not media_asset_ids:
        raise ValidationError(f"{platform} publish requires at least one media asset")
    if not media_asset_ids:
        return []
    rows = list(
        (
            await session.execute(
                select(MediaAssetRow).where(
                    MediaAssetRow.tenant_id == tenant_id,
                    MediaAssetRow.id.in_(media_asset_ids),
                )
            )
        ).scalars()
    )
    if len(rows) != len(set(media_asset_ids)):
        raise NotFoundError("one or more media assets were not found in tenant")
    by_id = {row.id: row for row in rows}
    for asset_id in media_asset_ids:
        content_type = str(by_id[asset_id].content_type or "")
        if not content_type.lower().startswith("image/"):
            raise ValidationError("publish media must be image assets")
    return list(media_asset_ids)


async def _freeze_product_parameters(
    session: Any, *, tenant_id: str, product_id: str
) -> tuple[dict[str, Any], str, int]:
    """Freeze ACTIVE catalog product copy and ordered cover media (xianyu)."""
    from cloudctl_domain import ConflictError, NotFoundError, ValidationError

    from .db import ProductMediaRow, ProductRow

    product = await session.scalar(
        select(ProductRow).where(
            ProductRow.id == product_id, ProductRow.tenant_id == tenant_id
        )
    )
    if product is None:
        raise NotFoundError("product was not found")
    if product.status != "ACTIVE":
        raise ConflictError("product is not active")
    media = list(
        await session.scalars(
            select(ProductMediaRow)
            .where(
                ProductMediaRow.product_id == product.id,
                ProductMediaRow.tenant_id == tenant_id,
            )
            .order_by(ProductMediaRow.sort_order)
        )
    )
    if not media:
        raise ValidationError("product has no media assets for listing")
    parameters = {
        "listingBody": product.description,
        "price": str(product.price),
        "mediaAssetIds": [row.media_asset_id for row in media],
        "productId": product.id,
    }
    return parameters, product.id, int(product.revision or 1)


async def _freeze_content_parameters(
    session: Any, *, tenant_id: str, content_id: str, revision_no: int | None
) -> tuple[dict[str, Any], str, int]:
    """Freeze an immutable content revision into xhs note parameters."""
    from cloudctl_domain import ConflictError, NotFoundError, ValidationError

    from .db import ContentItemRow, ContentRevisionMediaRow, ContentRevisionRow

    content = await session.scalar(
        select(ContentItemRow).where(
            ContentItemRow.id == content_id, ContentItemRow.tenant_id == tenant_id
        )
    )
    if content is None:
        raise NotFoundError("content was not found")
    if content.status != "ACTIVE":
        raise ConflictError("archived content cannot be published")
    statement = select(ContentRevisionRow).where(
        ContentRevisionRow.tenant_id == tenant_id,
        ContentRevisionRow.content_id == content.id,
    )
    if revision_no is not None:
        statement = statement.where(ContentRevisionRow.revision_no == revision_no)
    revision = await session.scalar(statement.order_by(ContentRevisionRow.revision_no.desc()))
    if revision is None:
        raise NotFoundError("content revision was not found")
    payload = revision.payload if isinstance(revision.payload, dict) else {}
    if payload.get("targetApp") == "douyin":
        raise ValidationError("content revision targets douyin and cannot mint an xhs command")
    body = payload.get("body")
    if not isinstance(body, str) or not body.strip():
        raise ValidationError("content revision payload has no body")
    media_asset_ids = payload.get("mediaAssetIds")
    if not isinstance(media_asset_ids, list):
        media_asset_ids = []
    if media_asset_ids:
        linked = set(
            await session.scalars(
                select(ContentRevisionMediaRow.media_asset_id).where(
                    ContentRevisionMediaRow.tenant_id == tenant_id,
                    ContentRevisionMediaRow.content_revision_id == revision.id,
                )
            )
        )
        unlinked = [asset_id for asset_id in media_asset_ids if asset_id not in linked]
        if unlinked:
            raise ValidationError(
                "revision media linkage is missing for: " + ", ".join(map(str, unlinked))
            )
    parameters = {
        "title": content.title,
        "body": body,
        "tags": payload.get("tags") or [],
        "mediaAssetIds": list(media_asset_ids),
    }
    return parameters, content.id, int(revision.revision_no)


def select(row: Any) -> Any:
    """Local import shim so the factory stays import-cycle free."""
    from sqlalchemy import select

    return select(row)


async def mint_publish_command(
    session: Any,
    *,
    tenant_id: str,
    command_type: str,
    device_id: str,
    account_id: str,
    product_id: str | None = None,
    content_id: str | None = None,
    revision_no: int | None = None,
) -> dict[str, Any]:
    """Mint a CommandV1 publish command from a web business object.

    Product → xianyu.publish_listing.v1, ContentRevision →
    xiaohongshu.publish_note.v1. Freezes the business copy, validates media /
    account binding / version snapshot fail-closed, derives the stable
    publishTargetId, and returns a payload the caller stamps into
    PlatformTaskCreate (the existing publishTargetId command_payload channel).
    """
    from cloudctl_domain import ValidationError

    platform = PUBLISH_COMMAND_PLATFORMS.get(command_type)
    if platform is None:
        raise ValidationError(
            "commandType is not a publish CommandV1 type mintable from business objects"
        )
    if command_type not in OPEN_ONLY_COMMAND_TYPES:
        raise ValidationError("publish mint requires an open-only command type")
    if command_type == "xianyu.publish_listing.v1" and not product_id:
        raise ValidationError("xianyu publish mint requires productId")
    if command_type == "xiaohongshu.publish_note.v1" and not content_id:
        raise ValidationError("xiaohongshu publish mint requires contentId")

    await _load_bound_account_and_binding(
        session,
        tenant_id=tenant_id,
        account_id=account_id,
        device_id=device_id,
        platform=platform,
    )

    if command_type == "xianyu.publish_listing.v1":
        require_at_least_one = False  # product freeze already enforces >= 1
        parameters, identity, frozen_revision = await _freeze_product_parameters(
            session, tenant_id=tenant_id, product_id=str(product_id)
        )
    else:
        require_at_least_one = True  # an xhs note always needs at least one image
        parameters, identity, frozen_revision = await _freeze_content_parameters(
            session, tenant_id=tenant_id, content_id=str(content_id), revision_no=revision_no
        )

    media_asset_ids = [
        asset_id
        for asset_id in (parameters.get("mediaAssetIds") or [])
        if isinstance(asset_id, str)
    ]
    await _validate_publish_media(
        session,
        tenant_id=tenant_id,
        platform=platform,
        media_asset_ids=media_asset_ids,
        require_at_least_one=require_at_least_one,
    )

    recipe_ref = _validated_builtin_recipe_ref(command_type)
    publish_target_id = derive_publish_target_id(
        content_id=identity,
        revision_no=frozen_revision,
        platform=platform,
        account_id=account_id,
        device_id=device_id,
    )
    try:
        minted = mint_operation_command(
            PUBLISH_OPERATION_IDS[command_type], parameters
        )
    except PydanticValidationError as exc:
        raise ValidationError(f"frozen business copy does not fit {command_type}: {exc}") from exc
    minted.update(
        {
            "publishTargetId": publish_target_id,
            "mediaDeliveryId": f"delivery-{platform}-{identity}-{frozen_revision}",
            "recipe": recipe_ref,
            "publishTarget": {
                "contentId": identity,
                "revisionNo": frozen_revision,
                "platform": platform,
                "accountId": account_id,
                "deviceId": device_id,
            },
            "resultContract": {
                "outcome": OPEN_ONLY_RESULT_OUTCOME,
                "evidenceRequired": True,
            },
        }
    )
    return minted


def platform_task_create_fields(
    minted: dict[str, Any],
    *,
    device_id: str,
    account_id: str,
    expected_binding_version: int | None = None,
) -> dict[str, Any]:
    """Map a mint_publish_command result onto the PlatformTaskCreate body.

    This is the exact wiring for the existing publishTargetId stamping
    channel: platform_tasks.create copies body.publish_target_id into
    command_payload.publishTargetId, and command_v1_from_task re-reads the
    frozen parameters from command_payload at claim time.
    """
    fields: dict[str, Any] = {
        "deviceId": device_id,
        "accountId": account_id,
        "commandType": minted["commandType"],
        "parameters": minted["parameters"],
        "operationId": minted["operationId"],
        "publishTargetId": minted["publishTargetId"],
        "mediaDeliveryId": minted["mediaDeliveryId"],
        "productId": minted["parameters"].get("productId"),
    }
    if expected_binding_version is not None:
        fields["expectedBindingVersion"] = expected_binding_version
    return fields
