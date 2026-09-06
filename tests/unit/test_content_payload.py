from __future__ import annotations

import pytest
from cloudctl_api.content_payload import validate_content_payload


def test_post_payload_is_normalized() -> None:
    payload = validate_content_payload(
        {
            "kind": "post",
            "body": "  自用闲置，功能正常  ",
            "mediaAssetIds": ["asset-1", "asset-1"],
            "targetApp": "xiaohongshu",
            "draftState": "草稿",
        }
    )
    assert payload == {
        "kind": "post",
        "body": "自用闲置，功能正常",
        "mediaAssetIds": ["asset-1"],
        "targetApp": "xiaohongshu",
        "draftState": "草稿",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "post", "body": " ", "draftState": "草稿"},
        {"kind": "post", "body": "ok", "draftState": "已发布"},
        {"kind": "post", "body": "ok", "draftState": "草稿", "script": "alert(1)"},
        {"kind": "post", "body": "ok", "draftState": "草稿", "listingDescription": "nope"},
    ],
)
def test_post_payload_rejects_unsafe_or_invalid_fields(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        validate_content_payload(payload)


def test_generic_payload_still_allowed() -> None:
    assert validate_content_payload({"caption": "version one"}) == {"caption": "version one"}


def test_product_payload_requires_price() -> None:
    payload = validate_content_payload(
        {
            "kind": "product",
            "body": "自用闲置，功能正常",
            "listingPrice": "128",
            "category": "数码",
            "stock": 1,
            "draftState": "草稿",
        }
    )
    assert payload["kind"] == "product"
    assert payload["listingPrice"] == "128"
    with pytest.raises(ValueError):
        validate_content_payload(
            {
                "kind": "product",
                "body": "还没有价格",
                "category": "数码",
                "draftState": "草稿",
            }
        )
