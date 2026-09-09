"""Signed local Recipe packages interpreted on the phone, not by cloud click loops."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .registry import package_signature_payload, verify_package_signature

ALLOWED_ACTIONS = frozenset(
    {"tap", "input", "scroll", "extract", "wait", "launch", "media", "log", "checkpoint"}
)
FORBIDDEN_ACTIONS = frozenset({"shell", "dex", "js", "javascript", "frida", "eval", "adb"})
ALLOWED_APPS = {
    "xianyu": "com.taobao.idlefish",
    "xiaohongshu": "com.xingin.xhs",
    "companion": "com.company.cloudctl.companion",
}
CURRENT_ENGINE_VERSION = 1
TERMINAL_ID = "SUCCEEDED"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RecipeManifest(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    signing_key_id: str = Field(alias="signingKeyId", min_length=1, max_length=80)
    min_engine_version: int = Field(alias="minEngineVersion", ge=1, le=1000)
    platform: Literal["xianyu", "xiaohongshu", "companion"]
    app: str
    command_types: list[str] = Field(alias="commandTypes", min_length=1, max_length=16)


class RecipeState(StrictModel):
    state_id: str = Field(alias="stateId", min_length=1, max_length=128)
    entry_guard: str | None = Field(default=None, alias="entryGuard", max_length=160)
    action: str
    locator_ref: str | None = Field(default=None, alias="locatorRef", max_length=160)
    postcondition: str | None = Field(default=None, max_length=160)
    on_success: str = Field(alias="onSuccess", min_length=1, max_length=128)
    on_failure: str | None = Field(default=None, alias="onFailure", max_length=128)
    on_pause: Literal["WAITING_USER"] | None = Field(default=None, alias="onPause")
    terminal: bool = False

    @model_validator(mode="after")
    def whitelist_action(self) -> RecipeState:
        if self.action in FORBIDDEN_ACTIONS or self.action not in ALLOWED_ACTIONS:
            raise ValueError(f"action is not on the APK whitelist: {self.action}")
        if ".." in (self.locator_ref or "") or (self.locator_ref or "").startswith("/"):
            raise ValueError("locatorRef path traversal is not allowed")
        return self


class RecipeGraph(StrictModel):
    start_state_id: str = Field(alias="startStateId")
    max_iterations: int = Field(alias="maxIterations", ge=1, le=200)
    max_duration_ms: int = Field(alias="maxDurationMs", ge=1000, le=900_000)
    safe_checkpoint: str | None = Field(default=None, alias="safeCheckpoint")
    resume_guard: str | None = Field(default=None, alias="resumeGuard", max_length=160)
    commit_action_id: str | None = Field(default=None, alias="commitActionId")
    states: list[RecipeState] = Field(min_length=1, max_length=80)


class RecipeSignature(StrictModel):
    algorithm: Literal["Ed25519"]
    key_id: str = Field(alias="keyId")
    digest: str


class RecipePackage(StrictModel):
    api_version: Literal["cloudctl.recipe/v1"] = Field(alias="apiVersion")
    kind: Literal["LocalRecipePackage"]
    manifest: RecipeManifest
    graph: RecipeGraph
    signature: RecipeSignature

    @model_validator(mode="after")
    def bounded_graph_and_app(self) -> RecipePackage:
        if self.manifest.app != ALLOWED_APPS[self.manifest.platform]:
            raise ValueError("manifest app does not match platform")
        if self.manifest.min_engine_version > CURRENT_ENGINE_VERSION:
            raise ValueError("UNSUPPORTED_RECIPE")
        ids = {state.state_id for state in self.graph.states}
        if len(ids) != len(self.graph.states):
            raise ValueError("stateId values must be unique")
        if self.graph.start_state_id not in ids:
            raise ValueError("startStateId is missing")
        reachable_terminal = False
        for state in self.graph.states:
            for target in (state.on_success, state.on_failure):
                if target in {None, TERMINAL_ID, "FAILED", "WAITING_USER"}:
                    if target == TERMINAL_ID:
                        reachable_terminal = True
                    continue
                if target not in ids:
                    raise ValueError(f"branch target is unknown: {target}")
            if state.terminal or state.on_success == TERMINAL_ID:
                reachable_terminal = True
        if not reachable_terminal:
            raise ValueError("state graph has no terminal exit")
        return self


def canonical_recipe_bytes(package: dict[str, Any]) -> bytes:
    body = {
        "apiVersion": package["apiVersion"],
        "kind": package["kind"],
        "manifest": {k: v for k, v in package["manifest"].items() if k != "hash"},
        "graph": package["graph"],
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def validate_recipe_package(
    value: dict[str, Any],
    *,
    public_key_base64: str | None = None,
    engine_version: int = CURRENT_ENGINE_VERSION,
) -> RecipePackage:
    parsed = RecipePackage.model_validate(value)
    digest = hashlib.sha256(canonical_recipe_bytes(value)).hexdigest()
    if parsed.manifest.hash != digest:
        raise ValueError("recipe hash does not match canonical graph")
    if parsed.manifest.min_engine_version > engine_version:
        raise ValueError("UNSUPPORTED_RECIPE")
    if public_key_base64:
        payload = package_signature_payload(
            artifact_sha256=parsed.manifest.hash,
            manifest=value["manifest"],
            sbom_ref="recipe://local",
            sbom_sha256=parsed.manifest.hash,
        )
        verify_package_signature(
            public_key_base64=public_key_base64,
            signature_base64=parsed.signature.digest,
            payload=payload,
        )
    return parsed
