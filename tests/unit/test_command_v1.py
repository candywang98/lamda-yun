from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cloudctl_api.builtin_recipes import BUILTIN_RECIPES, builtin_recipe_ref
from cloudctl_api.command_v1 import command_v1_from_task, parse_command_v1
from cloudctl_automation_sdk.recipe import validate_recipe_package
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2] / "contracts" / "phase1" / "fixtures"


def test_valid_xianyu_publish_listing_parses() -> None:
    payload = json.loads((ROOT / "valid" / "xianyu-publish-listing.json").read_text(encoding="utf-8"))
    parsed = parse_command_v1(payload)
    assert parsed["protocolVersion"] == "cloudctl.command/v1"
    assert parsed["commandType"] == "xianyu.publish_listing.v1"
    assert parsed["accountId"] == "account-jia"
    assert parsed["bindingVersion"] == 3
    assert parsed["targetPackage"] == "com.taobao.idlefish"
    assert parsed["lease"]["controlEpoch"] == 7
    assert "shell" not in json.dumps(parsed).lower()


@pytest.mark.parametrize(
    "name",
    ["shell-command.json", "wrong-account.json", "unknown-field.json"],
)
def test_invalid_command_fixtures_are_rejected(name: str) -> None:
    payload = json.loads((ROOT / "invalid" / name).read_text(encoding="utf-8"))
    with pytest.raises((ValidationError, ValueError)):
        parse_command_v1(payload)


def test_wrong_device_package_is_rejected() -> None:
    payload = json.loads((ROOT / "valid" / "xianyu-publish-listing.json").read_text(encoding="utf-8"))
    payload["targetPackage"] = "com.example.malware"
    with pytest.raises((ValidationError, ValueError)):
        parse_command_v1(payload)


def test_builtin_recipes_are_hash_pinned_and_bounded() -> None:
    for command_type, package in BUILTIN_RECIPES.items():
        parsed = validate_recipe_package(package)
        ref = builtin_recipe_ref(command_type)
        assert ref["versionId"] == parsed.manifest.id
        assert ref["sha256"] == parsed.manifest.hash
        assert parsed.manifest.min_engine_version == 1
        assert {state.action for state in parsed.graph.states} <= {
            "tap",
            "input",
            "scroll",
            "extract",
            "wait",
            "launch",
            "media",
            "log",
            "checkpoint",
        }


def test_command_v1_from_task_uses_builtin_recipe_and_rejects_wrong_package() -> None:
    snapshot = "c" * 64
    minted = command_v1_from_task(
        task_id="11111111-1111-7111-8111-111111111111",
        attempt_id="22222222-2222-7222-8222-222222222222",
        command_type="device.probe_capabilities.v1",
        device_id="33333333-3333-7333-8333-333333333333",
        account_id="44444444-4444-7444-8444-444444444444",
        binding_version=1,
        target_package="com.company.cloudctl.companion",
        command_payload={"snapshotSha256": snapshot, "parameters": {}},
        control_epoch=3,
        lease_expires_at=datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
    )
    assert minted["protocolVersion"] == "cloudctl.command/v1"
    assert minted["recipe"] == builtin_recipe_ref("device.probe_capabilities.v1")
    assert minted["legacyStepsEnabled"] is False
    with pytest.raises((ValidationError, ValueError)):
        command_v1_from_task(
            task_id="11111111-1111-7111-8111-111111111111",
            attempt_id="22222222-2222-7222-8222-222222222222",
            command_type="xianyu.publish_listing.v1",
            device_id="33333333-3333-7333-8333-333333333333",
            account_id="44444444-4444-7444-8444-444444444444",
            binding_version=1,
            target_package="com.example.malware",
            command_payload={
                "snapshotSha256": snapshot,
                "parameters": {"listingBody": "自用闲置，功能正常，支持当面交易", "price": "12"},
            },
            control_epoch=3,
            lease_expires_at=datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
        )
