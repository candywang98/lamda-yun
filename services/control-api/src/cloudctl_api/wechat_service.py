"""WeChat Official Account publisher service (V1-26 starter slice).

Server-side equivalent of the mobile controlled-commit ledger
(`commit_intent -> commit_once -> reconcile`, AGENTS.md rule 4):

* **One authorization.** ``authorize_publish`` freezes the draft (media id +
  article hash), the account, and the operator note into an INTENT row.
  Only roles holding ``publish.approve`` may authorize.
* **One attempt.** ``submit`` consumes ``submit_attempts`` (CHECK-constrained
  to ``<= 1``) before calling ``freepublish/submit`` exactly once. Replays
  return the recorded state and never re-call the official API. There is no
  automatic retry of a publish under any circumstance.
* **Uncertain stays blocked.** If the single submit attempt ends in a
  transport-level failure the row becomes ``UNKNOWN``/``RECONCILING``.
  ``poll`` reconciles via ``freepublish/get`` and only then moves the row to
  a terminal ``PUBLISHED``/``FAILED`` state with evidence (article URL or
  official error code).
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from cloudctl_domain import (
    Actor,
    ConflictError,
    NotFoundError,
    Permission,
    ValidationError,
    canonical_hash,
    require_permissions,
)
from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .db import (
    AuditEventRow,
    Database,
    WechatAccountRow,
    WechatDraftRow,
    WechatPublishRow,
)
from .settings import Settings
from .wechat_client import (
    HttpxWeChatTransport,
    WeChatApiError,
    WeChatOfficialClient,
    WeChatTokenManager,
    WeChatTransport,
    WeChatTransportError,
)
from .wechat_schemas import (
    WechatAccountCreate,
    WechatDraftCreate,
    WechatPublishAuthorize,
)

_ENCRYPTED_PREFIX = "v1:"
_DEVELOPMENT_PREFIX = "dev-b64:"

_PUBLISH_STATES = {
    "INTENT": "PENDING_SUBMIT",
    "SUBMITTING": "SUBMITTING",
    "SUBMITTED": "RECONCILING",
    "UNKNOWN": "RECONCILING",
    "PUBLISHED": "SUCCEEDED",
    "FAILED": "FAILED",
}


def _now() -> datetime:
    return datetime.now(UTC)


class WeChatSecretCipher:
    """Fernet-at-rest envelope for appSecret material.

    Production must configure ``wechat_secret_encryption_key``; without it the
    service refuses to persist secrets. Development/test without a key may use
    a clearly-marked base64 envelope so the slice stays runnable, but the key
    id advertises the weaker mode and audit records surface it.
    """

    def __init__(self, key: SecretStr | None) -> None:
        raw = key.get_secret_value().strip() if key is not None else ""
        self._fernet: Fernet | None = None
        if raw:
            self._fernet = Fernet(raw.encode())
            self.key_id = f"fernet-{hashlib.sha256(raw.encode()).hexdigest()[:12]}"
        else:
            self.key_id = "development-unencrypted"

    @property
    def encrypted(self) -> bool:
        return self._fernet is not None

    def encrypt(self, secret: str) -> str:
        if self._fernet is not None:
            return _ENCRYPTED_PREFIX + self._fernet.encrypt(secret.encode()).decode()
        return _DEVELOPMENT_PREFIX + base64.b64encode(secret.encode()).decode()

    def decrypt(self, stored: str) -> str:
        if stored.startswith(_ENCRYPTED_PREFIX):
            if self._fernet is None:
                raise ConflictError("WECHAT_SECRET_ENCRYPTION_KEY is not configured")
            try:
                return self._fernet.decrypt(stored[len(_ENCRYPTED_PREFIX) :].encode()).decode()
            except InvalidToken as exc:
                raise ConflictError("stored appSecret cannot be decrypted") from exc
        if stored.startswith(_DEVELOPMENT_PREFIX):
            return base64.b64decode(stored[len(_DEVELOPMENT_PREFIX) :]).decode()
        raise ConflictError("stored appSecret envelope is unrecognized")


def account_view(row: WechatAccountRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "appId": row.app_id,
        "displayLabel": row.display_label,
        "status": row.status,
        "secretFingerprint": row.secret_fingerprint[:12],
        "secretEncrypted": row.secret_key_id != "development-unencrypted",
        "secretKeyId": row.secret_key_id,
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }


def draft_view(row: WechatDraftRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "accountId": row.account_id,
        "status": row.status,
        "article": row.article,
        "articleSha256": row.article_sha256,
        "mediaId": row.media_id,
        "errorCode": row.error_code,
        "detail": row.detail,
        "createdBy": row.created_by,
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }


def publish_view(row: WechatPublishRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "draftId": row.draft_id,
        "accountId": row.account_id,
        "status": row.status,
        "state": _PUBLISH_STATES.get(row.status, "UNKNOWN"),
        "publishId": row.publish_id,
        "articleUrl": row.article_url,
        "submitAttempts": row.submit_attempts,
        "pollCount": row.poll_count,
        "errorCode": row.error_code,
        "detail": row.detail,
        "authorizedBy": row.authorized_by,
        "submittedBy": row.submitted_by,
        "submittedAt": row.submitted_at,
        "resolvedAt": row.resolved_at,
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }


def _audit(
    session: Any,
    actor: Actor,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    result: str,
    metadata: dict[str, Any],
) -> None:
    session.add(
        AuditEventRow(
            id=str(uuid.uuid4()),
            tenant_id=str(actor.tenant_id),
            actor_type="user",
            actor_id=str(actor.user_id),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=actor.request_id,
            result=result,
            metadata_json=metadata,
            occurred_at=_now(),
        )
    )


def _publish_parameter_hash(
    draft: WechatDraftRow, account: WechatAccountRow, idempotency_key: str
) -> str:
    material = (
        f"cloudctl.wechat-publish/v1\n{draft.id}\n{account.id}\n"
        f"{draft.media_id or ''}\n{draft.article_sha256}\n{idempotency_key}"
    )
    return hashlib.sha256(material.encode()).hexdigest()


class WeChatPublisherService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        *,
        transport: WeChatTransport | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self._transport = transport if transport is not None else HttpxWeChatTransport(settings)
        self.client = WeChatOfficialClient(self._transport, settings)
        self.tokens = WeChatTokenManager(
            self.client, margin_seconds=float(settings.wechat_token_expiry_margin_seconds)
        )
        self.cipher = WeChatSecretCipher(settings.wechat_secret_encryption_key)

    async def close_transport(self) -> None:
        closer = getattr(self._transport, "close", None)
        if closer is not None:
            await closer()

    # ------------------------------------------------------------ accounts

    async def register_account(self, actor: Actor, body: WechatAccountCreate) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        secret = body.app_secret.get_secret_value()
        if not secret or len(secret) < 16:
            raise ValidationError("appSecret must be at least 16 characters")
        fingerprint = hashlib.sha256(secret.encode()).hexdigest()
        now = _now()
        try:
            async with self.database.unit_of_work() as session:
                existing = await session.scalar(
                    select(WechatAccountRow).where(
                        WechatAccountRow.tenant_id == str(actor.tenant_id),
                        WechatAccountRow.app_id == body.app_id,
                    )
                )
                if existing is not None:
                    raise ConflictError("app is already registered for this tenant")
                row = WechatAccountRow(
                    id=str(uuid.uuid4()),
                    tenant_id=str(actor.tenant_id),
                    app_id=body.app_id,
                    display_label=body.display_label,
                    secret_ciphertext=self.cipher.encrypt(secret),
                    secret_fingerprint=fingerprint,
                    secret_key_id=self.cipher.key_id,
                    status="ACTIVE",
                    created_by=str(actor.user_id),
                    updated_at=now,
                    revoked_at=None,
                    created_at=now,
                )
                session.add(row)
                await session.flush()
                _audit(
                    session,
                    actor,
                    action="wechat.account.registered",
                    resource_type="wechat_account",
                    resource_id=row.id,
                    result="SUCCESS",
                    metadata={
                        "appId": row.app_id,
                        "secretFingerprint": fingerprint[:12],
                        "secretEncryptedAtRest": self.cipher.encrypted,
                    },
                )
                return account_view(row)
        except IntegrityError as exc:
            raise ConflictError("app is already registered for this tenant") from exc

    async def list_accounts(self, actor: Actor) -> list[dict[str, Any]]:
        require_permissions(actor.roles, Permission.PUBLISH_READ)
        async with self.database.unit_of_work() as session:
            rows = (
                await session.scalars(
                    select(WechatAccountRow)
                    .where(WechatAccountRow.tenant_id == str(actor.tenant_id))
                    .order_by(WechatAccountRow.created_at.desc())
                    .limit(200)
                )
            ).all()
            return [account_view(row) for row in rows]

    async def _owned_account(
        self, session: Any, actor: Actor, account_id: str
    ) -> WechatAccountRow:
        row = await session.get(WechatAccountRow, account_id)
        if row is None or row.tenant_id != str(actor.tenant_id):
            raise NotFoundError("wechat account was not found")
        return row

    async def get_account(self, actor: Actor, account_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.PUBLISH_READ)
        async with self.database.unit_of_work() as session:
            return account_view(await self._owned_account(session, actor, account_id))

    # -------------------------------------------------------------- drafts

    async def create_draft(
        self, actor: Actor, idempotency_key: str, body: WechatDraftCreate
    ) -> tuple[dict[str, Any], bool]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        if not idempotency_key or len(idempotency_key) > 128:
            raise ValidationError("a valid Idempotency-Key header is required")
        document = body.model_dump(mode="json", by_alias=True, exclude_none=True)
        request_sha256 = canonical_hash(document)
        article = {
            "title": body.title,
            "content": body.content_html,
            "digest": body.digest or "",
            "author": body.author or "",
            "thumbMediaId": body.thumb_media_id or "",
        }
        article_sha256 = canonical_hash(article)
        now = _now()
        account_id = ""
        draft_id = ""
        try:
            async with self.database.unit_of_work() as session:
                existing = await session.scalar(
                    select(WechatDraftRow).where(
                        WechatDraftRow.tenant_id == str(actor.tenant_id),
                        WechatDraftRow.idempotency_key == idempotency_key,
                    )
                )
                if existing is not None:
                    if existing.request_sha256 != request_sha256:
                        raise ConflictError(
                            "Idempotency-Key was reused with different draft content"
                        )
                    return draft_view(existing), False
                account = await self._owned_account(session, actor, body.account_id)
                if account.status != "ACTIVE":
                    raise ConflictError("wechat account is not active")
                draft_id = str(uuid.uuid4())
                account_id = account.id
                session.add(
                    WechatDraftRow(
                        id=draft_id,
                        tenant_id=str(actor.tenant_id),
                        account_id=account.id,
                        idempotency_key=idempotency_key,
                        request_sha256=request_sha256,
                        article=article,
                        article_sha256=article_sha256,
                        status="PENDING",
                        media_id=None,
                        created_by=str(actor.user_id),
                        error_code=None,
                        detail=None,
                        updated_at=now,
                        created_at=now,
                    )
                )
        except IntegrityError as exc:
            raise ConflictError("wechat draft idempotency conflict") from exc

        media_id = await self._push_draft(actor, account_id, draft_id, article)
        async with self.database.unit_of_work() as session:
            stored = await session.get(WechatDraftRow, draft_id, with_for_update=True)
            if media_id is None:
                stored.status = "UNKNOWN"
                stored.detail = "draft/add outcome is indeterminate; replay does not re-call"
            else:
                stored.status = "READY"
                stored.media_id = media_id
            stored.updated_at = _now()
            _audit(
                session,
                actor,
                action="wechat.draft.created",
                resource_type="wechat_draft",
                resource_id=draft_id,
                result="SUCCESS" if media_id is not None else "UNKNOWN",
                metadata={
                    "accountId": account_id,
                    "articleSha256": article_sha256,
                    "mediaId": media_id,
                },
            )
            return draft_view(stored), True

    async def _push_draft(
        self, actor: Actor, account_id: str, draft_id: str, article: dict[str, Any]
    ) -> str | None:
        """Call draft/add once. Returns media_id, or None when indeterminate."""
        try:
            token = await self._token_for(actor.tenant_id, account_id)
            return await self.client.add_draft(token, [article])
        except WeChatApiError as exc:
            async with self.database.unit_of_work() as session:
                row = await session.get(WechatDraftRow, draft_id, with_for_update=True)
                row.status = "FAILED"
                row.error_code = f"WECHAT_{exc.errcode}"
                row.detail = f"official draft/add rejected: {exc.errmsg}"
                row.updated_at = _now()
                _audit(
                    session,
                    actor,
                    action="wechat.draft.failed",
                    resource_type="wechat_draft",
                    resource_id=draft_id,
                    result="FAILURE",
                    metadata={"errcode": exc.errcode, "accountId": account_id},
                )
            raise ConflictError(f"draft was rejected by the official API ({exc.errcode})") from exc
        except WeChatTransportError:
            return None

    async def _token_for(self, tenant_id: Any, account_id: str) -> str:
        async with self.database.unit_of_work() as session:
            account = await session.get(WechatAccountRow, account_id)
            if account is None or account.tenant_id != str(tenant_id):
                raise NotFoundError("wechat account was not found")
            if account.status != "ACTIVE":
                raise ConflictError("wechat account is not active")
            app_id = account.app_id
            app_secret = self.cipher.decrypt(account.secret_ciphertext)
        return await self.tokens.get_token(str(tenant_id), app_id, app_secret)

    async def get_draft(self, actor: Actor, draft_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.PUBLISH_READ)
        async with self.database.unit_of_work() as session:
            row = await session.get(WechatDraftRow, draft_id)
            if row is None or row.tenant_id != str(actor.tenant_id):
                raise NotFoundError("wechat draft was not found")
            return draft_view(row)

    # ------------------------------------------------ publish ledger (G3)

    async def authorize_publish(
        self, actor: Actor, draft_id: str, idempotency_key: str, body: WechatPublishAuthorize
    ) -> tuple[dict[str, Any], bool]:
        """The single authorization gate: PUBLISH_APPROVE holders freeze intent."""
        require_permissions(actor.roles, Permission.PUBLISH_APPROVE)
        if not idempotency_key or len(idempotency_key) > 128:
            raise ValidationError("a valid Idempotency-Key header is required")
        request_sha256 = canonical_hash(
            {"draftId": draft_id, "note": body.authorization_note or ""}
        )
        now = _now()
        try:
            async with self.database.unit_of_work() as session:
                existing = await session.scalar(
                    select(WechatPublishRow).where(
                        WechatPublishRow.tenant_id == str(actor.tenant_id),
                        WechatPublishRow.idempotency_key == idempotency_key,
                    )
                )
                if existing is not None:
                    if existing.request_sha256 != request_sha256:
                        raise ConflictError(
                            "Idempotency-Key was reused with a different authorization"
                        )
                    return publish_view(existing), False
                draft = await session.get(WechatDraftRow, draft_id, with_for_update=True)
                if draft is None or draft.tenant_id != str(actor.tenant_id):
                    raise NotFoundError("wechat draft was not found")
                if draft.status != "READY" or not draft.media_id:
                    raise ConflictError("only a READY draft with a media id can be published")
                per_draft = await session.scalar(
                    select(WechatPublishRow).where(WechatPublishRow.draft_id == draft.id)
                )
                if per_draft is not None:
                    raise ConflictError("this draft already has a publish authorization")
                account = await session.get(WechatAccountRow, draft.account_id)
                if account is None or account.tenant_id != str(actor.tenant_id):
                    raise NotFoundError("wechat account was not found")
                if account.status != "ACTIVE":
                    raise ConflictError("wechat account is not active")
                row = WechatPublishRow(
                    id=str(uuid.uuid4()),
                    tenant_id=str(actor.tenant_id),
                    draft_id=draft.id,
                    account_id=account.id,
                    idempotency_key=idempotency_key,
                    request_sha256=request_sha256,
                    parameter_hash=_publish_parameter_hash(draft, account, idempotency_key),
                    authorized_by=str(actor.user_id),
                    submitted_by=None,
                    status="INTENT",
                    publish_id=None,
                    article_url=None,
                    submit_attempts=0,
                    poll_count=0,
                    error_code=None,
                    detail=body.authorization_note or None,
                    submitted_at=None,
                    resolved_at=None,
                    updated_at=now,
                    created_at=now,
                )
                session.add(row)
                await session.flush()
                _audit(
                    session,
                    actor,
                    action="wechat.publish.authorized",
                    resource_type="wechat_publish",
                    resource_id=row.id,
                    result="SUCCESS",
                    metadata={
                        "draftId": draft.id,
                        "accountId": account.id,
                        "mediaId": draft.media_id,
                        "parameterHash": row.parameter_hash,
                    },
                )
                return publish_view(row), True
        except IntegrityError as exc:
            raise ConflictError("wechat publish authorization conflict") from exc

    async def _owned_publish(
        self, session: Any, actor: Actor, publish_id: str, *, for_update: bool = False
    ) -> WechatPublishRow:
        row = await session.get(WechatPublishRow, publish_id, with_for_update=for_update)
        if row is None or row.tenant_id != str(actor.tenant_id):
            raise NotFoundError("wechat publish was not found")
        return row

    async def submit(self, actor: Actor, publish_id: str) -> dict[str, Any]:
        """Execute the authorized publish exactly once; never re-submit."""
        require_permissions(actor.roles, Permission.PUBLISH_CREATE)
        async with self.database.unit_of_work() as session:
            row = await self._owned_publish(session, actor, publish_id, for_update=True)
            if row.submit_attempts >= 1:
                # Replay: the single attempt is already spent. Never re-call.
                view = publish_view(row)
                view["replayed"] = True
                return view
            if row.status != "INTENT":
                raise ConflictError("publish is not awaiting its single submit attempt")
            draft = await session.get(WechatDraftRow, row.draft_id)
            if draft is None or draft.tenant_id != str(actor.tenant_id):
                raise NotFoundError("wechat draft was not found")
            if draft.status != "READY" or not draft.media_id:
                raise ConflictError("the frozen draft is no longer publishable")
            account_id = row.account_id
            media_id = draft.media_id

        # Token acquisition happens before the attempt is consumed: a token
        # outage leaves the intent intact because nothing was submitted yet.
        try:
            token = await self._token_for(actor.tenant_id, account_id)
        except WeChatTransportError as exc:
            raise ConflictError("WECHAT_TOKEN_UNAVAILABLE") from exc
        except WeChatApiError as exc:
            async with self.database.unit_of_work() as session:
                failed = await self._owned_publish(session, actor, publish_id, for_update=True)
                failed.status = "FAILED"
                failed.error_code = f"WECHAT_{exc.errcode}"
                failed.detail = f"access token was rejected: {exc.errmsg}"
                failed.resolved_at = _now()
                failed.updated_at = _now()
                _audit(
                    session,
                    actor,
                    action="wechat.publish.failed",
                    resource_type="wechat_publish",
                    resource_id=publish_id,
                    result="FAILURE",
                    metadata={"stage": "token", "errcode": exc.errcode},
                )
                return publish_view(failed)

        async with self.database.unit_of_work() as session:
            # Re-check under the row lock so concurrent submits cannot both
            # consume the single attempt.
            spending = await self._owned_publish(session, actor, publish_id, for_update=True)
            if spending.submit_attempts >= 1:
                view = publish_view(spending)
                view["replayed"] = True
                return view
            spending.submit_attempts = 1  # CHECK constraint caps this at one attempt
            spending.status = "SUBMITTING"
            spending.submitted_by = str(actor.user_id)
            spending.submitted_at = _now()
            spending.updated_at = _now()
            _audit(
                session,
                actor,
                action="wechat.publish.submitted",
                resource_type="wechat_publish",
                resource_id=publish_id,
                result="STARTED",
                metadata={"attempt": 1},
            )

        try:
            official_publish_id = await self.client.submit_publish(token, media_id)
            outcome = ("SUBMITTED", official_publish_id, None, None)
        except WeChatApiError as exc:
            outcome = ("FAILED", None, f"WECHAT_{exc.errcode}", exc.errmsg or "")
        except WeChatTransportError:
            outcome = (
                "UNKNOWN",
                None,
                None,
                "submit outcome indeterminate; awaiting reconciliation, never auto-retried",
            )

        async with self.database.unit_of_work() as session:
            final = await self._owned_publish(session, actor, publish_id, for_update=True)
            status, official_id, error_code, detail = outcome
            final.status = status
            final.publish_id = official_id or final.publish_id
            final.error_code = error_code
            if detail:
                final.detail = detail
            final.updated_at = _now()
            _audit(
                session,
                actor,
                action="wechat.publish.settled",
                resource_type="wechat_publish",
                resource_id=publish_id,
                result={"SUBMITTED": "SUCCESS", "UNKNOWN": "UNKNOWN", "FAILED": "FAILURE"}[status],
                metadata={"attempt": 1, "publishId": final.publish_id, "errcode": error_code},
            )
            return publish_view(final)

    async def poll(self, actor: Actor, publish_id: str) -> dict[str, Any]:
        """Reconcile via freepublish/get; only evidence makes a terminal state."""
        require_permissions(actor.roles, Permission.PUBLISH_READ)
        async with self.database.unit_of_work() as session:
            row = await self._owned_publish(session, actor, publish_id, for_update=True)
            if row.status not in ("SUBMITTED", "UNKNOWN"):
                raise ConflictError("publish is not awaiting reconciliation")
            if not row.publish_id:
                raise ConflictError(
                    "reconciliation requires an official publish id; manual investigation"
                )
            poll_target = row.publish_id
            account_id = row.account_id

        try:
            token = await self._token_for(actor.tenant_id, account_id)
            document = await self.client.get_publish(token, poll_target)
        except WeChatTransportError as exc:
            raise ConflictError("WECHAT_POLL_UNAVAILABLE") from exc
        except WeChatApiError as exc:
            async with self.database.unit_of_work() as session:
                stuck = await self._owned_publish(session, actor, publish_id, for_update=True)
                stuck.poll_count += 1
                stuck.updated_at = _now()
                _audit(
                    session,
                    actor,
                    action="wechat.publish.reconciled",
                    resource_type="wechat_publish",
                    resource_id=publish_id,
                    result="UNKNOWN",
                    metadata={"errcode": exc.errcode, "poll": stuck.poll_count},
                )
            raise ConflictError(
                f"freepublish/get failed ({exc.errcode}); still reconciling"
            ) from exc

        publish_status = document.get("publish_status")
        article_url = None
        detail_items = document.get("article_detail")
        if isinstance(detail_items, dict):
            items = detail_items.get("item")
            if isinstance(items, list) and items and isinstance(items[0], dict):
                url = items[0].get("article_url")
                if isinstance(url, str):
                    article_url = url

        async with self.database.unit_of_work() as session:
            final = await self._owned_publish(session, actor, publish_id, for_update=True)
            final.poll_count += 1
            final.updated_at = _now()
            if publish_status == "publish" and article_url:
                final.status = "PUBLISHED"
                final.article_url = article_url
                final.resolved_at = _now()
                result = "SUCCESS"
            elif publish_status == "fail":
                final.status = "FAILED"
                fail = document.get("fail_info")
                final.error_code = "WECHAT_PUBLISH_REJECTED"
                final.detail = canonical_hash(fail) if fail else "official API reported failure"
                final.resolved_at = _now()
                result = "FAILURE"
            else:
                result = "PENDING"
            _audit(
                session,
                actor,
                action="wechat.publish.reconciled",
                resource_type="wechat_publish",
                resource_id=publish_id,
                result=result,
                metadata={
                    "publishId": poll_target,
                    "publishStatus": publish_status,
                    "poll": final.poll_count,
                },
            )
            return publish_view(final)

    async def get_publish(self, actor: Actor, publish_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.PUBLISH_READ)
        async with self.database.unit_of_work() as session:
            return publish_view(await self._owned_publish(session, actor, publish_id))
