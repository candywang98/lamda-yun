from __future__ import annotations

import pytest
from cloudctl_automation_sdk import validate_manifest
from pydantic import ValidationError


def manifest() -> dict:
    return {
        "apiVersion": "cloudctl.example/v1",
        "kind": "AutomationPackage",
        "metadata": {"name": "publisher", "version": "1.0.0"},
        "spec": {
            "entrypoint": "src.entrypoint:run",
            "runtime": {"python": ">=3.12,<3.13", "lamda": ">=10.6,<11", "android": ">=10,<=17"},
            "targets": [{"packageName": "com.example.target", "versions": ">=1,<2"}],
            "capabilities": {
                "required": ["ui.selectors", "screenshot"],
                "optional": [],
                "forbidden": [
                    "shell.arbitrary",
                    "frida",
                    "mitm",
                    "proxy.mutate",
                    "adb.remote",
                ],
            },
            "parametersSchema": "schemas/parameters.json",
            "locators": ["locators/app.yaml"],
            "submitPolicy": {"mode": "commit-intent-single-shot"},
            "signature": {"algorithm": "Ed25519", "keyId": "prod-1"},
        },
    }


def test_manifest_accepts_signed_capability_scoped_package() -> None:
    parsed = validate_manifest(manifest())
    assert parsed.spec.signature.algorithm == "Ed25519"


def test_manifest_rejects_arbitrary_shell_capability() -> None:
    value = manifest()
    value["spec"]["capabilities"]["required"].append("shell.arbitrary")
    with pytest.raises(ValidationError, match="forbidden capabilities"):
        validate_manifest(value)


def test_manifest_rejects_retryable_commit_policy() -> None:
    value = manifest()
    value["spec"]["submitPolicy"]["mode"] = "retry-until-success"
    with pytest.raises(ValidationError, match="commit-intent-single-shot"):
        validate_manifest(value)
