"""WeChat Official Account API client with an injectable transport.

Every outbound HTTP interaction goes through :class:`WeChatTransport`, so
integration tests inject a fake and never touch the real network. Error
taxonomy mirrors the controlled-commit semantics of the mobile action ledger:

* :class:`WeChatApiError` — the official API answered with a definitive
  ``errcode``. The side effect is known (it did not happen, or it was
  rejected), so the caller may record a terminal failure.
* :class:`WeChatTransportError` — timeout / network / 5xx / unparsable body.
  The side effect on WeChat is *indeterminate*; callers must keep the ledger
  entry non-terminal (UNKNOWN) and reconcile by polling instead of retrying.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

from .settings import Settings

_TOKEN_ENDPOINT = "/cgi-bin/token"  # noqa: S105 - API path, not a token value.
_DRAFT_ADD_ENDPOINT = "/cgi-bin/draft/add"
_FREEPUBLISH_SUBMIT_ENDPOINT = "/cgi-bin/freepublish/submit"
_FREEPUBLISH_GET_ENDPOINT = "/cgi-bin/freepublish/get"


class WeChatTransportError(Exception):
    """Outbound call failed in a way that leaves the side effect indeterminate."""


class WeChatApiError(Exception):
    """The official API returned a definitive non-zero ``errcode``."""

    def __init__(self, errcode: int, errmsg: str) -> None:
        super().__init__(f"wechat official api rejected the call: {errcode} {errmsg}")
        self.errcode = errcode
        self.errmsg = errmsg


class WeChatTransport(Protocol):
    """Minimal HTTP boundary; production uses httpx, tests use a fake."""

    async def post_json(self, url: str, *, json: dict[str, Any]) -> tuple[int, dict[str, Any]]: ...

    async def get_json(self, url: str, *, params: dict[str, str]) -> tuple[int, dict[str, Any]]: ...


class HttpxWeChatTransport:
    """Default transport. Owns a lazily created httpx client."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._settings.wechat_http_timeout_seconds,
                follow_redirects=False,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def post_json(self, url: str, *, json: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            response = await self._http().post(url, json=json)
        except httpx.HTTPError as exc:
            raise WeChatTransportError("wechat request failed at the transport layer") from exc
        return response.status_code, _decode(response)

    async def get_json(self, url: str, *, params: dict[str, str]) -> tuple[int, dict[str, Any]]:
        try:
            response = await self._http().get(url, params=params)
        except httpx.HTTPError as exc:
            raise WeChatTransportError("wechat request failed at the transport layer") from exc
        return response.status_code, _decode(response)


def _decode(response: httpx.Response) -> dict[str, Any]:
    if len(response.content) > 1_048_576:
        raise WeChatTransportError("wechat response exceeds the size budget")
    try:
        body = response.json()
    except ValueError as exc:
        raise WeChatTransportError("wechat response was not valid JSON") from exc
    if not isinstance(body, dict):
        raise WeChatTransportError("wechat response was not a JSON object")
    return body


@dataclass(frozen=True, slots=True)
class WeChatAccessToken:
    value: str
    expires_at_monotonic: float
    expires_in: int


class WeChatOfficialClient:
    """Typed wrapper over the endpoints used by the V1 publisher slice."""

    def __init__(self, transport: WeChatTransport, settings: Settings) -> None:
        self._transport = transport
        self._base = settings.wechat_api_base_url.rstrip("/")

    async def _call(self, coroutine: Awaitable[tuple[int, dict[str, Any]]]) -> dict[str, Any]:
        status, body = await coroutine
        if status >= 500:
            raise WeChatTransportError(f"wechat endpoint answered HTTP {status}")
        errcode = body.get("errcode")
        if isinstance(errcode, int) and errcode != 0:
            errmsg = body.get("errmsg")
            raise WeChatApiError(errcode, errmsg if isinstance(errmsg, str) else "")
        if not 200 <= status < 300:
            raise WeChatTransportError(f"wechat endpoint answered HTTP {status}")
        return body

    async def _post(
        self, endpoint: str, access_token: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        query = urlencode({"access_token": access_token})
        return await self._call(
            self._transport.post_json(f"{self._base}{endpoint}?{query}", json=payload)
        )

    async def fetch_token(self, app_id: str, app_secret: str) -> WeChatAccessToken:
        body = await self._call(
            self._transport.get_json(
                f"{self._base}{_TOKEN_ENDPOINT}",
                params={
                    "grant_type": "client_credential",
                    "appid": app_id,
                    "secret": app_secret,
                },
            )
        )
        token = body.get("access_token")
        expires_in = body.get("expires_in")
        if (
            not isinstance(token, str)
            or not token
            or not isinstance(expires_in, int)
            or isinstance(expires_in, bool)
            or expires_in <= 0
        ):
            raise WeChatTransportError("wechat token response was malformed")
        return WeChatAccessToken(
            value=token,
            expires_at_monotonic=time.monotonic() + float(expires_in),
            expires_in=expires_in,
        )

    async def add_draft(self, access_token: str, articles: list[dict[str, Any]]) -> str:
        official_articles = [
            {
                ("thumb_media_id" if key == "thumbMediaId" else key): value
                for key, value in article.items()
            }
            for article in articles
        ]
        body = await self._post(_DRAFT_ADD_ENDPOINT, access_token, {"articles": official_articles})
        media_id = body.get("media_id")
        if not isinstance(media_id, str) or not media_id:
            raise WeChatTransportError("wechat draft response was malformed")
        return media_id

    async def submit_publish(self, access_token: str, media_id: str) -> str:
        body = await self._post(_FREEPUBLISH_SUBMIT_ENDPOINT, access_token, {"media_id": media_id})
        publish_id = body.get("publish_id")
        if not isinstance(publish_id, str) or not publish_id:
            raise WeChatTransportError("wechat publish submit response was malformed")
        return publish_id

    async def get_publish(self, access_token: str, publish_id: str) -> dict[str, Any]:
        return await self._post(_FREEPUBLISH_GET_ENDPOINT, access_token, {"publish_id": publish_id})


class WeChatTokenManager:
    """Per (tenant, appId) single-flight access-token cache.

    Tenant isolation is structural: the cache key always includes the tenant,
    so one tenant's credential can never be replayed for another. A per-key
    ``asyncio.Lock`` guarantees that concurrent callers trigger exactly one
    upstream token fetch while a valid token is cached. Token and secret
    values are never logged.
    """

    def __init__(self, client: WeChatOfficialClient, *, margin_seconds: float) -> None:
        self._client = client
        self._margin = margin_seconds
        self._cache: dict[tuple[str, str], WeChatAccessToken] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    def _lock(self, key: tuple[str, str]) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def get_token(self, tenant_id: str, app_id: str, app_secret: str) -> str:
        key = (tenant_id, app_id)
        async with self._lock(key):
            cached = self._cache.get(key)
            if cached is not None and time.monotonic() + self._margin < cached.expires_at_monotonic:
                return cached.value
            token = await self._client.fetch_token(app_id, app_secret)
            self._cache[key] = token
            return token.value

    def invalidate(self, tenant_id: str, app_id: str) -> None:
        self._cache.pop((tenant_id, app_id), None)
