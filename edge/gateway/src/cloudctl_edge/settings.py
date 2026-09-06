from __future__ import annotations

import ipaddress
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class SettingsError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GatewaySettings:
    edge_id: str
    hub_endpoint: str
    state_dir: Path
    artifact_staging_root: Path
    edge_credentials_dir: Path
    companion_tls_certificate: Path
    companion_tls_private_key: Path
    companion_bind_host: str
    companion_bind_port: int
    device_profiles_path: Path
    enrollment_path: Path
    hub_tls_server_name: str | None = None
    software_version: str = "0.1.0"
    lamda_sidecar_python: Path | None = None
    lab_adb_debug_enabled: bool = False
    lab_adb_path: Path | None = None
    lab_adb_device_id: str | None = None

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> GatewaySettings:
        values = os.environ if environment is None else environment

        def required(name: str) -> str:
            value = values.get(name, "").strip()
            if not value:
                raise SettingsError(f"{name} is required")
            return value

        try:
            bind_port = int(values.get("CLOUDCTL_COMPANION_BIND_PORT", "8443"))
        except ValueError as exc:
            raise SettingsError("CLOUDCTL_COMPANION_BIND_PORT must be an integer") from exc
        lab_adb_enabled = values.get("CLOUDCTL_LAB_ADB_DEBUG_ENABLED", "").strip().lower()
        if lab_adb_enabled not in {"", "0", "false", "1", "true"}:
            raise SettingsError("CLOUDCTL_LAB_ADB_DEBUG_ENABLED must be true or false")
        raw_adb_path = values.get("CLOUDCTL_LAB_ADB_PATH", "").strip()
        raw_adb_device_id = values.get("CLOUDCTL_LAB_ADB_DEVICE_ID", "").strip()
        tls_server_name = _optional_tls_server_name(
            values.get("CLOUDCTL_HUB_TLS_SERVER_NAME")
            if "CLOUDCTL_HUB_TLS_SERVER_NAME" in values
            else None
        )
        return cls(
            edge_id=required("CLOUDCTL_EDGE_ID"),
            hub_endpoint=required("CLOUDCTL_HUB_ENDPOINT"),
            state_dir=Path(required("CLOUDCTL_STATE_DIR")),
            artifact_staging_root=Path(required("CLOUDCTL_ARTIFACT_STAGING_ROOT")),
            edge_credentials_dir=Path(required("CLOUDCTL_EDGE_CREDENTIALS_DIR")),
            companion_tls_certificate=Path(required("CLOUDCTL_COMPANION_TLS_CERTIFICATE")),
            companion_tls_private_key=Path(required("CLOUDCTL_COMPANION_TLS_PRIVATE_KEY")),
            companion_bind_host=required("CLOUDCTL_COMPANION_BIND_HOST"),
            companion_bind_port=bind_port,
            device_profiles_path=Path(required("CLOUDCTL_DEVICE_PROFILES_PATH")),
            enrollment_path=Path(required("CLOUDCTL_COMPANION_ENROLLMENT_PATH")),
            hub_tls_server_name=tls_server_name,
            software_version=values.get("CLOUDCTL_SOFTWARE_VERSION", "0.1.0").strip() or "0.1.0",
            lamda_sidecar_python=Path(required("CLOUDCTL_LAMDA_SIDECAR_PYTHON")),
            lab_adb_debug_enabled=lab_adb_enabled in {"1", "true"},
            lab_adb_path=Path(raw_adb_path) if raw_adb_path else None,
            lab_adb_device_id=raw_adb_device_id or None,
        )

    def validate_runtime(self) -> None:
        if (
            not self.companion_tls_certificate.is_file()
            or not self.companion_tls_private_key.is_file()
        ):
            raise SettingsError("Companion TLS certificate and private key are required")
        if not 1 <= self.companion_bind_port <= 65535:
            raise SettingsError("Companion bind port is invalid")
        if not self.companion_bind_host:
            raise SettingsError("Companion bind host must be explicit")
        if not self.hub_endpoint.startswith("https://") or self.hub_endpoint.endswith(":65000"):
            raise SettingsError(
                "Edge Hub endpoint must use HTTPS and cannot target device port 65000"
            )
        if self.hub_tls_server_name is not None:
            validate_hub_tls_server_name(self.hub_tls_server_name)
        for name in ("edge.crt", "edge.key", "ca.crt"):
            if not (self.edge_credentials_dir / name).is_file():
                raise SettingsError("complete Edge mTLS credentials are required")
        if not self.device_profiles_path.is_file():
            raise SettingsError("device profile configuration is required")
        if not self.enrollment_path.is_file():
            raise SettingsError("Companion enrollment configuration is required")
        if (
            self.lamda_sidecar_python is None
            or not self.lamda_sidecar_python.is_absolute()
            or not self.lamda_sidecar_python.is_file()
        ):
            raise SettingsError("an absolute LAMDA sidecar Python runtime is required")
        if self.lab_adb_debug_enabled and (
            self.lab_adb_path is None
            or not self.lab_adb_path.is_absolute()
            or not self.lab_adb_path.is_file()
            or self.lab_adb_device_id is None
        ):
            raise SettingsError(
                "lab ADB debug requires an absolute ADB executable and explicit device ID"
            )


_DNS_NAME = re.compile(
    r"(?=^.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.?$"
)


def _optional_tls_server_name(value: str | None) -> str | None:
    if value is None:
        return None
    if not value or value != value.strip():
        raise SettingsError("CLOUDCTL_HUB_TLS_SERVER_NAME cannot be blank or contain whitespace")
    return validate_hub_tls_server_name(value)


def validate_hub_tls_server_name(value: str) -> str:
    if any(character.isspace() for character in value):
        raise SettingsError("CLOUDCTL_HUB_TLS_SERVER_NAME cannot contain whitespace")
    if any(marker in value for marker in ("://", "/", "\\", ":", "?", "#", "@")):
        raise SettingsError(
            "CLOUDCTL_HUB_TLS_SERVER_NAME must be a DNS name or IP address without URI or port"
        )
    try:
        ipaddress.ip_address(value)
    except ValueError as exc:
        if _DNS_NAME.fullmatch(value) is None:
            raise SettingsError(
                "CLOUDCTL_HUB_TLS_SERVER_NAME is not a valid DNS name or IP address"
            ) from exc
    return value
