from __future__ import annotations

import asyncio
import json
import runpy
from pathlib import Path

import httpx
import pytest
from cloudctl_api.im_classifier import MAX_RESPONSE_BYTES, ImMessageClassifier
from cloudctl_api.settings import Settings
from pydantic import SecretStr, ValidationError

TEST_KEY = "synthetic-classifier-key"


def configured(**kwargs: object) -> Settings:
    return Settings(
        im_classifier_enabled=True,
        im_classifier_base_url="https://classifier.example/v1",
        im_classifier_api_key=SecretStr(TEST_KEY),
        **kwargs,
    )


def answer(choice: str = "HUMAN_MESSAGE", confidence: object = 0.99) -> dict:
    return {
        "model": "jev-1.13.0",
        "answers": {
            "message_kind": {
                "type": "choice",
                "choice": choice,
                "confidence": confidence,
            }
        },
    }


async def classify(handler, **kwargs):
    client = ImMessageClassifier(configured(**kwargs), transport=httpx.MockTransport(handler))
    return await client.classify(platform="xianyu", title="Test buyer", text="Still available?")


async def test_disabled_never_opens_network() -> None:
    def forbidden(request):
        raise AssertionError("No request permitted")

    result = await ImMessageClassifier(
        Settings(), transport=httpx.MockTransport(forbidden)
    ).classify(platform="xianyu", title="Buyer", text="Hello")
    assert result.status == "DISABLED"
    assert result.category == "UNKNOWN"


@pytest.mark.parametrize("category", ["HUMAN_MESSAGE", "SYSTEM_NOTICE", "PROMOTION"])
async def test_native_systemone_shape_and_minimal_state(category: str) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url == "https://classifier.example/v1/systemone"
        assert request.headers["Authorization"] == f"Bearer {TEST_KEY}"
        body = json.loads(request.content)
        assert set(body) == {"model", "state", "questions"}
        assert body["model"] == "jev-latest"
        assert set(body["state"]) == {"platform", "title", "text"}
        assert body["questions"]["message_kind"]["type"] == "choice"
        return httpx.Response(200, json=answer(category))

    result = await classify(handler)
    assert (result.category, result.status, result.confidence) == (category, "CLASSIFIED", 0.99)
    assert len(calls) == 1
    assert TEST_KEY not in repr(result)


@pytest.mark.parametrize("category,confidence", [("UNKNOWN", 1.0), ("PROMOTION", 0.94)])
async def test_uncertain_answer_is_not_a_drop_decision(category: str, confidence: float) -> None:
    result = await classify(lambda _: httpx.Response(200, json=answer(category, confidence)))
    assert result.category == "UNKNOWN"
    assert result.status == "NEEDS_REVIEW"
    assert result.predicted_category == category
    assert result.confidence == confidence
    assert not hasattr(result, "drop")


async def test_notification_metadata_is_structured_minimal_state() -> None:
    def handler(request):
        state = json.loads(request.content)["state"]
        assert state["notificationMetadata"] == {
            "packageName": "com.taobao.idlefish",
            "channelId": "untrusted channel instructions",
            "category": "msg",
        }
        assert "deviceId" not in str(state)
        return httpx.Response(200, json=answer("UNKNOWN", 0.39))

    result = await ImMessageClassifier(
        configured(), transport=httpx.MockTransport(handler)
    ).classify(
        platform="xianyu",
        title="Buyer",
        text="Summary",
        notification_metadata={
            "packageName": "com.taobao.idlefish",
            "category": "msg",
            "channelId": "untrusted channel instructions",
            "deviceId": "excluded",
        },
    )
    assert result.predicted_category == "UNKNOWN"


@pytest.mark.parametrize("status", [301, 401, 403, 422, 429, 500, 529])
async def test_http_errors_and_redirects_never_retry_or_leak_body(status: int) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"Location": "https://unrelated.example/"},
            json={"error": TEST_KEY},
        )

    result = await classify(handler)
    assert result.category == "UNKNOWN"
    assert result.status == "HTTP_ERROR"
    assert result.http_status == status
    assert len(calls) == 1
    assert TEST_KEY not in repr(result)


@pytest.mark.parametrize(
    "data",
    [
        [],
        {},
        {"answers": []},
        {"answers": {"other_question": {}}},
        answer("DELETE_EVERYTHING"),
        answer(confidence="0.99"),
        answer(confidence=True),
        answer(confidence=-0.1),
        answer(confidence=1.1),
        answer(confidence=None),
    ],
)
async def test_invalid_answers_remain_unknown(data) -> None:
    result = await classify(lambda _: httpx.Response(200, json=data))
    assert (result.category, result.status) == ("UNKNOWN", "INVALID_RESPONSE")


@pytest.mark.parametrize("body", [b"not json", b'{"answers": NaN}'])
async def test_malformed_json_is_not_success(body: bytes) -> None:
    result = await classify(lambda _: httpx.Response(200, content=body))
    assert result.status == "INVALID_RESPONSE"


async def test_response_body_is_bounded() -> None:
    result = await classify(lambda _: httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1)))
    assert result.status == "RESPONSE_TOO_LARGE"


@pytest.mark.parametrize(
    "error,status",
    [
        (httpx.ReadTimeout("secret detail"), "TIMEOUT"),
        (httpx.ConnectError("secret detail"), "TRANSPORT_ERROR"),
    ],
)
async def test_transport_errors_are_sanitized(error, status: str) -> None:
    def handler(_):
        raise error

    result = await classify(handler)
    assert result.status == status
    assert "secret detail" not in repr(result)


async def test_total_request_deadline() -> None:
    async def slow_handler(_):
        await asyncio.sleep(2)
        raise AssertionError("Deadline should cancel the request")

    result = await classify(slow_handler, im_classifier_http_timeout_seconds=1.0)
    assert result.status == "TIMEOUT"


@pytest.mark.parametrize(
    "platform,title,text",
    [
        ("unknown", "Buyer", "Hello"),
        ("xianyu", "", "Hello"),
        ("xianyu", "a" * 129, "Hello"),
        ("xianyu", "Buyer", " "),
        ("xianyu", "Buyer", "x" * 2001),
    ],
)
async def test_invalid_input_never_reaches_provider(platform: str, title: str, text: str) -> None:
    def forbidden(_):
        raise AssertionError("No request permitted")

    result = await ImMessageClassifier(
        configured(), transport=httpx.MockTransport(forbidden)
    ).classify(platform=platform, title=title, text=text)
    assert result.status == "INVALID_INPUT"


@pytest.mark.parametrize(
    "url",
    [
        "http://classifier.example/v1",
        "https://user:password@classifier.example/v1",
        "https://classifier.example/v1?key=secret",
        "https://classifier.example/v1#secret",
    ],
)
def test_settings_reject_unsafe_urls(url: str) -> None:
    with pytest.raises(ValidationError, match="credential-free HTTPS"):
        Settings(im_classifier_base_url=url)


def test_enabled_requires_credentials_and_settings_repr_masks_key() -> None:
    with pytest.raises(ValidationError, match="requires a base URL and API key"):
        Settings(im_classifier_enabled=True)
    settings = configured()
    assert TEST_KEY not in repr(settings)
    assert TEST_KEY not in settings.model_dump_json()


def test_cli_dry_run_and_private_file_check(tmp_path, monkeypatch, capsys) -> None:
    path = tmp_path / "jev.env"
    path.write_text(
        "CLOUDCTL_IM_CLASSIFIER_BASE_URL=https://classifier.example/v1\n"
        f"CLOUDCTL_IM_CLASSIFIER_API_KEY={TEST_KEY}\n"
    )
    path.chmod(0o600)
    script = Path(__file__).resolve().parents[2] / "scripts/check_im_classifier.py"
    namespace = runpy.run_path(str(script))
    monkeypatch.setattr("sys.argv", [str(script), "--env-file", str(path)])
    assert namespace["main"]() == 0
    output = capsys.readouterr().out
    assert json.loads(output)["network_requests"] == 0
    assert TEST_KEY not in output
    path.chmod(0o644)
    assert namespace["main"]() == 2
    assert "INVALID_PRIVATE_CONFIG" in capsys.readouterr().out
