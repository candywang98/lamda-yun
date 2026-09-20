"""F10 request contracts for media derivation, pool freezing, and preflight."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class WatermarkRenderRequest(StrictModel):
    text: str = Field(min_length=1, max_length=200)
    position: Literal[
        "top_left",
        "top_right",
        "center",
        "bottom_left",
        "bottom_right",
    ] = "bottom_right"
    opacity: int = Field(default=70, ge=1, le=100)
    font_size: int = Field(default=32, alias="fontSize", ge=8, le=256)
    margin: int = Field(default=24, ge=0, le=2048)
    rule_version_id: str | None = Field(
        default=None, alias="ruleVersionId", min_length=1, max_length=128
    )

    @field_validator("text")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("watermark text cannot be blank")
        return text


class MediaPoolFreezeRequest(StrictModel):
    task_key: str = Field(alias="taskKey", min_length=1, max_length=128)
    group_id: str = Field(alias="groupId", min_length=1, max_length=36)
    count: int = Field(ge=1, le=49)
    seed: str | None = Field(default=None, min_length=1, max_length=128)


class PublishPreflightRequest(StrictModel):
    product_id: str = Field(alias="productId", min_length=1, max_length=36)
    account_id: str = Field(alias="accountId", min_length=1, max_length=36)
    device_id: str = Field(alias="deviceId", min_length=1, max_length=36)
    platform: Literal["xianyu", "xiaohongshu"]
