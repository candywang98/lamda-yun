"""Application-owned OIDC verification and request-scoped RBAC actors."""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import jwt
from cloudctl_domain import Actor, AuthenticationError, ForbiddenError, Role
from fastapi import Depends, Request
from jwt import PyJWTError
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from .db import UserRow
from .settings import Settings, get_settings

# ---------------------------------------------------------------------------
# Identity "D path" (scope-decisions D-6/D-10, A14)
# ---------------------------------------------------------------------------
# Production trusts exactly one nginx-overwritten identity header and maps it
# to a provisioned user row; everything a client could self-report about its
# identity is rejected outright in production. The nginx layer terminates
# HTTP BasicAuth (or, later, Authelia/Dex OIDC) on the edge and overwrites
# ``X-CloudCtl-Principal``; uvicorn stays loopback-only. The OIDC bearer path
# remains available and unchanged — the principal header is an additional
# production mode, not a replacement (D-10 rollout order: server-side mapping
# first, OIDC federation once the mapping path runs stable).

PRINCIPAL_HEADER = "X-CloudCtl-Principal"
PRINCIPAL_ISSUER = "cloudctl-principal-nginx"
SELF_REPORTED_IDENTITY_HEADERS = ("X-Tenant-Id", "X-User-Id", "X-Roles", "X-MFA")


class OidcClaims(BaseModel):
    sub: str = Field(min_length=1, max_length=255)
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    roles: list[Role] = Field(default_factory=list, max_length=20)
    mfa: bool = False
    iss: str
    aud: str | list[str]
    exp: int
    nbf: int | None = None


class OidcJwtVerifier:
    """Verify access tokens without trusting proxy-populated ASGI scope data."""

    _MAX_TOKEN_BYTES = 16_384
    _MAX_JWKS_BYTES = 1_048_576
    _MAX_JWKS_KEYS = 100

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client
        self._owns_http_client = http_client is None
        self._static_key = self._load_static_key(settings)
        self._jwks: list[dict[str, Any]] | None = None
        self._jwks_expires_at = 0.0
        self._jwks_lock = asyncio.Lock()

    @staticmethod
    def _load_static_key(settings: Settings) -> bytes | str | None:
        if settings.oidc_public_key_pem is not None:
            encoded = settings.oidc_public_key_pem.encode("utf-8")
            if len(encoded) > 65_536:
                raise ValueError("OIDC public key PEM exceeds 64 KiB")
            return settings.oidc_public_key_pem
        if settings.oidc_public_key_path is None:
            return None
        path = Path(settings.oidc_public_key_path)
        try:
            encoded = path.read_bytes()
        except OSError as exc:
            raise ValueError(f"unable to read OIDC public key path: {path}") from exc
        if not encoded or len(encoded) > 65_536:
            raise ValueError("OIDC public key file must contain at most 64 KiB")
        return encoded

    async def close(self) -> None:
        if self._owns_http_client and self._http_client is not None:
            await self._http_client.aclose()

    async def verify(self, token: str) -> OidcClaims:
        if not token or len(token.encode("utf-8")) > self._MAX_TOKEN_BYTES:
            raise AuthenticationError("invalid bearer token")
        try:
            header = jwt.get_unverified_header(token)
        except PyJWTError as exc:
            raise AuthenticationError("invalid bearer token") from exc
        algorithm = header.get("alg")
        if (
            not isinstance(algorithm, str)
            or algorithm not in self._settings.oidc_allowed_algorithms
        ):
            raise AuthenticationError("bearer token algorithm is not allowed")

        key = self._static_key
        if key is None:
            key = await self._jwks_key(header, algorithm)
        try:
            payload = jwt.decode(
                token,
                key=key,
                algorithms=[algorithm],
                audience=self._settings.oidc_audience,
                issuer=self._settings.oidc_issuer,
                leeway=self._settings.oidc_clock_skew_seconds,
                options={
                    "require": ["exp", "iss", "aud", "sub"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
            return OidcClaims.model_validate(payload)
        except (PyJWTError, PydanticValidationError, ValueError, TypeError) as exc:
            raise AuthenticationError("bearer token verification failed") from exc

    async def _jwks_key(self, header: dict[str, Any], algorithm: str) -> Any:
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid or len(kid) > 255:
            raise AuthenticationError("JWKS bearer token requires a valid key id")
        keys = await self._get_jwks(force_refresh=False)
        matching = self._matching_jwks(keys, kid, algorithm)
        if not matching:
            keys = await self._get_jwks(force_refresh=True)
            matching = self._matching_jwks(keys, kid, algorithm)
        if len(matching) != 1:
            raise AuthenticationError("bearer token key id is unknown or ambiguous")
        try:
            return jwt.PyJWK.from_dict(matching[0], algorithm=algorithm).key
        except (PyJWTError, ValueError, TypeError) as exc:
            raise AuthenticationError("invalid OIDC signing key") from exc

    @staticmethod
    def _matching_jwks(
        keys: list[dict[str, Any]], kid: str, algorithm: str
    ) -> list[dict[str, Any]]:
        expected_key_type = "RSA" if algorithm == "RS256" else "EC"
        return [
            key
            for key in keys
            if key.get("kid") == kid
            and key.get("alg", algorithm) == algorithm
            and key.get("kty") == expected_key_type
            and key.get("use", "sig") == "sig"
            and (
                "key_ops" not in key
                or (isinstance(key["key_ops"], list) and "verify" in key["key_ops"])
            )
        ]

    async def _get_jwks(self, *, force_refresh: bool) -> list[dict[str, Any]]:
        now = time.monotonic()
        if not force_refresh and self._jwks is not None and now < self._jwks_expires_at:
            return self._jwks
        async with self._jwks_lock:
            now = time.monotonic()
            if not force_refresh and self._jwks is not None and now < self._jwks_expires_at:
                return self._jwks
            url = self._settings.oidc_jwks_url
            if url is None:
                raise AuthenticationError("OIDC verifier is not configured")
            if self._http_client is None:
                self._http_client = httpx.AsyncClient(
                    timeout=self._settings.oidc_http_timeout_seconds,
                    follow_redirects=False,
                )
            try:
                response = await self._http_client.get(
                    url,
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise AuthenticationError("unable to refresh OIDC signing keys") from exc
            if len(response.content) > self._MAX_JWKS_BYTES:
                raise AuthenticationError("OIDC JWKS response is too large")
            try:
                document = response.json()
                raw_keys = document["keys"]
            except (ValueError, KeyError, TypeError) as exc:
                raise AuthenticationError("invalid OIDC JWKS response") from exc
            if not isinstance(raw_keys, list) or not 1 <= len(raw_keys) <= self._MAX_JWKS_KEYS:
                raise AuthenticationError("invalid OIDC JWKS key set")
            if not all(isinstance(key, dict) for key in raw_keys):
                raise AuthenticationError("invalid OIDC JWKS key set")
            self._jwks = raw_keys
            self._jwks_expires_at = now + self._settings.oidc_jwks_cache_seconds
            return raw_keys


def _development_claims(request: Request) -> OidcClaims:
    required_headers = ("X-Tenant-Id", "X-User-Id", "X-Roles", "X-MFA")
    if any(not request.headers.get(name, "").strip() for name in required_headers):
        raise AuthenticationError("development identity headers are required")
    tenant = request.headers["X-Tenant-Id"]
    user = request.headers["X-User-Id"]
    roles = [item.strip() for item in request.headers["X-Roles"].split(",")]
    try:
        return OidcClaims(
            sub=f"dev:{user}",
            tenant_id=uuid.UUID(tenant),
            user_id=uuid.UUID(user),
            roles=[Role(role) for role in roles if role],
            mfa=request.headers["X-MFA"].lower() == "true",
            iss="cloudctl-development-bypass",
            aud="cloudctl-api",
            exp=2**31 - 1,
        )
    except (ValueError, PydanticValidationError) as exc:
        raise ForbiddenError("invalid development identity headers") from exc


async def _production_principal_claims(request: Request, principal: str) -> OidcClaims:
    """Map a trusted nginx principal onto a provisioned user row (D path).

    The principal is only meaningful when the edge proxy overwrote it after
    authenticating the caller; the mapping is server-side (``user_account``:
    tenant, roles, disabled flag) so a client can never influence tenant or
    role assignment. Unknown or disabled principals are plain 401s.
    """
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise AuthenticationError("principal identity mapping is unavailable")
    if len(principal) > 255:
        raise AuthenticationError("principal is not provisioned")
    async with database.unit_of_work() as session:
        row = await session.scalar(
            select(UserRow).where(
                UserRow.oidc_subject == principal,
                UserRow.disabled.is_(False),
            )
        )
    if row is None:
        raise AuthenticationError("principal is not provisioned")
    try:
        return OidcClaims(
            sub=row.oidc_subject,
            tenant_id=uuid.UUID(row.tenant_id),
            user_id=uuid.UUID(row.id),
            roles=[Role(role) for role in row.roles or [] if role],
            # The edge terminated authentication (HTTP BasicAuth for now);
            # the D-10 OIDC federation phase carries real MFA claims.
            mfa=True,
            iss=PRINCIPAL_ISSUER,
            aud="cloudctl-api",
            exp=2**31 - 1,
        )
    except (ValueError, PydanticValidationError) as exc:
        raise AuthenticationError("provisioned principal has an invalid identity") from exc


async def _bearer_claims(request: Request) -> OidcClaims:
    authorization = request.headers.get("Authorization", "")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthenticationError("bearer authentication is required")
    verifier: OidcJwtVerifier | None = getattr(request.app.state, "oidc_verifier", None)
    if verifier is None:
        raise AuthenticationError("OIDC verifier is not configured")
    return await verifier.verify(parts[1])


async def current_actor(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Actor:
    if settings.dev_auth_bypass:
        if settings.env not in {"development", "test"}:
            raise ForbiddenError("development authentication bypass is disabled")
        claims = _development_claims(request)
    elif settings.env == "production":
        # Identity D path (A14): a client may never self-report identity in
        # production — those headers are stripped by the edge, so their mere
        # presence is a spoofing attempt and fails closed with 401.
        forged = sorted(
            name
            for name in SELF_REPORTED_IDENTITY_HEADERS
            if request.headers.get(name, "").strip()
        )
        if forged:
            raise AuthenticationError(
                "client self-reported identity headers are rejected in "
                f"production: {', '.join(forged)}"
            )
        principal = request.headers.get(PRINCIPAL_HEADER, "").strip()
        if principal:
            claims = await _production_principal_claims(request, principal)
        else:
            claims = await _bearer_claims(request)
    else:
        claims = await _bearer_claims(request)
    return Actor(
        tenant_id=claims.tenant_id,
        user_id=claims.user_id,
        roles=frozenset(claims.roles),
        mfa=claims.mfa,
        request_id=request.state.request_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
