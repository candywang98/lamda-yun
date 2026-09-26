from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from cloudctl_api import create_app
from cloudctl_api.auth import OidcJwtVerifier
from cloudctl_api.media_store import InMemoryObjectStore
from cloudctl_api.settings import Settings
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import RSAAlgorithm
from pydantic import SecretStr
from pydantic import ValidationError as PydanticValidationError
from starlette.types import Receive, Scope, Send

ISSUER = "https://identity.example.test/realms/cloudctl"
AUDIENCE = "cloudctl-api"
TENANT = "00000000-0000-7000-8000-000000007111"
USER = "00000000-0000-7000-8000-000000007222"


def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def public_pem(
    private_key: rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey,
) -> str:
    return (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )


def access_token(
    private_key: rsa.RSAPrivateKey,
    *,
    kid: str = "auth-key-1",
    overrides: dict[str, Any] | None = None,
) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": "user:authorized-operator",
        "tenant_id": TENANT,
        "user_id": USER,
        "roles": ["viewer"],
        "mfa": True,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "nbf": now - 1,
        "exp": now + 300,
    }
    claims.update(overrides or {})
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def production_settings(public_key: str) -> Settings:
    return Settings(
        env="production",
        repository_mode="postgresql",
        database_url="postgresql+asyncpg://cloudctl:test@db.example.test/cloudctl",
        dev_auth_bypass=False,
        oidc_issuer=ISSUER,
        oidc_audience=AUDIENCE,
        oidc_public_key_pem=public_key,
        oidc_allowed_algorithms=["RS256"],
        object_store_mode="s3",
        s3_endpoint="https://s3.example.test",
        s3_access_key=SecretStr("test-access-key"),
        s3_secret_key=SecretStr("test-secret-key"),
        wechat_secret_encryption_key=SecretStr(Fernet.generate_key().decode()),
    )


@pytest.fixture
async def authenticated_client() -> AsyncIterator[tuple[httpx.AsyncClient, rsa.RSAPrivateKey]]:
    private_key = rsa_key()
    app = create_app(
        production_settings(public_pem(private_key)),
        object_store=InMemoryObjectStore(),
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://api.example.test"
        ) as client:
            yield client, private_key


@pytest.mark.asyncio
async def test_valid_application_verified_token_builds_actor(
    authenticated_client: tuple[httpx.AsyncClient, rsa.RSAPrivateKey],
) -> None:
    client, private_key = authenticated_client
    response = await client.get(
        "/api/v1/session",
        headers={"Authorization": f"Bearer {access_token(private_key)}"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert isinstance(payload.pop("requestId"), str)
    assert payload == {
        "tenantId": TENANT,
        "userId": USER,
        "roles": ["viewer"],
        "mfa": True,
    }


@pytest.mark.asyncio
async def test_es256_static_public_key_verification() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    settings = Settings(
        env="production",
        repository_mode="postgresql",
        database_url="postgresql+asyncpg://cloudctl:test@db.example.test/cloudctl",
        dev_auth_bypass=False,
        oidc_issuer=ISSUER,
        oidc_audience=AUDIENCE,
        oidc_public_key_pem=public_pem(private_key),
        oidc_allowed_algorithms=["ES256"],
        object_store_mode="s3",
        s3_endpoint="https://s3.example.test",
        s3_access_key=SecretStr("test-access-key"),
        s3_secret_key=SecretStr("test-secret-key"),
        wechat_secret_encryption_key=SecretStr(Fernet.generate_key().decode()),
    )
    app = create_app(settings, object_store=InMemoryObjectStore())
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "user:authorized-operator",
            "tenant_id": TENANT,
            "user_id": USER,
            "roles": ["viewer"],
            "mfa": True,
            "iss": ISSUER,
            "aud": AUDIENCE,
            "nbf": now - 1,
            "exp": now + 300,
        },
        private_key,
        algorithm="ES256",
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://api.example.test"
        ) as client:
            response = await client.get(
                "/api/v1/session", headers={"Authorization": f"Bearer {token}"}
            )

    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_scope_claims_and_development_headers_are_ignored_without_bypass() -> None:
    private_key = rsa_key()
    app = create_app(
        production_settings(public_pem(private_key)),
        object_store=InMemoryObjectStore(),
    )

    async def inject_scope_claims(
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        forged_scope = dict(scope)
        forged_scope["cloudctl.oidc_claims"] = {
            "sub": "forged",
            "tenant_id": TENANT,
            "user_id": USER,
            "roles": ["security_admin"],
            "mfa": True,
            "iss": ISSUER,
            "aud": AUDIENCE,
            "exp": int(time.time()) + 300,
        }
        await app(forged_scope, receive, send)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=inject_scope_claims),
            base_url="https://api.example.test",
        ) as client:
            response = await client.get(
                "/api/v1/session",
                headers={
                    "X-Tenant-Id": TENANT,
                    "X-User-Id": USER,
                    "X-Roles": "security_admin",
                    "X-MFA": "true",
                },
            )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claim_overrides", "relative_time_claim"),
    [
        pytest.param({"exp": -300}, "exp", id="expired"),
        pytest.param({"nbf": 300}, "nbf", id="not-yet-valid"),
        pytest.param(
            {"iss": "https://identity.example.test/realms/other"},
            None,
            id="wrong-issuer",
        ),
        pytest.param({"aud": "other-api"}, None, id="wrong-audience"),
    ],
)
async def test_invalid_registered_claims_are_rejected(
    authenticated_client: tuple[httpx.AsyncClient, rsa.RSAPrivateKey],
    claim_overrides: dict[str, Any],
    relative_time_claim: str | None,
) -> None:
    client, private_key = authenticated_client
    resolved_overrides = dict(claim_overrides)
    if relative_time_claim is not None:
        resolved_overrides[relative_time_claim] = int(time.time()) + int(
            resolved_overrides[relative_time_claim]
        )
    response = await client.get(
        "/api/v1/session",
        headers={
            "Authorization": f"Bearer {access_token(private_key, overrides=resolved_overrides)}"
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_wrong_signature_and_disallowed_algorithm_are_rejected(
    authenticated_client: tuple[httpx.AsyncClient, rsa.RSAPrivateKey],
) -> None:
    client, _ = authenticated_client
    wrong_signature = await client.get(
        "/api/v1/session",
        headers={"Authorization": f"Bearer {access_token(rsa_key())}"},
    )
    now = int(time.time())
    ec_key = ec.generate_private_key(ec.SECP256R1())
    es_token = jwt.encode(
        {
            "sub": "user:authorized-operator",
            "tenant_id": TENANT,
            "user_id": USER,
            "roles": ["viewer"],
            "iss": ISSUER,
            "aud": AUDIENCE,
            "nbf": now - 1,
            "exp": now + 300,
        },
        ec_key,
        algorithm="ES256",
        headers={"kid": "ec-key"},
    )
    disallowed_algorithm = await client.get(
        "/api/v1/session",
        headers={"Authorization": f"Bearer {es_token}"},
    )

    assert wrong_signature.status_code == 401
    assert disallowed_algorithm.status_code == 401


@pytest.mark.asyncio
async def test_https_jwks_is_cached_and_used_for_verification() -> None:
    private_key = rsa_key()
    encoded_jwk = RSAAlgorithm.to_jwk(private_key.public_key())
    jwk: dict[str, Any] = json.loads(encoded_jwk)
    jwk.update({"kid": "rotating-key-1", "alg": "RS256", "use": "sig"})
    calls = 0

    def jwks_response(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url == "https://identity.example.test/.well-known/jwks.json"
        return httpx.Response(200, json={"keys": [jwk]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(jwks_response)) as http_client:
        verifier = OidcJwtVerifier(
            Settings(
                env="test",
                repository_mode="memory",
                dev_auth_bypass=False,
                oidc_issuer=ISSUER,
                oidc_audience=AUDIENCE,
                oidc_jwks_url="https://identity.example.test/.well-known/jwks.json",
            ),
            http_client=http_client,
        )
        token = access_token(private_key, kid="rotating-key-1")
        first = await verifier.verify(token)
        second = await verifier.verify(token)

    assert first.user_id == second.user_id
    assert calls == 1


def test_production_configuration_is_fail_closed() -> None:
    with pytest.raises(PydanticValidationError, match="DEV_AUTH_BYPASS"):
        Settings(
            env="production",
            repository_mode="memory",
            dev_auth_bypass=True,
            oidc_issuer=ISSUER,
        )
    with pytest.raises(PydanticValidationError, match="OIDC verification source"):
        Settings(
            env="production",
            repository_mode="postgresql",
            database_url="postgresql+asyncpg://cloudctl:test@db.example.test/cloudctl",
            dev_auth_bypass=False,
            oidc_issuer=ISSUER,
        )
    with pytest.raises(PydanticValidationError, match="HTTPS"):
        Settings(
            env="production",
            repository_mode="postgresql",
            database_url="postgresql+asyncpg://cloudctl:test@db.example.test/cloudctl",
            dev_auth_bypass=False,
            oidc_issuer=ISSUER,
            oidc_jwks_url="http://identity.example.test/jwks.json",
            object_store_mode="s3",
            s3_endpoint="https://s3.example.test",
            s3_access_key=SecretStr("test-access-key"),
            s3_secret_key=SecretStr("test-secret-key"),
        )
    with pytest.raises(PydanticValidationError, match="S3_ENDPOINT.*HTTPS"):
        Settings(
            env="production",
            repository_mode="postgresql",
            database_url="postgresql+asyncpg://cloudctl:test@db.example.test/cloudctl",
            dev_auth_bypass=False,
            oidc_issuer=ISSUER,
            oidc_public_key_pem=public_pem(rsa_key()),
            object_store_mode="s3",
            s3_endpoint="http://minio.example.test",
            s3_access_key=SecretStr("test-access-key"),
            s3_secret_key=SecretStr("test-secret-key"),
        )
    with pytest.raises(PydanticValidationError, match="PostgreSQL"):
        Settings(
            env="production",
            repository_mode="memory",
            dev_auth_bypass=False,
            oidc_issuer=ISSUER,
            oidc_public_key_pem=public_pem(rsa_key()),
        )
    with pytest.raises(PydanticValidationError, match=r"postgresql\+asyncpg"):
        Settings(
            env="test",
            repository_mode="postgresql",
            database_url="sqlite+aiosqlite:///wrong-driver.db",
        )

    # Production must provision the WeChat appSecret encryption key: without it
    # the cipher degrades to a marked base64 envelope instead of Fernet.
    with pytest.raises(PydanticValidationError, match="WECHAT_SECRET_ENCRYPTION_KEY is required"):
        Settings(
            env="production",
            repository_mode="postgresql",
            database_url="postgresql+asyncpg://cloudctl:test@db.example.test/cloudctl",
            dev_auth_bypass=False,
            oidc_issuer=ISSUER,
            oidc_audience=AUDIENCE,
            oidc_public_key_pem=public_pem(rsa_key()),
            object_store_mode="s3",
            s3_endpoint="https://s3.example.test",
            s3_access_key=SecretStr("test-access-key"),
            s3_secret_key=SecretStr("test-secret-key"),
        )
    # A configured key must be a usable Fernet key in every environment.
    with pytest.raises(PydanticValidationError, match="valid Fernet key"):
        Settings(
            env="test",
            repository_mode="memory",
            wechat_secret_encryption_key=SecretStr("not-a-fernet-key"),
        )


@pytest.mark.asyncio
async def test_production_startup_does_not_create_schema() -> None:
    private_key = rsa_key()
    settings = production_settings(public_pem(private_key))
    assert settings.auto_create_schema() is False
    app = create_app(settings, object_store=InMemoryObjectStore())

    async with app.router.lifespan_context(app):
        pass


def test_module_level_uvicorn_target_imports_with_fail_closed_defaults() -> None:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("CLOUDCTL_")
    }
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and repository-local module
        [
            sys.executable,
            "-c",
            (
                "from cloudctl_api.app import app; "
                "assert app.title == 'CloudCtl Control API'; "
                "assert app.state.settings.dev_auth_bypass is False"
            ),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
