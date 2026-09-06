from __future__ import annotations

from typing import Any

import pytest
from cloudctl_edge.cert_store import EdgeCredentials
from cloudctl_edge.control_stream import secure_channel
from cloudctl_edge.settings import GatewaySettings, SettingsError


def _environment() -> dict[str, str]:
    return {
        "CLOUDCTL_EDGE_ID": "edge-a",
        "CLOUDCTL_HUB_ENDPOINT": "https://127.0.0.1:17443",
        "CLOUDCTL_STATE_DIR": "/var/lib/cloudctl-edge",
        "CLOUDCTL_ARTIFACT_STAGING_ROOT": "/var/lib/cloudctl-edge/staging",
        "CLOUDCTL_EDGE_CREDENTIALS_DIR": "/etc/cloudctl-edge/tls",
        "CLOUDCTL_COMPANION_TLS_CERTIFICATE": "/etc/cloudctl-edge/companion.crt",
        "CLOUDCTL_COMPANION_TLS_PRIVATE_KEY": "/etc/cloudctl-edge/companion.key",
        "CLOUDCTL_COMPANION_BIND_HOST": "127.0.0.1",
        "CLOUDCTL_DEVICE_PROFILES_PATH": "/etc/cloudctl-edge/devices.json",
        "CLOUDCTL_COMPANION_ENROLLMENT_PATH": "/etc/cloudctl-edge/enrollment.json",
        "CLOUDCTL_LAMDA_SIDECAR_PYTHON": "/opt/cloudctl-lamda/bin/python",
    }


def test_tls_server_name_is_optional_and_explicit() -> None:
    environment = _environment()
    assert GatewaySettings.from_env(environment).hub_tls_server_name is None
    environment["CLOUDCTL_HUB_TLS_SERVER_NAME"] = "hub.seoul.example"
    assert GatewaySettings.from_env(environment).hub_tls_server_name == "hub.seoul.example"


@pytest.mark.parametrize(
    "value",
    ["", "   ", " hub.example", "hub.example ", "https://hub.example", "hub.example:7443"],
)
def test_tls_server_name_rejects_blank_uri_whitespace_and_port(value: str) -> None:
    environment = _environment()
    environment["CLOUDCTL_HUB_TLS_SERVER_NAME"] = value
    with pytest.raises(SettingsError, match="CLOUDCTL_HUB_TLS_SERVER_NAME"):
        GatewaySettings.from_env(environment)


def test_secure_channel_uses_override_without_changing_mtls_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    channel_credentials = object()

    def fake_ssl_channel_credentials(**kwargs: bytes) -> object:
        captured["credential_inputs"] = kwargs
        return channel_credentials

    def fake_secure_channel(target: str, credentials: object, **kwargs: object) -> object:
        captured.update(target=target, credentials=credentials, **kwargs)
        return object()

    monkeypatch.setattr(
        "cloudctl_edge.control_stream.grpc.ssl_channel_credentials",
        fake_ssl_channel_credentials,
    )
    monkeypatch.setattr("cloudctl_edge.control_stream.grpc.aio.secure_channel", fake_secure_channel)
    identity = EdgeCredentials(
        certificate=b"edge-certificate",
        private_key=b"edge-private-key",
        certificate_chain=b"trusted-ca",
    )
    secure_channel(
        "https://127.0.0.1:17443",
        identity,
        tls_server_name="hub.seoul.example",
    )
    assert captured["target"] == "127.0.0.1:17443"
    assert captured["credentials"] is channel_credentials
    assert captured["options"] == (("grpc.ssl_target_name_override", "hub.seoul.example"),)
    assert captured["credential_inputs"] == {
        "root_certificates": b"trusted-ca",
        "private_key": b"edge-private-key",
        "certificate_chain": b"edge-certificate",
    }


def test_secure_channel_default_has_no_name_override(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        "cloudctl_edge.control_stream.grpc.ssl_channel_credentials", lambda **_kwargs: object()
    )

    def fake_secure_channel(target: str, credentials: object, **kwargs: object) -> object:
        captured.update(target=target, credentials=credentials, **kwargs)
        return object()

    monkeypatch.setattr("cloudctl_edge.control_stream.grpc.aio.secure_channel", fake_secure_channel)
    secure_channel(
        "https://hub.example:7443",
        EdgeCredentials(b"certificate", b"private-key", b"trusted-ca"),
    )
    assert captured["options"] == ()
