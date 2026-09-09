from __future__ import annotations

import json
from pathlib import Path

import pytest
from cloudctl_api.command_factory import mint_operation_command, xianyu_operations
from cloudctl_api.command_v1 import parse_command_v1

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
        mint_operation_command("xy-tasks-01", {"listingBody": "ok", "price": "1", "shellCommand": "rm"})
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
