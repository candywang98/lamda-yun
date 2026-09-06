from __future__ import annotations

import pytest
from cloudctl_outbox.main import _build_debug_sink_from_environment


def test_debug_sink_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "CLOUDCTL_DEBUG_HUB_URL",
        "CLOUDCTL_DEBUG_HUB_GRPC_TARGET",
        "CLOUDCTL_DEBUG_HUB_CLIENT_CERTIFICATE",
        "CLOUDCTL_DEBUG_HUB_CLIENT_PRIVATE_KEY",
        "CLOUDCTL_DEBUG_HUB_CA_CERTIFICATE",
    ):
        monkeypatch.delenv(key, raising=False)
    assert _build_debug_sink_from_environment() is None


def test_debug_sink_requires_complete_mtls_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDCTL_DEBUG_HUB_URL", "https://hub.example")
    with pytest.raises(RuntimeError, match="certificate paths"):
        _build_debug_sink_from_environment()


def test_debug_sink_prefers_explicit_grpc_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLOUDCTL_DEBUG_HUB_URL", raising=False)
    monkeypatch.setenv("CLOUDCTL_DEBUG_HUB_GRPC_TARGET", "edge-hub.internal:7443")
    monkeypatch.setenv("CLOUDCTL_DEBUG_HUB_CLIENT_CERTIFICATE", "client.crt")
    monkeypatch.setenv("CLOUDCTL_DEBUG_HUB_CLIENT_PRIVATE_KEY", "client.key")
    monkeypatch.setenv("CLOUDCTL_DEBUG_HUB_CA_CERTIFICATE", "ca.crt")
    monkeypatch.setattr("cloudctl_outbox.main.DebugHubGrpcSink", lambda *args, **kwargs: args)
    assert _build_debug_sink_from_environment() == ("edge-hub.internal:7443",)
