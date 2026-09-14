"""Control-plane settings with secure environment validation."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

OidcAlgorithm = Literal["RS256", "ES256"]


def default_oidc_algorithms() -> list[OidcAlgorithm]:
    return ["RS256"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLOUDCTL_", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    repository_mode: Literal["memory", "sqlite", "postgresql"] = "memory"
    database_url: str | None = None
    sqlite_path: Path = Path(".cloudctl/cloudctl.db")
    oidc_issuer: str = Field(
        default="http://localhost:8080/realms/cloudctl", min_length=1, max_length=2048
    )
    oidc_audience: str = Field(default="cloudctl-api", min_length=1, max_length=255)
    oidc_jwks_url: str | None = Field(default=None, min_length=1, max_length=2048)
    oidc_public_key_pem: str | None = Field(default=None, min_length=1, max_length=65_536)
    oidc_public_key_path: Path | None = None
    oidc_allowed_algorithms: list[OidcAlgorithm] = Field(default_factory=default_oidc_algorithms)
    oidc_jwks_cache_seconds: int = Field(default=300, ge=60, le=86_400)
    oidc_clock_skew_seconds: int = Field(default=30, ge=0, le=300)
    oidc_http_timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
    dev_auth_bypass: bool = False
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:5174",
            "http://localhost:5174",
        ]
    )
    debug_relay_url: str = "wss://127.0.0.1:7443/debug"
    event_poll_seconds: float = Field(default=1.0, ge=0.05, le=30.0)
    object_store_mode: Literal["memory", "s3", "filesystem"] = "memory"
    object_store_dir: Path = Path(".cloudctl/media")
    public_base_url: str | None = None
    s3_endpoint: str | None = None
    s3_bucket: str = "cloudctl"
    s3_region: str = "us-east-1"
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None
    media_upload_expires_seconds: int = Field(default=900, ge=60, le=3600)
    operation_executor_urls: dict[str, str] = Field(default_factory=dict)
    operation_executor_bearer_token: SecretStr | None = None
    operation_executor_timeout_seconds: float = Field(default=15.0, ge=1.0, le=120.0)
    automation_signing_public_keys: dict[str, str] = Field(default_factory=dict)
    automation_rollout_max_failure_rate: float = Field(default=0.02, ge=0.0, le=0.25)
    wechat_api_base_url: str = Field(
        default="https://api.weixin.qq.com", min_length=8, max_length=512
    )
    wechat_http_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    wechat_token_expiry_margin_seconds: int = Field(default=120, ge=30, le=600)
    wechat_secret_encryption_key: SecretStr | None = None
    apk_analysis_public_keys: dict[str, str] = Field(default_factory=dict)
    apk_denied_permissions: list[str] = Field(
        default_factory=lambda: [
            "android.permission.BIND_DEVICE_ADMIN",
            "android.permission.MANAGE_DEVICE_ADMINS",
            "android.permission.REQUEST_DELETE_PACKAGES",
            "android.permission.REQUEST_INSTALL_PACKAGES",
        ]
    )

    @model_validator(mode="after")
    def secure_production(self) -> "Settings":
        if self.dev_auth_bypass and self.env not in {"development", "test"}:
            raise ValueError("CLOUDCTL_DEV_AUTH_BYPASS is only allowed in development or test")
        if self.env == "production" and "*" in self.cors_allowed_origins:
            raise ValueError("wildcard CORS origins are forbidden in production")
        if self.repository_mode == "postgresql":
            if not self.database_url:
                raise ValueError("CLOUDCTL_DATABASE_URL is required for PostgreSQL mode")
            if not self.database_url.startswith("postgresql+asyncpg://"):
                raise ValueError("CLOUDCTL_DATABASE_URL must use postgresql+asyncpg://")
        key_sources = sum(
            value is not None
            for value in (self.oidc_jwks_url, self.oidc_public_key_pem, self.oidc_public_key_path)
        )
        if key_sources > 1:
            raise ValueError(
                "OIDC verification sources are mutually exclusive; configure exactly one"
            )
        if self.env == "production" and not self.dev_auth_bypass and key_sources != 1:
            raise ValueError("production requires exactly one OIDC verification source")
        if self.env == "production":
            if self.repository_mode != "postgresql":
                raise ValueError("production requires PostgreSQL repository mode")
            if self.object_store_mode != "s3":
                raise ValueError("production requires S3 object storage mode")
            if not self.oidc_issuer.startswith("https://"):
                raise ValueError("CLOUDCTL_OIDC_ISSUER must use HTTPS in production")
            if self.oidc_jwks_url is not None and not self.oidc_jwks_url.startswith("https://"):
                raise ValueError("CLOUDCTL_OIDC_JWKS_URL must use HTTPS in production")
        if not self.oidc_allowed_algorithms:
            raise ValueError("at least one OIDC JWT algorithm must be allowed")
        if len(set(self.apk_denied_permissions)) != len(self.apk_denied_permissions):
            raise ValueError("CLOUDCTL_APK_DENIED_PERMISSIONS cannot contain duplicates")
        if self.object_store_mode == "s3":
            if not self.s3_bucket.strip():
                raise ValueError("CLOUDCTL_S3_BUCKET is required for S3 object storage")
            if self.s3_access_key is None or self.s3_secret_key is None:
                raise ValueError("S3 access and secret keys are required for S3 object storage")
            if self.s3_endpoint is not None:
                s3_endpoint = urlsplit(self.s3_endpoint)
                if s3_endpoint.scheme not in {"http", "https"} or not s3_endpoint.netloc:
                    raise ValueError("CLOUDCTL_S3_ENDPOINT must be an absolute HTTP(S) URL")
                if s3_endpoint.username is not None or s3_endpoint.password is not None:
                    raise ValueError("CLOUDCTL_S3_ENDPOINT cannot contain credentials")
                if s3_endpoint.query or s3_endpoint.fragment:
                    raise ValueError("CLOUDCTL_S3_ENDPOINT cannot contain query or fragment")
                if self.env == "production" and s3_endpoint.scheme != "https":
                    raise ValueError("CLOUDCTL_S3_ENDPOINT must use HTTPS in production")
        if self.operation_executor_urls:
            token = self.operation_executor_bearer_token
            if token is None or not token.get_secret_value().strip():
                raise ValueError(
                    "CLOUDCTL_OPERATION_EXECUTOR_BEARER_TOKEN is required when adapters "
                    "are configured"
                )
        for operation_key, endpoint in self.operation_executor_urls.items():
            parsed = urlsplit(endpoint)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"executor URL for {operation_key} must be absolute HTTP(S)")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError(f"executor URL for {operation_key} cannot contain credentials")
            if parsed.query or parsed.fragment:
                raise ValueError(
                    f"executor URL for {operation_key} cannot contain query or fragment"
                )
            if self.env == "production" and parsed.scheme != "https":
                raise ValueError(f"executor URL for {operation_key} must use HTTPS in production")
        return self

    def resolved_database_url(self) -> str:
        if self.repository_mode == "memory":
            return "sqlite+aiosqlite:///:memory:"
        if self.repository_mode == "sqlite":
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite+aiosqlite:///{self.sqlite_path.as_posix()}"
        assert self.database_url is not None
        return self.database_url

    def auto_create_schema(self) -> bool:
        return self.env in {"development", "test"} and self.repository_mode in {
            "memory",
            "sqlite",
        }

    def auto_seed_development_data(self) -> bool:
        return (
            self.env == "development" and self.repository_mode == "memory" and self.dev_auth_bypass
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
