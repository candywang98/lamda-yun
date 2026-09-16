"""A09 operation catalog tests: the 31 xy-tasks actions registered per field-map.

Covers the task-card acceptance:
- every xy-tasks-01..31 action is registered (OperationDefinition + feature map);
- each action carries its own result schema (polish/deleted/price/... — never a
  shared generic "delete"/"success" blob);
- strict parameter allowlists reject unknown fields and budget/target drift;
- the CommandV1 mint lane stays fail-closed outside PRODUCTION_ALIASES;
- the task-schedule/v1 §2 identity chain: operationId create→GET is visible.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.command_factory import (
    PRODUCTION_ALIASES,
    mint_operation_command,
    xianyu_operations,
    xy_catalog_registration,
)
from cloudctl_api.mobile_schemas import RESULT_TYPES
from cloudctl_api.operation_catalog import (
    BLOCKED_FEATURE_IDS,
    BY_CATALOG_ID,
    BY_KEY,
    DEFINITIONS,
    FEATURE_BY_ID,
    FEATURE_OPERATION_MAP,
    XY_TASK_CATALOG_IDS,
)
from cloudctl_api.operation_parameters import (
    CORE_MODELS,
    PAGE_MODELS,
    PAGE_OPERATION_KEYS,
    validate_operation_parameters,
)
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]

# xy-tasks actions that share the field-map commandType as their catalog key
# (xy-tasks-01 keeps its pre-existing xianyu.listing.publish key).
KEY_OVERRIDES = {"xy-tasks-01": "xianyu.listing.publish"}
# Field-map fields owned by other lanes: device routing (deviceIds) and the
# publish allocator knobs validated by the command_factory mint lane
# (COMMON_TASK_FIELDS), not the operation-lane core contract.
ROUTING_FIELDS = frozenset(
    {"deviceIds", "productIds", "allocation", "formMode", "addressMode", "descPool", "watermark"}
)
DELETE_CATALOG_IDS = ("xy-tasks-06", "xy-tasks-07", "xy-tasks-16", "xy-tasks-17", "xy-tasks-18")


def _spec_by_id() -> dict[str, dict]:
    return {item["id"]: item for item in xianyu_operations()}


# ---------------------------------------------------------------------------
# Registration parity with docs/phase1/field-map.json (31 actions).
# ---------------------------------------------------------------------------


def test_all_31_field_map_actions_are_registered() -> None:
    specs = _spec_by_id()
    assert set(BY_CATALOG_ID) == set(XY_TASK_CATALOG_IDS) == set(specs)
    for catalog_id, spec in specs.items():
        definition = BY_CATALOG_ID[catalog_id]
        assert definition.module == "xy_tasks"
        assert definition.catalog_id == catalog_id
        # Where field-map declares a commandType, the registration reuses it as
        # the catalog key (xy-tasks-01 keeps its pre-existing mint-lane key);
        # null-commandType shared-service pages register a xianyu.* inventory key.
        command_type = spec.get("commandType")
        if command_type:
            assert definition.key == KEY_OVERRIDES.get(catalog_id, command_type), catalog_id
        else:
            assert definition.key.startswith("xianyu."), catalog_id
        # field-map declared fields (minus the app=main constraint marker and
        # the mint-lane routing fields) must be inside the declared allowlist.
        declared = {field for field in spec.get("fields", []) if field != "app=main"}
        assert declared - ROUTING_FIELDS <= definition.allowed_parameters, catalog_id


def test_every_xy_feature_maps_to_its_registration() -> None:
    for catalog_id in XY_TASK_CATALOG_IDS:
        definition = BY_CATALOG_ID[catalog_id]
        feature = FEATURE_BY_ID[catalog_id]
        assert feature.operation_key == definition.key, catalog_id
        assert FEATURE_OPERATION_MAP[catalog_id] == definition.key
        assert PAGE_OPERATION_KEYS[catalog_id] == definition.key
        assert catalog_id in PAGE_MODELS


def test_core_parameter_models_cover_all_xy_registrations() -> None:
    for catalog_id in XY_TASK_CATALOG_IDS:
        model = CORE_MODELS[BY_CATALOG_ID[catalog_id].key]
        aliases = {(field.alias or name) for name, field in model.model_fields.items()}
        assert aliases == BY_CATALOG_ID[catalog_id].allowed_parameters, catalog_id


# ---------------------------------------------------------------------------
# Result identity: every action has its own correct result type.
# ---------------------------------------------------------------------------


def test_result_types_are_pairwise_distinct_and_non_generic() -> None:
    result_types = [definition.result_type for definition in DEFINITIONS]
    assert all(result_types)
    assert len(set(result_types)) == len(result_types)
    xy_types = {BY_CATALOG_ID[cid].result_type for cid in XY_TASK_CATALOG_IDS}
    # Red line: no action may collapse into a generic delete/success blob.
    for generic in ("deleted", "success", "ok", "Result", "XianyuDeletedResult"):
        assert generic not in xy_types


def test_result_types_match_action_semantics() -> None:
    by_id = {cid: BY_CATALOG_ID[cid].result_type for cid in XY_TASK_CATALOG_IDS}
    # 擦亮商品 reports a polish result.
    assert "Polish" in by_id["xy-tasks-03"]
    # Every deletion reports a deleted result of its own resource kind.
    for catalog_id, fragment in (
        ("xy-tasks-06", "GoodsDeleted"),
        ("xy-tasks-07", "PostDeleted"),
        ("xy-tasks-16", "FeedDeleted"),
        ("xy-tasks-17", "MessageDeleted"),
        ("xy-tasks-18", "CommentDeleted"),
    ):
        assert fragment in by_id[catalog_id], catalog_id
    assert len({by_id[cid] for cid in DELETE_CATALOG_IDS}) == len(DELETE_CATALOG_IDS)
    # 价格 actions report a price update; 评价/推广 carry their own identities.
    assert "PriceUpdated" in by_id["xy-tasks-13"]
    assert "ReviewPosted" in by_id["xy-tasks-14"]
    assert "PromoteStarted" in by_id["xy-tasks-11"]
    assert "CoinDiscountApplied" in by_id["xy-tasks-10"]
    # Publishes are distinct from deletes and from each other.
    assert by_id["xy-tasks-01"] == RESULT_TYPES["xianyu.publish_listing.v1"]
    assert by_id["xy-tasks-01"] != by_id["xy-tasks-02"]


def test_existing_definitions_keep_distinct_result_types() -> None:
    non_xy = [d for d in DEFINITIONS if d.catalog_id is None]
    assert {d.result_type for d in non_xy} == {
        "AccountHealthReportResult",
        "DeviceCapabilityInventoryResult",
        "GroupMembershipIndexResult",
        "MediaDerivativeGeneratedResult",
        "WatermarkPreviewRenderedResult",
        "WorkRevisionValidatedResult",
        "PublishSnapshotValidatedResult",
        "TaskEvidenceExportResult",
        "QualificationRunReportResult",
        "DebugEvidenceExportResult",
        "ApkArtifactAnalysisResult",
        "ApkRolloutHealthReportResult",
        "SecurityPolicyExportResult",
        "AccessReviewReportResult",
        "AuditExportResult",
    }


# ---------------------------------------------------------------------------
# Availability: executable / pending real-device verification / contract only.
# ---------------------------------------------------------------------------


def test_availability_classification_and_prerequisites() -> None:
    specs = _spec_by_id()
    pending = {
        catalog_id
        for catalog_id in XY_TASK_CATALOG_IDS
        if specs[catalog_id].get("status") == "AVAILABILITY_PENDING"
    }
    assert pending == {"xy-tasks-02", "xy-tasks-07"}
    for catalog_id in XY_TASK_CATALOG_IDS:
        definition = BY_CATALOG_ID[catalog_id]
        if catalog_id == "xy-tasks-01":
            assert definition.availability == "executable"
            assert definition.prerequisite == ""
        elif catalog_id in pending:
            # AVAILABILITY_PENDING keeps the action visible as contract_only
            # with the T102 real-device prerequisite spelled out.
            assert definition.availability == "pending_device_verification"
            assert "T102" in definition.prerequisite
            assert FEATURE_BY_ID[catalog_id].execution_state == "contract_only"
        else:
            assert definition.availability == "contract_only"
            assert definition.prerequisite
    # The production-policy block on coin/review engagement features is kept.
    assert {"xy-tasks-09", "xy-tasks-10", "xy-tasks-11", "xy-tasks-14"} <= BLOCKED_FEATURE_IDS
    for catalog_id in ("xy-tasks-09", "xy-tasks-10", "xy-tasks-11", "xy-tasks-14"):
        assert "BLOCKED_FEATURE_IDS" in BY_CATALOG_ID[catalog_id].prerequisite
        assert FEATURE_BY_ID[catalog_id].policy == "blocked"


# ---------------------------------------------------------------------------
# Strict parameter allowlists: unknown fields and budget/target drift.
# ---------------------------------------------------------------------------


def test_all_xy_operations_reject_unknown_parameters() -> None:
    for catalog_id in XY_TASK_CATALOG_IDS:
        key = BY_CATALOG_ID[catalog_id].key
        with pytest.raises(ValidationError):
            validate_operation_parameters(key, None, {"unexpectedField": True})


def test_budget_and_target_drift_is_rejected() -> None:
    # Promotion budget tiers are closed Literals: an undeclared coin package
    # or item target is a drift and must not validate.
    with pytest.raises(ValidationError):
        validate_operation_parameters(
            "xianyu.coin_promote",
            None,
            {"promoteItem": "manually_selected", "promotePackage": "coins_9999"},
        )
    with pytest.raises(ValidationError):
        validate_operation_parameters(
            "xianyu.coin_promote",
            None,
            {"promoteItem": "every_listing", "promotePackage": "coins_60"},
        )
    with pytest.raises(ValidationError):
        validate_operation_parameters(
            "xianyu.coin_promote",
            None,
            {"promoteItem": "manually_selected", "promotePackage": "coins_60", "dailyBudget": 5},
        )
    # Price cuts: bounded percent, exactly one cut dimension, declared target.
    with pytest.raises(ValidationError):
        validate_operation_parameters(
            "xianyu.price_cut", None, {"percentCut": 99, "target": "all_listings"}
        )
    with pytest.raises(ValidationError):
        validate_operation_parameters(
            "xianyu.price_cut",
            None,
            {"percentCut": 10, "amountCut": "5", "target": "all_listings"},
        )
    with pytest.raises(ValidationError):
        validate_operation_parameters("xianyu.price_cut", None, {"target": "all_listings"})
    with pytest.raises(ValidationError):
        validate_operation_parameters(
            "xianyu.price_cut", None, {"percentCut": 10, "target": "whatever"}
        )
    # Deletion / deduction / review targets are declared selections.
    with pytest.raises(ValidationError):
        validate_operation_parameters("xianyu.delete_goods", None, {"target": "everything"})
    with pytest.raises(ValidationError):
        validate_operation_parameters(
            "xianyu.review", None, {"reviewBody": "好", "reviewTarget": "everyone"}
        )
    with pytest.raises(ValidationError):
        validate_operation_parameters(
            "xianyu.coin_discount",
            None,
            {"dikouType": "anything", "dikouTarget": "all_eligible"},
        )


def test_valid_parameters_still_normalize() -> None:
    polished = validate_operation_parameters(
        "xianyu.polish_goods", "xy-tasks-03", {"intervalSeconds": 30}
    )
    assert polished == {"intervalSeconds": 30}
    promoted = validate_operation_parameters(
        "xianyu.coin_promote",
        "xy-tasks-11",
        {"promoteItem": "manually_selected", "promotePackage": "coins_60"},
    )
    assert promoted == {"promoteItem": "manually_selected", "promotePackage": "coins_60"}
    cut = validate_operation_parameters(
        "xianyu.price_cut", "xy-tasks-13", {"percentCut": 10, "target": "all_listings"}
    )
    assert cut == {"percentCut": 10, "target": "all_listings"}
    deleted = validate_operation_parameters(
        "xianyu.delete_goods", "xy-tasks-06", {"target": "sold_out"}
    )
    assert deleted == {"target": "sold_out"}


# ---------------------------------------------------------------------------
# Mint lane: fail-closed outside PRODUCTION_ALIASES, resultType stamped.
# ---------------------------------------------------------------------------


def test_only_publish_goods_mints_a_production_command() -> None:
    specs = _spec_by_id()
    for catalog_id in XY_TASK_CATALOG_IDS:
        spec = specs[catalog_id]
        if catalog_id == "xy-tasks-01":
            continue
        command_type = spec.get("commandType")
        if not command_type or command_type not in PRODUCTION_ALIASES:
            with pytest.raises(ValueError, match="not enabled|T102|AVAILABILITY_PENDING"):
                mint_operation_command(catalog_id, {})
    minted = mint_operation_command("xy-tasks-01", {"listingBody": "自用闲置", "price": "128"})
    assert minted["commandType"] == "xianyu.publish_listing.v1"
    assert minted["resultType"] == RESULT_TYPES["xianyu.publish_listing.v1"]
    registration = xy_catalog_registration("xy-tasks-01")
    assert registration is not None
    assert registration == {
        "operationKey": "xianyu.listing.publish",
        "resultType": "XianyuPublishListingResult",
        "availability": "executable",
        "prerequisite": "",
    }
    assert xy_catalog_registration("xy-tasks-99") is None


def test_contract_only_registration_reports_its_prerequisite() -> None:
    with pytest.raises(ValueError, match="contract_only.*not enabled"):
        mint_operation_command("xy-tasks-06", {"target": "sold_out"})
    with pytest.raises(ValueError, match="T102"):
        mint_operation_command("xy-tasks-02", {})
    with pytest.raises(ValueError, match="T102"):
        mint_operation_command("xy-tasks-07", {})


# ---------------------------------------------------------------------------
# task-schedule/v1 §2 identity chain: operationId create→GET stays visible.
# ---------------------------------------------------------------------------

TENANT = "00000000-0000-7000-8000-000000000111"
OPERATOR = "00000000-0000-7000-8000-000000000222"


def identity() -> dict[str, str]:
    return {
        "X-Tenant-Id": TENANT,
        "X-User-Id": OPERATOR,
        "X-Roles": "device_operator",
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


async def _bound_device(client: httpx.AsyncClient, name: str) -> tuple[str, str, int]:
    device = await client.post(
        "/api/v1/mobile/devices",
        headers=identity(),
        json={"logicalName": name, "androidVersion": "14", "companionVersion": "1.0.0"},
    )
    assert device.status_code == 201, device.text
    account = await client.post(
        "/api/v1/accounts",
        headers=identity(),
        json={
            "platform": "xianyu",
            "externalSubjectRef": f"{name}-subject",
            "displayLabel": name,
            "secretRef": f"vault://cloudctl/accounts/{name}",
            "authorizationBasis": "Owner authorized the test account.",
        },
    )
    assert account.status_code == 201, account.text
    binding = await client.post(
        f"/api/v1/accounts/{account.json()['id']}/bindings",
        headers=identity(),
        json={"deviceId": device.json()["id"], "confirmationNote": "Owner confirmed."},
    )
    assert binding.status_code == 201, binding.text
    return (
        str(device.json()["id"]),
        str(account.json()["id"]),
        int(binding.json()["bindingVersion"]),
    )


@pytest.mark.asyncio
async def test_operation_id_full_chain_create_get_visible(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id, account_id, binding_version = await _bound_device(client, "phone-a09")
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "a09-chain-publish"},
        json={
            "deviceId": device_id,
            "accountId": account_id,
            "expectedBindingVersion": binding_version,
            "operationId": "xy-tasks-01",
            "parameters": {"listingBody": "自用闲置，功能正常", "price": "128"},
        },
    )
    assert created.status_code == 201, created.text
    item = created.json()["items"][0]
    assert item["commandType"] == "xianyu.publish_listing.v1"
    # A04 creation freeze: the catalog operationId is persisted on the task,
    # the frozen command payload, and the operator GET view.
    assert item["operationId"] == "xy-tasks-01"
    assert item["commandPayload"]["operationId"] == "xy-tasks-01"
    assert item["commandPayload"]["parameters"]["listingBody"] == "自用闲置，功能正常"
    assert item["commandPayload"]["snapshotSha256"]
    detail = await client.get(f"/api/v1/platform-tasks/{item['taskId']}", headers=identity())
    assert detail.status_code == 200, detail.text
    assert detail.json()["operationId"] == "xy-tasks-01"
    assert detail.json()["commandPayload"]["operationId"] == "xy-tasks-01"
    # A contract_only registration cannot mint a production command.
    denied = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "a09-chain-delete"},
        json={
            "deviceId": device_id,
            "accountId": account_id,
            "expectedBindingVersion": binding_version,
            "operationId": "xy-tasks-06",
            "parameters": {"target": "sold_out"},
        },
    )
    assert denied.status_code == 422
    # The 422 problem body carries the fail-closed mint reason in its fields.
    assert "not enabled" in str(denied.json().get("fields", {}))


def test_field_map_copies_stay_in_sync() -> None:
    docs_copy = ROOT / "docs" / "phase1" / "field-map.json"
    services_copy = ROOT / "services" / "control-api" / "src" / "cloudctl_api" / "field-map.json"
    assert docs_copy.read_text(encoding="utf-8") == services_copy.read_text(encoding="utf-8")


def test_catalog_and_by_key_stay_consistent() -> None:
    assert set(BY_KEY) == {definition.key for definition in DEFINITIONS}
    assert BY_KEY["xianyu.listing.publish"].catalog_id == "xy-tasks-01"
    for definition in DEFINITIONS:
        if definition.availability != "executable":
            assert definition.prerequisite
