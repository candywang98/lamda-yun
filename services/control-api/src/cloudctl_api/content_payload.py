"""Strict payload contracts for tenant-scoped content revisions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

UNSAFE_KEY_FRAGMENTS = frozenset(
    {
        "adb",
        "captcha",
        "command",
        "credential",
        "frida",
        "mitm",
        "password",
        "pem",
        "privatekey",
        "proxy",
        "script",
        "secret",
        "shell",
        "token",
    }
)
MAX_GENERIC_PAYLOAD_BYTES = 16_384
POST_BODY_MAX_LENGTH = 20_000
POST_MEDIA_LIMIT = 20


class PostPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: Literal["post"]
    body: str = Field(min_length=1, max_length=POST_BODY_MAX_LENGTH)
    media_asset_ids: list[str] = Field(
        default_factory=list,
        alias="mediaAssetIds",
        max_length=POST_MEDIA_LIMIT,
    )
    target_app: Literal["xiaohongshu", "douyin", "unspecified"] = Field(
        default="unspecified",
        alias="targetApp",
    )
    draft_state: Literal["草稿", "待复核"] = Field(alias="draftState")

    @field_validator("body")
    @classmethod
    def body_is_plain_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("body cannot contain NUL")
        stripped = value.strip()
        if not stripped:
            raise ValueError("body is required")
        return stripped

    @field_validator("media_asset_ids")
    @classmethod
    def media_ids_are_bounded(cls, value: list[str]) -> list[str]:
        return _unique_media_ids(value)


class ProductPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: Literal["product"]
    body: str = Field(min_length=1, max_length=POST_BODY_MAX_LENGTH)
    listing_price: str = Field(
        alias="listingPrice",
        min_length=1,
        max_length=32,
        pattern=r"^[0-9]+(\.[0-9]{1,2})?$",
    )
    category: str = Field(min_length=1, max_length=80)
    stock: int = Field(default=1, ge=0, le=100_000)
    media_asset_ids: list[str] = Field(
        default_factory=list,
        alias="mediaAssetIds",
        max_length=POST_MEDIA_LIMIT,
    )
    draft_state: Literal["草稿", "待复核"] = Field(alias="draftState")

    @field_validator("body")
    @classmethod
    def body_is_plain_text(cls, value: str) -> str:
        return PostPayload.body_is_plain_text(value)

    @field_validator("media_asset_ids")
    @classmethod
    def media_ids_are_bounded(cls, value: list[str]) -> list[str]:
        return _unique_media_ids(value)


def _unique_media_ids(value: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or len(item) > 36:
            raise ValueError("mediaAssetIds must be content-library asset ids")
        if item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    return cleaned


def _inspect_keys(value: Any, key: str = "") -> None:
    normalized = key.lower().replace("_", "").replace("-", "")
    if any(fragment in normalized for fragment in UNSAFE_KEY_FRAGMENTS):
        raise ValueError(f"unsafe content field is prohibited: {key}")
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _inspect_keys(child_value, str(child_key))
    elif isinstance(value, list):
        for child_value in value:
            _inspect_keys(child_value, key)


def validate_content_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    _inspect_keys(payload)
    kind = payload.get("kind")
    if kind in {"post", "product"}:
        model = PostPayload if kind == "post" else ProductPayload
        try:
            return model.model_validate(payload).model_dump(mode="json", by_alias=True)
        except ValidationError as exc:
            first = exc.errors(include_url=False)[0]
            location = ".".join(str(part) for part in first["loc"])
            raise ValueError(f"invalid {kind} payload {location}: {first['msg']}") from exc
    encoded = str(payload)
    if len(encoded.encode()) > MAX_GENERIC_PAYLOAD_BYTES:
        raise ValueError("payload exceeds 16 KiB")
    return payload
