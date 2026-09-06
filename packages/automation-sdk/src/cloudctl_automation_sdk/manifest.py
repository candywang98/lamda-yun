"""Automation package manifest validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

PRODUCTION_FORBIDDEN = frozenset({"shell.arbitrary", "frida", "mitm", "proxy.mutate", "adb.remote"})


class RuntimeSpec(BaseModel):
    python: str
    lamda: str
    android: str


class TargetSpec(BaseModel):
    package_name: str = Field(alias="packageName")
    versions: str


class CapabilitySpec(BaseModel):
    required: set[str] = Field(default_factory=set)
    optional: set[str] = Field(default_factory=set)
    forbidden: set[str] = Field(default_factory=set)


class SubmitPolicy(BaseModel):
    mode: str


class SignatureSpec(BaseModel):
    algorithm: str
    key_id: str = Field(alias="keyId")


class AutomationSpec(BaseModel):
    entrypoint: str
    runtime: RuntimeSpec
    targets: list[TargetSpec]
    capabilities: CapabilitySpec
    parameters_schema: str = Field(alias="parametersSchema")
    locators: list[str]
    submit_policy: SubmitPolicy = Field(alias="submitPolicy")
    signature: SignatureSpec


class ManifestMetadata(BaseModel):
    name: str
    version: str


class AutomationManifest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    api_version: str = Field(alias="apiVersion")
    kind: str
    metadata: ManifestMetadata
    spec: AutomationSpec

    @model_validator(mode="after")
    def enforce_security_contract(self) -> AutomationManifest:
        if self.api_version != "cloudctl.example/v1" or self.kind != "AutomationPackage":
            raise ValueError("unsupported automation manifest kind or apiVersion")
        if self.spec.submit_policy.mode != "commit-intent-single-shot":
            raise ValueError("automation package must use commit-intent-single-shot")
        requested = self.spec.capabilities.required | self.spec.capabilities.optional
        dangerous = requested & PRODUCTION_FORBIDDEN
        if dangerous:
            raise ValueError(f"forbidden capabilities requested: {sorted(dangerous)}")
        if not PRODUCTION_FORBIDDEN.issubset(self.spec.capabilities.forbidden):
            raise ValueError("manifest must explicitly forbid production-dangerous capabilities")
        if self.spec.signature.algorithm != "Ed25519":
            raise ValueError("only Ed25519 automation signatures are accepted")
        return self


def validate_manifest(value: dict[str, Any]) -> AutomationManifest:
    return AutomationManifest.model_validate(value)
