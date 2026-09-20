"""WeChat Official Account publisher (V1-26): ledger, idempotency, isolation.

All external calls go through a fake transport; no test touches the network.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import sqlite3
import uuid
from collections import deque
from collections.abc import AsyncIterator

import httpx
import pytest
from alembic import command
from alembic.config import Config
from cloudctl_api import create_app
from cloudctl_api.db import AuditEventRow, WechatAccountRow, WechatDraftRow
from cloudctl_api.settings import Settings
from cloudctl_api.wechat_client import WeChatApiError, WeChatTransportError
from cryptography.fernet import Fernet
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select
from test_control_api_migrations import ALEMBIC_INI, migration_config, table_columns, tables

TENANT = "00000000-0000-7000-8000-000000000111"
TENANT_B = "00000000-0000-7000-8000-000000000999"
EDITOR = "00000000-0000-7000-8000-000000000222"
APPROVER = "00000000-0000-7000-8000-000000000333"
PUBLISHER = "00000000-0000-7000-8000-000000000555"
FOREIGN_USER = "00000000-0000-7000-8000-000000000777"

SECRET_A = "super-secret-appsecret-000001"
SECRET_B = "super-secret-appsecret-000002"
SECRET_FERNET_KEY = Fernet.generate_key().decode()


WECHAT_REVISION = "20260915_0019"
WECHAT_PARENT = "20260914_0018"

_ENDPOINTS = {
    "/cgi-bin/token": "token",
    "/cgi-bin/draft/add": "draft",
    "/cgi-bin/freepublish/submit": "submit",
    "/cgi-bin/freepublish/get": "get",
}


class FakeWeChatTransport:
    """Records every call and replays scripted responses. Zero real network.

    Responses are queued per official endpoint, so a cached token call or an
    idempotent replay cannot consume a response scripted for another endpoint.
    The token endpoint answers with TOKEN-A when nothing else is scripted.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self._queues: dict[str, deque[tuple[int, dict, Exception | None]]] = {
            name: deque() for name in ("token", "draft", "submit", "get")
        }

    def _queue(self, endpoint: str, *, status: int, body: dict | None, error: Exception | None):
        self._queues[endpoint].append((status, body if body is not None else {}, error))

    def queue_token(self, *, token: str = "TOKEN-A", expires_in: int = 7200) -> None:
        self._queue(
            "token",
            status=200,
            body={"access_token": token, "expires_in": expires_in},
            error=None,
        )

    def queue_draft(self, *, media_id: str = "MEDIA-1") -> None:
        self._queue("draft", status=200, body={"media_id": media_id}, error=None)

    def queue_draft_error(self, error: Exception) -> None:
        self._queue("draft", status=200, body=None, error=error)

    def queue_submit(self, *, publish_id: str = "PUBLISH-1") -> None:
        self._queue("submit", status=200, body={"publish_id": publish_id}, error=None)

    def queue_submit_error(self, error: Exception) -> None:
        self._queue("submit", status=200, body=None, error=error)

    def queue_get(self, body: dict) -> None:
        self._queue("get", status=200, body=body, error=None)

    def _next(self, method: str, url: str) -> tuple[int, dict]:
        self.calls.append((method, url))
        endpoint = next((name for path, name in _ENDPOINTS.items() if path in url), None)
        if endpoint is None:
            raise AssertionError(f"unexpected wechat call: {method} {url}")
        queue = self._queues[endpoint]
        if not queue:
            if endpoint == "token":
                return 200, {"access_token": "TOKEN-A", "expires_in": 7200}
            raise AssertionError(f"unexpected {endpoint} call; script a response first")
        status, body, error = queue.popleft()
        if error is not None:
            raise error
        return status, body

    async def post_json(self, url: str, *, json=None) -> tuple[int, dict]:
        return self._next("POST", url)

    async def get_json(self, url: str, *, params=None) -> tuple[int, dict]:
        return self._next("GET", url)

    def count(self, fragment: str) -> int:
        return sum(1 for _, url in self.calls if fragment in url)


def identity(
    *, tenant: str = TENANT, user: str = EDITOR, role: str = "content_editor", mfa: bool = True
) -> dict[str, str]:
    return {
        "X-Tenant-Id": tenant,
        "X-User-Id": user,
        "X-Roles": role,
        "X-MFA": str(mfa).lower(),
        "X-Request-Id": str(uuid.uuid4()),
    }


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI, FakeWeChatTransport]]:
    transport = FakeWeChatTransport()
    app = create_app(
        Settings(env="test", repository_mode="memory", dev_auth_bypass=True),
        wechat_transport=transport,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, app, transport


@pytest.fixture
async def encrypted_api() -> (
    AsyncIterator[tuple[httpx.AsyncClient, FastAPI, FakeWeChatTransport]]
):
    """Same as ``api`` but with a Fernet key so secrets are encrypted at rest."""
    transport = FakeWeChatTransport()
    app = create_app(
        Settings(
            env="test",
            repository_mode="memory",
            dev_auth_bypass=True,
            wechat_secret_encryption_key=SecretStr(SECRET_FERNET_KEY),
        ),
        wechat_transport=transport,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, app, transport

async def register_account(
    client: httpx.AsyncClient,
    *,
    app_id: str = "wx1234567890abcdef",
    secret: str = SECRET_A,
    label: str = "测试公众号",
    tenant: str = TENANT,
    role: str = "content_editor",
) -> dict:
    response = await client.post(
        "/api/v1/wechat/accounts",
        headers=identity(tenant=tenant, role=role),
        json={"appId": app_id, "appSecret": secret, "displayLabel": label},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_draft(
    client: httpx.AsyncClient,
    transport: FakeWeChatTransport,
    account_id: str,
    key: str,
    *,
    media_id: str = "MEDIA-1",
    title: str = "V1 发布切片验证",
    draft_error: Exception | None = None,
    tenant: str = TENANT,
    role: str = "content_editor",
    queue: bool = True,
) -> httpx.Response:
    """Post a draft request; script the official response only when expected.

    ``queue=False`` is used for requests that must be answered without an
    official API call (idempotent replays, validation conflicts). The fake then
    has an empty per-endpoint queue, so any unexpected call raises
    ``AssertionError`` instead of silently consuming a leftover response that
    was scripted for a different request.
    """
    if queue:
        if draft_error is None:
            transport.queue_draft(media_id=media_id)
        else:
            transport.queue_draft_error(draft_error)
    return await client.post(
        "/api/v1/wechat/drafts",
        headers={**identity(tenant=tenant, role=role), "Idempotency-Key": key},
        json={
            "accountId": account_id,
            "title": title,
            "contentHtml": "<h2>标题</h2><p>正文内容</p>",
            "digest": "摘要",
            "author": "运营",
        },
    )


async def authorize(
    client: httpx.AsyncClient,
    draft_id: str,
    key: str,
    *,
    tenant: str = TENANT,
    role: str = "approver",
    user: str = APPROVER,
) -> httpx.Response:
    return await client.post(
        f"/api/v1/wechat/drafts/{draft_id}:authorize-publish",
        headers={**identity(tenant=tenant, user=user, role=role), "Idempotency-Key": key},
        json={"authorizationNote": "内容已审阅，允许发布"},
    )


async def audit_actions(app: FastAPI, tenant: str = TENANT) -> list[dict]:
    async with app.state.database.unit_of_work() as session:
        rows = (
            await session.scalars(
                select(AuditEventRow)
                .where(AuditEventRow.tenant_id == tenant)
                .order_by(AuditEventRow.occurred_at)
            )
        ).all()
        return [
            {
                "action": row.action,
                "resourceType": row.resource_type,
                "resourceId": row.resource_id,
                "result": row.result,
                "metadata": row.metadata_json,
            }
            for row in rows
        ]


# --------------------------------------------------------------- accounts


async def test_account_registration_hides_secret_and_audits(api):
    client, app, transport = api
    account = await register_account(client)

    assert account["appId"] == "wx1234567890abcdef"
    assert account["status"] == "ACTIVE"
    assert "appSecret" not in account
    assert account["secretFingerprint"] and len(account["secretFingerprint"]) == 12
    assert SECRET_A not in json.dumps(account)

    # The plaintext secret never reaches the stored envelope or audit metadata.
    async with app.state.database.unit_of_work() as session:
        row = await session.get(WechatAccountRow, account["id"])
        assert row is not None
        assert SECRET_A not in row.secret_ciphertext
        assert row.secret_fingerprint != SECRET_A
    events = await audit_actions(app)
    registered = [e for e in events if e["action"] == "wechat.account.registered"]
    assert len(registered) == 1
    assert SECRET_A not in json.dumps(registered[0]["metadata"])
    assert transport.calls == []  # registration itself never calls the official API

    # Duplicate app per tenant and viewer role are rejected.
    duplicate = await client.post(
        "/api/v1/wechat/accounts",
        headers=identity(),
        json={"appId": "wx1234567890abcdef", "appSecret": SECRET_A, "displayLabel": "重复"},
    )
    assert duplicate.status_code == 409
    viewer = await client.post(
        "/api/v1/wechat/accounts",
        headers=identity(role="viewer"),
        json={"appId": "wxabcdefabcdefab", "appSecret": SECRET_A, "displayLabel": "越权"},
    )
    assert viewer.status_code == 403


async def test_fernet_key_encrypts_secret_at_rest_and_round_trips(encrypted_api):
    """With a configured key the stored envelope is Fernet, not base64."""
    client, app, transport = encrypted_api
    account = await register_account(client)

    cipher = app.state.wechat_publisher_service.cipher
    assert cipher.encrypted is True
    assert cipher.key_id.startswith("fernet-")

    async with app.state.database.unit_of_work() as session:
        row = await session.get(WechatAccountRow, account["id"])
        assert row is not None
        assert row.secret_ciphertext.startswith("v1:")
        assert not row.secret_ciphertext.startswith("dev-b64:")
        assert SECRET_A not in row.secret_ciphertext
        assert row.secret_key_id == cipher.key_id
        # Round trip: the stored envelope decrypts back to the plaintext secret.
        assert cipher.decrypt(row.secret_ciphertext) == SECRET_A

    # Views keep exposing only the fingerprint and the audit metadata stays clean.
    assert "appSecret" not in account
    assert len(account["secretFingerprint"]) == 12
    assert SECRET_A not in json.dumps(account)
    events = await audit_actions(app)
    registered = [e for e in events if e["action"] == "wechat.account.registered"]
    assert len(registered) == 1
    assert registered[0]["metadata"]["secretEncryptedAtRest"] is True
    assert SECRET_A not in json.dumps(events)
    assert transport.calls == []  # registration never calls the official API


async def test_fernet_secret_decrypts_for_official_token_call(encrypted_api):
    """The official-API flow decrypts the stored envelope to fetch a token."""
    client, _app, transport = encrypted_api
    account = await register_account(client)
    response = await create_draft(
        client, transport, account["id"], "fernet-token-1", title="Fernet 解密链路"
    )
    assert response.status_code == 201, response.text
    assert transport.count("/cgi-bin/token") == 1
    assert transport.count("/cgi-bin/draft/add") == 1


async def test_without_key_dev_falls_back_to_marked_base64_envelope(api):
    """Development/test stays runnable without a key, with a marked envelope."""
    client, app, _transport = api
    account = await register_account(client)

    cipher = app.state.wechat_publisher_service.cipher
    assert cipher.encrypted is False
    assert cipher.key_id == "development-unencrypted"

    async with app.state.database.unit_of_work() as session:
        row = await session.get(WechatAccountRow, account["id"])
        assert row is not None
        assert row.secret_ciphertext.startswith("dev-b64:")
        assert SECRET_A not in row.secret_ciphertext
        assert cipher.decrypt(row.secret_ciphertext) == SECRET_A


# ----------------------------------------------------------------- drafts


async def test_draft_creation_is_idempotent_and_reuses_cached_token(api):
    client, app, transport = api
    account = await register_account(client)

    first = await create_draft(client, transport, account["id"], "draft-key-1")
    assert first.status_code == 201, first.text
    assert first.headers["Idempotency-Replayed"] == "false"
    body = first.json()
    assert body["status"] == "READY"
    assert body["mediaId"] == "MEDIA-1"
    assert body["article"]["title"] == "V1 发布切片验证"

    # Same Idempotency-Key + same body replays without new official calls: the
    # empty draft queue makes any re-call fail loudly.
    replay = await create_draft(client, transport, account["id"], "draft-key-1", queue=False)
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["id"] == body["id"]
    assert transport.count("/cgi-bin/token") == 1  # cached access token
    assert transport.count("/cgi-bin/draft/add") == 1

    # Same key with different content is a conflict, again without API calls.
    conflict = await create_draft(
        client, transport, account["id"], "draft-key-1", title="改动", queue=False
    )
    assert conflict.status_code == 409
    assert transport.count("/cgi-bin/draft/add") == 1

    # An indeterminate draft/add keeps UNKNOWN and is never re-called on replay.
    unknown = await create_draft(
        client, transport, account["id"], "draft-key-2", draft_error=WeChatTransportError("t/o")
    )
    assert unknown.status_code == 201, unknown.text
    assert unknown.json()["status"] == "UNKNOWN"
    unknown_replay = await create_draft(
        client, transport, account["id"], "draft-key-2", queue=False
    )
    assert unknown_replay.status_code == 200
    assert unknown_replay.json()["status"] == "UNKNOWN"
    assert transport.count("/cgi-bin/draft/add") == 2  # one per distinct idempotency key

    # A definitive official rejection fails the stored draft and surfaces 409.
    rejected = await create_draft(
        client,
        transport,
        account["id"],
        "draft-key-3",
        draft_error=WeChatApiError(40007, "invalid media"),
    )
    assert rejected.status_code == 409
    async with app.state.database.unit_of_work() as session:
        row = await session.scalar(
            select(WechatDraftRow).where(
                WechatDraftRow.tenant_id == TENANT,
                WechatDraftRow.idempotency_key == "draft-key-3",
            )
        )
        assert row is not None and row.status == "FAILED"
        assert row.error_code == "WECHAT_40007"
    events = await audit_actions(app)
    assert "wechat.draft.created" in {e["action"] for e in events}
    assert "wechat.draft.failed" in {e["action"] for e in events}


# ------------------------------------------------------------ token cache


async def test_token_cache_is_single_flight_and_tenant_scoped(api):
    client, app, transport = api
    await register_account(client, app_id="wxaaaaaaaaaaaaaaaa", secret=SECRET_A)
    await register_account(client, app_id="wxbbbbbbbbbbbbbbbb", secret=SECRET_B)
    service = app.state.wechat_publisher_service

    # Five concurrent acquisitions for the same account: one upstream fetch.
    transport.queue_token(token="TOKEN-A")
    tokens = await asyncio.gather(
        *[service.tokens.get_token(TENANT, "wxaaaaaaaaaaaaaaaa", SECRET_A) for _ in range(5)]
    )
    assert set(tokens) == {"TOKEN-A"}
    assert transport.count("/cgi-bin/token") == 1

    # Cached afterwards, still no second fetch.
    again = await service.tokens.get_token(TENANT, "wxaaaaaaaaaaaaaaaa", SECRET_A)
    assert again == "TOKEN-A"
    assert transport.count("/cgi-bin/token") == 1

    # A different account (different credential) gets its own token.
    transport.queue_token(token="TOKEN-B")
    token_b = await service.tokens.get_token(TENANT, "wxbbbbbbbbbbbbbbbb", SECRET_B)
    assert token_b == "TOKEN-B"
    assert transport.count("/cgi-bin/token") == 2

    # Tenant isolation: another tenant with the same appId fetches separately.
    transport.queue_token(token="TOKEN-B-TENANT")
    cross = await service.tokens.get_token(TENANT_B, "wxaaaaaaaaaaaaaaaa", SECRET_A)
    assert cross == "TOKEN-B-TENANT"
    assert transport.count("/cgi-bin/token") == 3

    # Expiry: a token whose lifetime falls inside the refresh margin is
    # fetched again on the next use (a fresh cache key avoids the 7200s token
    # that is legitimately still cached above).
    transport.queue_token(token="TOKEN-SHORT", expires_in=1)
    short = await service.tokens.get_token(TENANT, "wxcccccccccccccccc", SECRET_A)
    assert short == "TOKEN-SHORT"
    transport.queue_token(token="TOKEN-REFRESHED")
    refreshed = await service.tokens.get_token(TENANT, "wxcccccccccccccccc", SECRET_A)
    assert refreshed == "TOKEN-REFRESHED"
    assert transport.count("/cgi-bin/token") == 5


# --------------------------------------------------------- publish ledger


async def test_publish_requires_authorization_then_executes_once(api):
    client, app, transport = api
    account = await register_account(client)
    draft = (await create_draft(client, transport, account["id"], "pub-draft-1")).json()

    # A publisher cannot authorize: the gate needs publish.approve.
    denied = await authorize(client, draft["id"], "auth-denied", role="publisher", user=PUBLISHER)
    assert denied.status_code == 403
    # Without any intent there is nothing to submit.
    missing = await client.post(
        "/api/v1/wechat/publishes/00000000-0000-7000-8000-000000000abc:submit",
        headers=identity(role="publisher", user=PUBLISHER),
    )
    assert missing.status_code == 404
    assert transport.count("/cgi-bin/freepublish/submit") == 0

    intent = await authorize(client, draft["id"], "auth-key-1")
    assert intent.status_code == 201, intent.text
    publish = intent.json()
    assert publish["status"] == "INTENT"
    assert publish["state"] == "PENDING_SUBMIT"
    assert publish["submitAttempts"] == 0

    # Replay of the authorization is idempotent.
    replayed = await authorize(client, draft["id"], "auth-key-1")
    assert replayed.status_code == 200
    assert replayed.headers["Idempotency-Replayed"] == "true"
    assert replayed.json()["id"] == publish["id"]
    # One authorization per draft.
    second = await authorize(client, draft["id"], "auth-key-2")
    assert second.status_code == 409

    # The publisher executes the single submit attempt.
    transport.queue_submit(publish_id="PUBLISH-1")
    submitted = await client.post(
        f"/api/v1/wechat/publishes/{publish['id']}:submit",
        headers=identity(role="publisher", user=PUBLISHER),
    )
    assert submitted.status_code == 200, submitted.text
    settled = submitted.json()
    assert settled["status"] == "SUBMITTED"
    assert settled["publishId"] == "PUBLISH-1"
    assert settled["submitAttempts"] == 1
    assert transport.count("/cgi-bin/freepublish/submit") == 1
    # Replay never re-calls the official API: the submit queue is empty, so
    # any re-call would raise inside the fake transport.
    replay_submit = await client.post(
        f"/api/v1/wechat/publishes/{publish['id']}:submit",
        headers=identity(role="publisher", user=PUBLISHER),
    )
    assert replay_submit.status_code == 200
    assert replay_submit.json()["replayed"] is True
    assert transport.count("/cgi-bin/freepublish/submit") == 1

    # Reconciliation completes only with official evidence.
    transport.queue_get(
        {
            "publish_status": "publish",
            "article_id": "ART-1",
            "article_detail": {"count": 1, "item": [{"article_url": "https://mp.example/article"}]},
        }
    )
    polled = await client.post(
        f"/api/v1/wechat/publishes/{publish['id']}:poll", headers=identity(role="viewer")
    )
    assert polled.status_code == 200, polled.text
    final = polled.json()
    assert final["status"] == "PUBLISHED"
    assert final["state"] == "SUCCEEDED"
    assert final["articleUrl"] == "https://mp.example/article"
    assert final["pollCount"] == 1
    assert final["resolvedAt"] is not None
    # Polling a settled publish is a conflict.
    settled_poll = await client.post(
        f"/api/v1/wechat/publishes/{publish['id']}:poll", headers=identity(role="viewer")
    )
    assert settled_poll.status_code == 409


async def test_uncertain_submit_stays_reconciling_and_never_retries(api):
    client, app, transport = api
    account = await register_account(client)
    draft = (await create_draft(client, transport, account["id"], "pub-draft-2")).json()
    publish = (await authorize(client, draft["id"], "auth-key-u")).json()

    transport.queue_submit_error(WeChatTransportError("connection reset"))
    uncertain = await client.post(
        f"/api/v1/wechat/publishes/{publish['id']}:submit",
        headers=identity(role="publisher", user=PUBLISHER),
    )
    assert uncertain.status_code == 200, uncertain.text
    unknown = uncertain.json()
    assert unknown["status"] == "UNKNOWN"
    assert unknown["state"] == "RECONCILING"
    assert unknown["submitAttempts"] == 1
    assert unknown["publishId"] is None
    assert "never auto-retried" in unknown["detail"]

    # Replay returns the recorded state and does not re-submit: the submit
    # queue is empty, so any re-call would raise inside the fake transport.
    replay = await client.post(
        f"/api/v1/wechat/publishes/{publish['id']}:submit",
        headers=identity(role="publisher", user=PUBLISHER),
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "UNKNOWN"
    assert replay.json()["replayed"] is True
    assert transport.count("/cgi-bin/freepublish/submit") == 1

    # Reconciliation reads require publish.read: viewer is the least role.
    blocked = await client.post(
        f"/api/v1/wechat/publishes/{publish['id']}:poll", headers=identity(role="viewer")
    )
    assert blocked.status_code == 409
    assert "manual investigation" in blocked.text
    status = await client.get(
        f"/api/v1/wechat/publishes/{publish['id']}", headers=identity(role="viewer")
    )
    assert status.json()["status"] == "UNKNOWN"  # still blocked, not terminal

    # A confirmed submit stays non-terminal until the poll returns evidence.
    draft2 = (await create_draft(client, transport, account["id"], "pub-draft-3")).json()
    publish2 = (await authorize(client, draft2["id"], "auth-key-s")).json()
    transport.queue_submit(publish_id="PUBLISH-2")
    submitted2 = await client.post(
        f"/api/v1/wechat/publishes/{publish2['id']}:submit",
        headers=identity(role="publisher", user=PUBLISHER),
    )
    assert submitted2.json()["status"] == "SUBMITTED"
    assert submitted2.json()["state"] == "RECONCILING"

    transport.queue_get({"publish_status": "originality check"})
    pending = await client.post(
        f"/api/v1/wechat/publishes/{publish2['id']}:poll", headers=identity(role="viewer")
    )
    assert pending.status_code == 200
    assert pending.json()["status"] == "SUBMITTED"  # still reconciling, not terminal

    transport.queue_get(
        {
            "publish_status": "publish",
            "article_detail": {"count": 1, "item": [{"article_url": "https://mp.example/ok"}]},
        }
    )
    done = await client.post(
        f"/api/v1/wechat/publishes/{publish2['id']}:poll", headers=identity(role="viewer")
    )
    assert done.status_code == 200
    assert done.json()["status"] == "PUBLISHED"
    assert done.json()["pollCount"] == 2


# ------------------------------------------------------ tenant isolation


async def test_tenant_isolation_returns_404_for_foreign_resources(api):
    client, app, transport = api
    account = await register_account(client)
    draft = (await create_draft(client, transport, account["id"], "iso-draft-1")).json()
    publish = (await authorize(client, draft["id"], "iso-auth-1")).json()

    # Foreign reads use the least privileged read role; the submit uses the
    # publisher role so the 404 proves ownership failed, not authorization.
    foreign_viewer = identity(tenant=TENANT_B, user=FOREIGN_USER, role="viewer")
    foreign_publisher = identity(tenant=TENANT_B, user=FOREIGN_USER, role="publisher")
    assert (
        await client.get("/api/v1/wechat/accounts", headers=foreign_viewer)
    ).json()["count"] == 0
    assert (
        await client.get(f"/api/v1/wechat/accounts/{account['id']}", headers=foreign_viewer)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/wechat/drafts/{draft['id']}", headers=foreign_viewer)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/wechat/publishes/{publish['id']}", headers=foreign_viewer)
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/wechat/publishes/{publish['id']}:submit", headers=foreign_publisher
        )
    ).status_code == 404
    # No foreign traffic reached the official API through tenant A's account.
    assert transport.count("/cgi-bin/freepublish") == 0

    # Tenant B can register its own account with the same appId (per-tenant unique).
    own = await register_account(client, tenant=TENANT_B, role="content_editor")
    assert own["appId"] == "wx1234567890abcdef"


async def test_audit_trail_covers_the_full_lifecycle_without_secrets(api):
    client, app, transport = api
    account = await register_account(client)
    draft = (await create_draft(client, transport, account["id"], "audit-draft-1")).json()
    publish = (await authorize(client, draft["id"], "audit-auth-1")).json()
    transport.queue_submit(publish_id="PUBLISH-A")
    await client.post(
        f"/api/v1/wechat/publishes/{publish['id']}:submit",
        headers=identity(role="publisher", user=PUBLISHER),
    )
    transport.queue_get(
        {
            "publish_status": "publish",
            "article_detail": {"count": 1, "item": [{"article_url": "https://mp.example/f"}]},
        }
    )
    await client.post(
        f"/api/v1/wechat/publishes/{publish['id']}:poll", headers=identity(role="viewer")
    )

    events = await audit_actions(app)
    actions = {event["action"] for event in events}
    assert {
        "wechat.account.registered",
        "wechat.draft.created",
        "wechat.publish.authorized",
        "wechat.publish.submitted",
        "wechat.publish.settled",
        "wechat.publish.reconciled",
    } <= actions
    blob = json.dumps(events)
    assert SECRET_A not in blob
    assert "TOKEN-A" not in blob  # access tokens never leak into audit records


# ------------------------------------------------------------- migrations


def test_wechat_publisher_migration_round_trip(tmp_path) -> None:
    """0019 chains onto 0018, creates the three tables, and downgrades cleanly."""
    database_path = tmp_path / "wechat-publisher.db"
    config = migration_config(database_path)
    command.upgrade(config, WECHAT_PARENT)
    with sqlite3.connect(database_path) as connection:
        assert not {"wechat_account", "wechat_draft", "wechat_publish"} & tables(connection)

    command.upgrade(config, WECHAT_REVISION)
    with sqlite3.connect(database_path) as connection:
        assert {"wechat_account", "wechat_draft", "wechat_publish"} <= tables(connection)
        assert {
            "id",
            "tenant_id",
            "app_id",
            "display_label",
            "secret_ciphertext",
            "secret_fingerprint",
            "secret_key_id",
            "status",
            "created_by",
            "created_at",
            "updated_at",
            "revoked_at",
        } == table_columns(connection, "wechat_account")
        assert {
            "id",
            "tenant_id",
            "account_id",
            "idempotency_key",
            "request_sha256",
            "article",
            "article_sha256",
            "status",
            "media_id",
            "created_by",
            "error_code",
            "detail",
            "created_at",
            "updated_at",
        } == table_columns(connection, "wechat_draft")
        assert {
            "id",
            "tenant_id",
            "draft_id",
            "account_id",
            "idempotency_key",
            "request_sha256",
            "parameter_hash",
            "authorized_by",
            "submitted_by",
            "status",
            "publish_id",
            "article_url",
            "submit_attempts",
            "poll_count",
            "error_code",
            "detail",
            "submitted_at",
            "resolved_at",
            "created_at",
            "updated_at",
        } == table_columns(connection, "wechat_publish")
        publish_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='wechat_publish'"
        ).fetchone()[0]
        account_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='wechat_account'"
        ).fetchone()[0]
        # The controlled-commit semantics are enforced by the database itself.
        assert "ck_wechat_publish_one_attempt" in publish_schema  # one submit attempt
        assert "uq_wechat_publish_draft" in publish_schema  # one authorization per draft
        assert "ck_wechat_publish_status" in publish_schema
        assert "uq_wechat_account_tenant_app" in account_schema
        assert "ck_wechat_account_status" in account_schema

    command.downgrade(config, WECHAT_PARENT)
    with sqlite3.connect(database_path) as connection:
        assert not {"wechat_account", "wechat_draft", "wechat_publish"} & tables(connection)


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite+aiosqlite:///:memory:",
        "postgresql+asyncpg://cloudctl:cloudctl@localhost:5432/cloudctl",
    ],
    ids=["sqlite", "postgres"],
)
def test_wechat_publisher_migration_renders_offline_sql_for_both_dialects(
    database_url: str,
) -> None:
    """Offline rendering never connects; it proves the step is valid SQL on both dialects."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url)
    upgrade_sql = io.StringIO()
    with contextlib.redirect_stdout(upgrade_sql):
        command.upgrade(config, f"{WECHAT_PARENT}:{WECHAT_REVISION}", sql=True)
    rendered = upgrade_sql.getvalue()
    assert "create_all" not in rendered  # declarative op.* only, never metadata.create_all
    for needle in (
        "CREATE TABLE wechat_account",
        "CREATE TABLE wechat_draft",
        "CREATE TABLE wechat_publish",
        "CREATE INDEX",
        "uq_wechat_account_tenant_app",
        "uq_wechat_draft_idempotency",
        "uq_wechat_publish_idempotency",
        "uq_wechat_publish_draft",
        "ck_wechat_account_status",
        "ck_wechat_draft_status",
        "ck_wechat_publish_status",
        "ck_wechat_publish_one_attempt",
    ):
        assert needle in rendered, needle

    downgrade_sql = io.StringIO()
    with contextlib.redirect_stdout(downgrade_sql):
        command.downgrade(config, f"{WECHAT_REVISION}:{WECHAT_PARENT}", sql=True)
    dropped = downgrade_sql.getvalue()
    for table in ("wechat_publish", "wechat_draft", "wechat_account"):
        assert f"DROP TABLE {table}" in dropped


async def test_rate_limited_submit_fails_once_with_official_errcode(api):
    """F16 delta: an official rate-limit answer (45009) is a terminal FAILED
    with the errcode preserved — never retried, never UNKNOWN (an HTTP-level
    timeout stays UNKNOWN; an API-level refusal is evidence)."""
    client, app, transport = api
    account = await register_account(client)
    draft = (await create_draft(client, transport, account["id"], "rl-draft-1")).json()
    intent = await authorize(client, draft["id"], "rl-auth-1")
    publish = intent.json()

    transport.queue_submit_error(WeChatApiError(45009, "api daily quota exceeded"))
    submitted = await client.post(
        f"/api/v1/wechat/publishes/{publish['id']}:submit",
        headers=identity(role="publisher", user=PUBLISHER),
    )
    assert submitted.status_code == 200, submitted.text
    settled = submitted.json()
    assert settled["status"] == "FAILED"
    assert settled["state"] == "FAILED"
    assert settled["errorCode"] == "WECHAT_45009"
    assert "quota exceeded" in settled["detail"]
    assert settled["submitAttempts"] == 1
    assert transport.count("/cgi-bin/freepublish/submit") == 1

    # The single attempt is spent: replay reports the same terminal view
    # without another official call.
    replay = await client.post(
        f"/api/v1/wechat/publishes/{publish['id']}:submit",
        headers=identity(role="publisher", user=PUBLISHER),
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["status"] == "FAILED"
    assert transport.count("/cgi-bin/freepublish/submit") == 1

    # FAILED is terminal: reconciliation refuses it.
    poll = await client.post(
        f"/api/v1/wechat/publishes/{publish['id']}:poll", headers=identity(role="viewer")
    )
    assert poll.status_code == 409
