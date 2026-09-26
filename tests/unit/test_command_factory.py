from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from cloudctl_api.command_factory import (
    OPEN_ONLY_RESULT_EVIDENCE_KEY,
    OPEN_ONLY_RESULT_OUTCOME,
    PUBLISH_COMMAND_PLATFORMS,
    PUBLISH_MEDIA_LIMITS,
    PUBLISH_OPERATION_IDS,
    PUBLISH_TARGET_NAMESPACE,
    derive_publish_target_id,
    mint_operation_command,
    platform_task_create_fields,
    validate_open_only_task_result,
    xianyu_operations,
)
from cloudctl_api.command_v1 import parse_command_v1
from cloudctl_domain import ValidationError

ROOT = Path(__file__).resolve().parents[2]


def test_all_31_xianyu_operations_have_unique_ids_and_field_map_parity() -> None:
    field_map = json.loads((ROOT / "docs/phase1/field-map.json").read_text(encoding="utf-8"))
    operations = xianyu_operations()
    assert [item["id"] for item in operations] == [item["id"] for item in field_map["operations"]]
    assert len({item["id"] for item in operations}) == 31
    assert {item["title"] for item in operations} == set(field_map["phase1Scope"]["xianyu31"])


def test_publish_goods_mints_open_only_listing_command() -> None:
    minted = mint_operation_command(
        "xy-tasks-01",
        {
            "listingBody": "自用闲置，功能正常，支持当面交易",
            "price": "128",
            "productIds": ["product-1"],
        },
    )
    assert minted["commandType"] == "xianyu.publish_listing.v1"
    assert minted["targetPackage"] == "com.taobao.idlefish"
    assert minted["openOnly"] is True
    assert minted["parameters"]["listingBody"].startswith("自用闲置")
    assert "productIds" not in minted["parameters"]


def test_xiaohongshu_allowlist_is_wired_through_factory() -> None:
    minted = mint_operation_command(
        "red-tasks-01",
        {"title": "测试笔记", "body": "正文不少于一个字", "tags": ["闲置"]},
    )
    assert minted["commandType"] == "xiaohongshu.publish_note.v1"
    assert minted["targetPackage"] == "com.xingin.xhs"
    assert minted["openOnly"] is True


def test_unwired_and_pending_operations_fail_closed() -> None:
    with pytest.raises(ValueError, match="T102|AVAILABILITY_PENDING"):
        mint_operation_command("xy-tasks-02", {"deviceIds": ["device-1"]})
    with pytest.raises(ValueError, match="not enabled"):
        mint_operation_command("xy-tasks-03", {"intervalSeconds": 30})
    with pytest.raises(ValueError, match="unknown operationId"):
        mint_operation_command("xy-tasks-99", {})
    with pytest.raises(ValueError, match="unauthorized"):
        mint_operation_command(
            "xy-tasks-01", {"listingBody": "ok", "price": "1", "shellCommand": "rm"}
        )
    with pytest.raises(ValueError, match="unknown operation fields"):
        mint_operation_command("device-probe", {"unexpectedFlag": True})


def test_factory_output_is_valid_command_v1_parameters() -> None:
    from datetime import UTC, datetime

    from cloudctl_api.command_v1 import command_v1_from_task

    minted = mint_operation_command(
        "device-probe",
        {"deviceIds": ["33333333-3333-7333-8333-333333333333"]},
    )
    command = command_v1_from_task(
        task_id="11111111-1111-7111-8111-111111111111",
        attempt_id="22222222-2222-7222-8222-222222222222",
        command_type=minted["commandType"],
        device_id="33333333-3333-7333-8333-333333333333",
        account_id="44444444-4444-7444-8444-444444444444",
        binding_version=1,
        target_package="com.company.cloudctl.companion",
        command_payload={"snapshotSha256": "d" * 64, "parameters": minted["parameters"]},
        control_epoch=4,
        lease_expires_at=datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
    )
    parsed = parse_command_v1(command)
    assert parsed["commandType"] == "device.probe_capabilities.v1"
    assert parsed["legacyStepsEnabled"] is False


# ---------------------------------------------------------------------------
# A05: stable publishTargetId derivation + open-only result identity.
# ---------------------------------------------------------------------------

TARGET_KWARGS = {
    "content_id": "content-1",
    "revision_no": 3,
    "platform": "xiaohongshu",
    "account_id": "account-1",
    "device_id": "device-1",
}


def test_derive_publish_target_id_is_stable_and_pinned_to_the_rule() -> None:
    first = derive_publish_target_id(**TARGET_KWARGS)
    second = derive_publish_target_id(**TARGET_KWARGS)
    assert first == second
    # The derivation rule is frozen: uuid5 of the namespace over the canonical
    # "content_id|revision_no|platform|account_id|device_id" string.
    canonical = "content-1|3|xiaohongshu|account-1|device-1"
    assert first == str(uuid.uuid5(PUBLISH_TARGET_NAMESPACE, canonical))
    uuid.UUID(first)  # stable ids are uuid-shaped


def test_derive_publish_target_id_changes_with_every_identity_member() -> None:
    base = derive_publish_target_id(**TARGET_KWARGS)
    variants = (
        {"content_id": "content-2"},
        {"revision_no": 4},
        {"platform": "xianyu"},
        {"account_id": "account-2"},
        {"device_id": "device-2"},
    )
    for variant in variants:
        changed = {**TARGET_KWARGS, **variant}
        assert derive_publish_target_id(**changed) != base, variant


def test_derive_publish_target_id_rejects_non_publish_inputs() -> None:
    with pytest.raises(ValueError, match="platform"):
        derive_publish_target_id(**{**TARGET_KWARGS, "platform": "douyin"})
    with pytest.raises(ValueError, match="revision_no"):
        derive_publish_target_id(**{**TARGET_KWARGS, "revision_no": 0})
    with pytest.raises(ValueError, match="content_id"):
        derive_publish_target_id(**{**TARGET_KWARGS, "content_id": ""})


def test_publish_mint_registry_stays_inside_the_frozen_scope() -> None:
    from cloudctl_api.command_factory import PRODUCTION_ALIASES

    assert set(PUBLISH_COMMAND_PLATFORMS) <= set(PRODUCTION_ALIASES.values())
    assert PUBLISH_MEDIA_LIMITS == {"xianyu": 49, "xiaohongshu": 18}
    minimal_parameters = {
        "xy-tasks-01": {"listingBody": "自用闲置", "price": "128"},
        "red-tasks-01": {"title": "测试笔记", "body": "正文"},
    }
    for command_type, operation_id in PUBLISH_OPERATION_IDS.items():
        minted = mint_operation_command(operation_id, minimal_parameters[operation_id])
        assert minted["commandType"] == command_type
        assert minted["openOnly"] is True


def test_open_only_result_contract_accepts_checkpoint_plus_evidence() -> None:
    validate_open_only_task_result(
        "xiaohongshu.publish_note.v1",
        {
            "outcome": OPEN_ONLY_RESULT_OUTCOME,
            OPEN_ONLY_RESULT_EVIDENCE_KEY: "s3://evidence/xhs-note-1/checkpoint.png",
            "resultType": "XiaohongshuPublishNoteResult",
        },
    )
    # A failure-style result with no outcome claim is shape-neutral.
    validate_open_only_task_result(
        "xianyu.publish_listing.v1", {"resultType": "XianyuPublishListingResult"}
    )
    # Non-open-only commands keep their own result identity.
    validate_open_only_task_result("device.probe_capabilities.v1", {"outcome": "ok"})
    validate_open_only_task_result("xianyu.collect_orders.v1", {"published": True})


@pytest.mark.parametrize(
    "result",
    [
        {"outcome": "published"},
        {"outcome": "ok"},
        {"published": True},
        {"publishSuccess": True},
        {"note": "发布成功"},
        {"detail": "listing 已发布"},
        {"nested": [{"messageCode": "XIANYU_PUBLISH_SUCCESS"}]},
        {"outcome": OPEN_ONLY_RESULT_OUTCOME},
        {"outcome": OPEN_ONLY_RESULT_OUTCOME, OPEN_ONLY_RESULT_EVIDENCE_KEY: "  "},
    ],
)
def test_open_only_result_contract_rejects_publish_success_claims(result: dict) -> None:
    with pytest.raises(ValidationError):
        validate_open_only_task_result("xianyu.publish_listing.v1", result)
    with pytest.raises(ValidationError):
        validate_open_only_task_result("xiaohongshu.publish_note.v1", result)


def test_platform_task_create_fields_map_mint_output_onto_existing_channel() -> None:
    minted = {
        "commandType": "xianyu.publish_listing.v1",
        "operationId": "xy-tasks-01",
        "parameters": {
            "listingBody": "自用闲置",
            "price": "128",
            "mediaAssetIds": ["asset-1"],
            "productId": "product-1",
        },
        "publishTargetId": "pt-1",
        "mediaDeliveryId": "delivery-xianyu-product-1-2",
    }
    fields = platform_task_create_fields(
        minted, device_id="device-1", account_id="account-1", expected_binding_version=2
    )
    assert fields == {
        "deviceId": "device-1",
        "accountId": "account-1",
        "commandType": "xianyu.publish_listing.v1",
        "operationId": "xy-tasks-01",
        "parameters": minted["parameters"],
        "publishTargetId": "pt-1",
        "mediaDeliveryId": "delivery-xianyu-product-1-2",
        "productId": "product-1",
        "expectedBindingVersion": 2,
    }
