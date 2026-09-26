"""F16 regressions use in-memory ledgers and fake transports only."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from cloudctl_api.db import WechatAccountRow, WechatDraftRow, WechatPublishRow
from cloudctl_api.settings import Settings
from cloudctl_api.wechat_client import WeChatApiError, WeChatOfficialClient, WeChatTransportError
from test_wechat_publisher import (
    PUBLISHER,
    FakeWeChatTransport,
    authorize,
    create_draft,
    identity,
    register_account,
)
from test_wechat_publisher import api as api


class RecordingTransport(FakeWeChatTransport):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[tuple[str, dict[str, Any]]] = []

    async def post_json(self, url: str, *, json: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.requests.append((url, json))
        return self._next("POST", url)


async def test_official_wire_uses_query_credentials_and_snake_case_cover() -> None:
    transport = RecordingTransport()
    client = WeChatOfficialClient(transport, Settings(env="test", repository_mode="memory"))
    credential = uuid.uuid4().hex + "+&= /"
    article = {"title": "offline fixture", "content": "<p>fixture</p>", "thumbMediaId": "COVER"}
    transport.queue_draft()
    transport.queue_submit()
    transport.queue_get({"publish_status": 1})

    assert await client.add_draft(credential, [article]) == "MEDIA-1"
    assert await client.submit_publish(credential, "MEDIA-1") == "PUBLISH-1"
    assert await client.get_publish(credential, "PUBLISH-1") == {"publish_status": 1}

    assert len(transport.requests) == 3
    expected_paths = [
        "/cgi-bin/draft/add",
        "/cgi-bin/freepublish/submit",
        "/cgi-bin/freepublish/get",
    ]
    for (url, payload), path in zip(transport.requests, expected_paths, strict=True):
        assert urlsplit(url).path == path
        assert parse_qs(urlsplit(url).query) == {"access_token": [credential]}
        assert "access_token" not in payload
    assert transport.requests[0][1] == {
        "articles": [
            {"title": "offline fixture", "content": "<p>fixture</p>", "thumb_media_id": "COVER"}
        ]
    }
    assert transport.requests[1][1] == {"media_id": "MEDIA-1"}
    assert transport.requests[2][1] == {"publish_id": "PUBLISH-1"}
    assert article["thumbMediaId"] == "COVER"  # Preserve the frozen internal document.


@pytest.mark.parametrize("status", [301, 401, 429, 500])
async def test_non_success_http_never_becomes_a_successful_submit(status: int) -> None:
    transport = RecordingTransport()
    transport._queue("submit", status=status, body={"publish_id": "UNTRUSTED"}, error=None)
    client = WeChatOfficialClient(transport, Settings(env="test", repository_mode="memory"))
    with pytest.raises(WeChatTransportError):
        await client.submit_publish(uuid.uuid4().hex, "MEDIA-1")
    assert transport.count("freepublish/submit") == 1


@pytest.mark.parametrize("expires_in", [0, -1, True, "7200"])
async def test_malformed_token_expiry_is_rejected(expires_in: Any) -> None:
    transport = RecordingTransport()
    transport._queue(
        "token",
        status=200,
        body={"access_token": uuid.uuid4().hex, "expires_in": expires_in},
        error=None,
    )
    client = WeChatOfficialClient(transport, Settings(env="test", repository_mode="memory"))
    with pytest.raises(WeChatTransportError, match="malformed"):
        await client.fetch_token("offline-app", uuid.uuid4().hex)


@pytest.mark.parametrize(
    "change", ["media_id", "article", "account_id", "account_status", "intent_status"]
)
async def test_submit_rechecks_frozen_intent_after_token_wait(
    api,  # noqa: F811 - pytest fixture shadows imported fixture
    monkeypatch,
    change: str,
) -> None:
    client, app, transport = api
    account = await register_account(client)
    draft_response = await create_draft(client, transport, account["id"], "draft-recheck")
    assert draft_response.status_code == 201
    draft = draft_response.json()
    authorized = await authorize(client, draft["id"], "publish-recheck")
    assert authorized.status_code == 201
    publish_id = authorized.json()["id"]
    other_account = await register_account(client, app_id="wxabcdefabcdefab")
    service = app.state.wechat_publisher_service
    original = service._token_for

    async def token_after_change(tenant_id, account_id):
        value = await original(tenant_id, account_id)
        async with app.state.database.unit_of_work() as session:
            if change == "account_status":
                row = await session.get(WechatAccountRow, account_id)
                row.status = "REVOKED"
            elif change == "intent_status":
                row = await session.get(WechatPublishRow, publish_id)
                row.status = "FAILED"
            else:
                row = await session.get(WechatDraftRow, draft["id"])
                if change == "article":
                    row.article = {**row.article, "title": "changed after authorization"}
                elif change == "account_id":
                    row.account_id = other_account["id"]
                else:
                    row.media_id = "CHANGED-MEDIA"
        return value

    monkeypatch.setattr(service, "_token_for", token_after_change)
    response = await client.post(
        f"/api/v1/wechat/publishes/{publish_id}:submit",
        headers=identity(user=PUBLISHER, role="publisher"),
    )
    assert response.status_code == 409, response.text
    assert transport.count("freepublish/submit") == 0
    async with app.state.database.unit_of_work() as session:
        row = await session.get(WechatPublishRow, publish_id)
        assert row.submit_attempts == 0


async def test_late_token_error_does_not_overwrite_another_submit(api, monkeypatch) -> None:  # noqa: F811 - pytest fixture shadows imported fixture
    client, app, transport = api
    account = await register_account(client)
    draft = (await create_draft(client, transport, account["id"], "draft-race")).json()
    authorized = await authorize(client, draft["id"], "publish-race")
    assert authorized.status_code == 201
    publish_id = authorized.json()["id"]
    service = app.state.wechat_publisher_service
    original = service._token_for
    first = True
    transport.queue_submit(publish_id="WINNING-PUBLISH")

    async def racing_token(tenant_id, account_id):
        nonlocal first
        if not first:
            return await original(tenant_id, account_id)
        first = False
        winner = await client.post(
            f"/api/v1/wechat/publishes/{publish_id}:submit",
            headers=identity(user=PUBLISHER, role="publisher"),
        )
        assert winner.status_code == 200, winner.text
        raise WeChatApiError(40014, "expired token fixture")

    monkeypatch.setattr(service, "_token_for", racing_token)
    response = await client.post(
        f"/api/v1/wechat/publishes/{publish_id}:submit",
        headers=identity(user=PUBLISHER, role="publisher"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["replayed"] is True
    assert transport.count("freepublish/submit") == 1
    async with app.state.database.unit_of_work() as session:
        row = await session.get(WechatPublishRow, publish_id)
        assert row.status == "SUBMITTED"
        assert row.publish_id == "WINNING-PUBLISH"
        assert row.error_code is None
        assert row.submit_attempts == 1


async def test_draft_disappearance_after_official_response_is_not_retried(api, monkeypatch) -> None:  # noqa: F811 - pytest fixture shadows imported fixture
    client, app, transport = api
    account = await register_account(client)
    service = app.state.wechat_publisher_service
    original = service._push_draft

    async def drop_after_response(actor, account_id, draft_id, article):
        result = await original(actor, account_id, draft_id, article)
        async with app.state.database.unit_of_work() as session:
            row = await session.get(WechatDraftRow, draft_id)
            await session.delete(row)
        return result

    monkeypatch.setattr(service, "_push_draft", drop_after_response)
    response = await create_draft(client, transport, account["id"], "draft-disappeared")
    assert response.status_code == 404, response.text
    assert transport.count("draft/add") == 1
    assert transport.count("freepublish/submit") == 0


async def submitted_publish(api) -> str:  # noqa: F811 - pytest fixture shadows imported fixture
    client, _, transport = api
    account = await register_account(client)
    draft = (await create_draft(client, transport, account["id"], "poll-draft")).json()
    intent = await authorize(client, draft["id"], "poll-intent")
    assert intent.status_code == 201, intent.text
    publish_id = intent.json()["id"]
    transport.queue_submit(publish_id="OFFICIAL-POLL")
    submitted = await client.post(
        f"/api/v1/wechat/publishes/{publish_id}:submit",
        headers=identity(user=PUBLISHER, role="publisher"),
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"
    return publish_id


def poll_document(status: Any) -> dict[str, Any]:
    return {
        "publish_id": "OFFICIAL-POLL",
        "publish_status": status,
        "article_detail": {
            "count": 1,
            "item": [{"idx": 1, "article_url": "https://mp.example/offline-fixture"}],
        },
    }


@pytest.mark.parametrize(
    ("status", "expected", "error"),
    [
        (0, "PUBLISHED", None),
        (1, "SUBMITTED", None),
        (2, "FAILED", "WECHAT_ORIGINALITY_REJECTED"),
        (3, "FAILED", "WECHAT_PUBLISH_REJECTED"),
        (4, "FAILED", "WECHAT_REVIEW_REJECTED"),
        (5, "FAILED", "WECHAT_ARTICLES_DELETED"),
        (6, "FAILED", "WECHAT_ARTICLES_BANNED"),
    ],
)
async def test_official_numeric_poll_states_never_resubmit(api, status, expected, error) -> None:  # noqa: F811 - pytest fixture shadows imported fixture
    client, _, transport = api
    publish_id = await submitted_publish(api)
    transport.queue_get(poll_document(status))
    response = await client.post(
        f"/api/v1/wechat/publishes/{publish_id}:poll", headers=identity(role="viewer")
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == expected
    assert result["errorCode"] == error
    assert result["submitAttempts"] == 1
    assert result["pollCount"] == 1
    assert (result["resolvedAt"] is None) == (status == 1)
    assert (result["articleUrl"] is not None) == (status == 0)
    if status in (5, 6):
        assert "published, then" in result["detail"]
    replay = await client.post(
        f"/api/v1/wechat/publishes/{publish_id}:submit",
        headers=identity(user=PUBLISHER, role="publisher"),
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert transport.count("freepublish/submit") == 1


@pytest.mark.parametrize("status", [False, True, None, "publish", "fail", "0", 0.0, -1, 7])
async def test_malformed_poll_status_leaves_ledger_unsettled(api, status) -> None:  # noqa: F811 - pytest fixture shadows imported fixture
    client, _, transport = api
    publish_id = await submitted_publish(api)
    transport.queue_get(poll_document(status))
    response = await client.post(
        f"/api/v1/wechat/publishes/{publish_id}:poll", headers=identity(role="viewer")
    )
    assert response.status_code == 409, response.text
    assert "WECHAT_POLL_MALFORMED" in response.text
    stored = await client.get(
        f"/api/v1/wechat/publishes/{publish_id}", headers=identity(role="viewer")
    )
    assert stored.json()["status"] == "SUBMITTED"
    assert stored.json()["resolvedAt"] is None
    assert stored.json()["pollCount"] == 0
    assert transport.count("freepublish/submit") == 1


@pytest.mark.parametrize("change", ["missing_id", "other_id", "missing_url", "blank_url"])
async def test_poll_requires_matching_identity_and_success_evidence(api, change) -> None:  # noqa: F811 - pytest fixture shadows imported fixture
    client, _, transport = api
    publish_id = await submitted_publish(api)
    document = poll_document(0)
    if change == "missing_id":
        document.pop("publish_id")
    elif change == "other_id":
        document["publish_id"] = "ANOTHER-PUBLISH"
    elif change == "missing_url":
        document.pop("article_detail")
    else:
        document["article_detail"]["item"][0]["article_url"] = "   "
    transport.queue_get(document)
    response = await client.post(
        f"/api/v1/wechat/publishes/{publish_id}:poll", headers=identity(role="viewer")
    )
    assert response.status_code == 409, response.text
    stored = await client.get(
        f"/api/v1/wechat/publishes/{publish_id}", headers=identity(role="viewer")
    )
    assert stored.json()["status"] == "SUBMITTED"
    assert stored.json()["articleUrl"] is None
    assert stored.json()["resolvedAt"] is None
    assert transport.count("freepublish/submit") == 1


@pytest.mark.parametrize("winner_status", [0, 4])
@pytest.mark.parametrize("late_status", [0, 3, "api_error"])
async def test_late_poll_preserves_concurrently_confirmed_terminal_state(
    api,  # noqa: F811 - pytest fixture shadows imported fixture
    monkeypatch,
    winner_status,
    late_status,
) -> None:
    client, app, transport = api
    publish_id = await submitted_publish(api)
    service = app.state.wechat_publisher_service
    original = service.client.get_publish
    first = True
    winning_view = {}
    transport.queue_get(poll_document(winner_status))

    async def racing_poll(token, official_id):
        nonlocal first
        if not first:
            return await original(token, official_id)
        first = False
        winner = await client.post(
            f"/api/v1/wechat/publishes/{publish_id}:poll", headers=identity(role="viewer")
        )
        assert winner.status_code == 200, winner.text
        persisted = await client.get(
            f"/api/v1/wechat/publishes/{publish_id}", headers=identity(role="viewer")
        )
        assert persisted.status_code == 200, persisted.text
        assert persisted.json()["status"] == ("PUBLISHED" if winner_status == 0 else "FAILED")
        assert persisted.json()["resolvedAt"] is not None
        assert persisted.json()["pollCount"] == 1
        winning_view.update(persisted.json())
        if late_status == "api_error":
            raise WeChatApiError(40014, "late token rejection fixture")
        return poll_document(late_status)

    monkeypatch.setattr(service.client, "get_publish", racing_poll)
    response = await client.post(
        f"/api/v1/wechat/publishes/{publish_id}:poll", headers=identity(role="viewer")
    )
    assert response.status_code == 200, response.text
    assert response.json() == winning_view
    stored = await client.get(
        f"/api/v1/wechat/publishes/{publish_id}", headers=identity(role="viewer")
    )
    assert stored.json() == winning_view
    assert transport.count("freepublish/submit") == 1


@pytest.mark.parametrize("change", ["publish_id", "account_id"])
async def test_poll_rechecks_ledger_identity_after_wait(api, monkeypatch, change) -> None:  # noqa: F811 - pytest fixture shadows imported fixture
    client, app, transport = api
    publish_id = await submitted_publish(api)
    other = await register_account(client, app_id="wxabcdefabcdefab")
    service = app.state.wechat_publisher_service
    original = service.client.get_publish
    transport.queue_get(poll_document(0))

    async def change_identity(token, official_id):
        result = await original(token, official_id)
        async with app.state.database.unit_of_work() as session:
            row = await session.get(WechatPublishRow, publish_id)
            if change == "publish_id":
                row.publish_id = "CHANGED-OFFICIAL-ID"
            else:
                row.account_id = other["id"]
        return result

    monkeypatch.setattr(service.client, "get_publish", change_identity)
    response = await client.post(
        f"/api/v1/wechat/publishes/{publish_id}:poll", headers=identity(role="viewer")
    )
    assert response.status_code == 409, response.text
    assert "identity changed" in response.text
    assert transport.count("freepublish/submit") == 1
