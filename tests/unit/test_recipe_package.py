from __future__ import annotations

import base64
import hashlib

import pytest
from cloudctl_automation_sdk.recipe import canonical_recipe_bytes, validate_recipe_package
from cloudctl_automation_sdk.registry import package_signature_payload
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError


def unsigned_package() -> dict:
    package = {
        "apiVersion": "cloudctl.recipe/v1",
        "kind": "LocalRecipePackage",
        "manifest": {
            "id": "recipe-xianyu-publish-1",
            "version": "1.0.0",
            "hash": "0" * 64,
            "signingKeyId": "prod-1",
            "minEngineVersion": 2,
            "platform": "xianyu",
            "app": "com.taobao.idlefish",
            "commandTypes": ["xianyu.publish_listing.v1"],
        },
        "graph": {
            "startStateId": "open",
            "maxIterations": 12,
            "maxDurationMs": 90000,
            "safeCheckpoint": "open",
            "resumeGuard": "package_foreground",
            "commitActionId": "publish",
            "states": [
                {
                    "stateId": "open", "action": "tap", "locatorRef": "xianyu_home_sell",
                    "onSuccess": "fill", "onFailure": "FAILED", "onPause": "WAITING_USER",
                },
                {
                    "stateId": "fill", "action": "input", "locatorRef": "xianyu_description",
                    "onSuccess": "publish", "onFailure": "FAILED",
                },
                {
                    "stateId": "publish", "action": "tap", "locatorRef": "xianyu_publish_button",
                    "postcondition": "xianyu_publish_success", "onSuccess": "SUCCEEDED",
                    "terminal": True,
                },
            ],
        },
        "signature": {"algorithm": "Ed25519", "keyId": "prod-1", "digest": "unsigned"},
    }
    rehash(package)
    return package


def rehash(value):
    value["manifest"]["hash"] = hashlib.sha256(canonical_recipe_bytes(value)).hexdigest()


def test_valid_recipe_is_bounded_and_whitelisted() -> None:
    parsed = validate_recipe_package(unsigned_package())
    assert parsed.graph.max_iterations == 12
    assert parsed.graph.commit_action_id == "publish"
    assert {state.action for state in parsed.graph.states} <= {
        "tap", "input", "scroll", "extract", "wait", "launch", "media", "log", "checkpoint",
    }


def test_unknown_action_and_path_traversal_rejected() -> None:
    value = unsigned_package()
    value["graph"]["states"][0]["action"] = "shell"
    rehash(value)
    with pytest.raises((ValidationError, ValueError)):
        validate_recipe_package(value)
    value = unsigned_package()
    value["graph"]["states"][0]["locatorRef"] = "../etc/passwd"
    rehash(value)
    with pytest.raises((ValidationError, ValueError)):
        validate_recipe_package(value)


def test_loop_without_exit_and_old_engine_rejected() -> None:
    value = unsigned_package()
    value["graph"].pop("commitActionId")
    value["graph"]["states"] = [
        {"stateId": "loop", "action": "wait", "onSuccess": "loop", "onFailure": "loop"}
    ]
    value["graph"]["startStateId"] = "loop"
    rehash(value)
    with pytest.raises((ValidationError, ValueError), match="terminal"):
        validate_recipe_package(value)
    value = unsigned_package()
    value["manifest"]["minEngineVersion"] = 99
    rehash(value)
    with pytest.raises(ValueError, match="UNSUPPORTED_RECIPE"):
        validate_recipe_package(value)


def test_tampered_hash_and_bad_signature_rejected() -> None:
    value = unsigned_package()
    value["manifest"]["hash"] = "a" * 64
    with pytest.raises(ValueError, match="hash"):
        validate_recipe_package(value)
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode()
    good = unsigned_package()
    payload = package_signature_payload(
        artifact_sha256=good["manifest"]["hash"], manifest=good["manifest"],
        sbom_ref="recipe://local", sbom_sha256=good["manifest"]["hash"],
    )
    good["signature"]["digest"] = base64.b64encode(key.sign(payload)).decode()
    validate_recipe_package(good, public_key_base64=public)
    good["signature"]["digest"] = base64.b64encode(b"not-a-real-signature-bytes-here!!!!").decode()
    with pytest.raises(ValueError):
        validate_recipe_package(good, public_key_base64=public)


def test_commit_cannot_run_on_old_engine_or_declare_old_minimum():
    value = unsigned_package()
    with pytest.raises(ValueError, match="UNSUPPORTED_RECIPE"):
        validate_recipe_package(value, engine_version=1)
    value["manifest"]["minEngineVersion"] = 1
    rehash(value)
    with pytest.raises(ValueError, match="requires engine version 2"):
        validate_recipe_package(value)


@pytest.mark.parametrize("field,value", [
    ("action", "checkpoint"), ("locatorRef", None), ("postcondition", None),
    ("postcondition", "xianyu_publish_button"), ("onSuccess", "open"),
    ("onFailure", "open"),
])
def test_invalid_commit_is_rejected(field, value):
    package = unsigned_package()
    package["graph"]["states"][-1][field] = value
    rehash(package)
    with pytest.raises(ValueError, match="commit requires"):
        validate_recipe_package(package)


@pytest.mark.parametrize("commit_id", [None, "missing", "bad/id"])
def test_commit_identity_cannot_be_missing_or_invalid(commit_id):
    package = unsigned_package()
    package["graph"]["commitActionId"] = commit_id
    rehash(package)
    with pytest.raises(ValueError):
        validate_recipe_package(package)
