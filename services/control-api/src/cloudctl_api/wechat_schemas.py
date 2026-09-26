"""Request models for the WeChat Official Account publisher (V1-26)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class WechatAccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    app_id: str = Field(
        alias="appId",
        min_length=6,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="WeChat Official Account appId (e.g. wx1234567890abcdef).",
    )
    app_secret: SecretStr = Field(
        alias="appSecret",
        min_length=16,
        max_length=128,
        description="appSecret; stored encrypted at rest, never returned or logged.",
    )
    display_label: str = Field(alias="displayLabel", min_length=1, max_length=160)


class WechatDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    account_id: str = Field(alias="accountId", min_length=36, max_length=36)
    title: str = Field(min_length=1, max_length=64, description="Official limit: 64 characters.")
    content_html: str = Field(
        alias="contentHtml",
        min_length=1,
        max_length=20_000,
        description="Article HTML body pushed to draft/add.",
    )
    digest: str | None = Field(default=None, max_length=120)
    author: str | None = Field(default=None, max_length=64)
    thumb_media_id: str | None = Field(
        alias="thumbMediaId", default=None, max_length=256, description="Cover material media id."
    )


class WechatPublishAuthorize(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    authorization_note: str | None = Field(alias="authorizationNote", default=None, max_length=500)
