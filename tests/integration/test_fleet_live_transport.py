"""fleet_live_transport adapter unit tests (L10, live-capabilities/v1 K13).

NOT_TESTED_LOCALLY: real ICE/TURN connectivity, DTLS/SRTP media flow, and
coturn enforcement of the minted credentials. These tests cover the shapes
and configuration model only; live TURN verification is a deploy seam.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import replace

import pytest

# fleet_live_transport lives in services/edge-hub/src, which the repo pytest
# pythonpath already exposes; adapters are pure stdlib, no DB needed here.
from fleet_live_transport import (
    ConnectionQuota,
    FleetLiveTransportRegistry,
    JpegHttpsAdapter,
    QuotaExceeded,
    TransportError,
    TransportUnavailable,
    TransportUnsupported,
    TurnConfig,
    TurnConfigError,
    WebRtcAdapter,
    default_registry,
    mint_turn_credentials,
    validate_ice_candidate,
    validate_sdp,
    validate_sdp_exchange,
    validate_turn_credentials,
)

TURN = TurnConfig(
    ice_servers=("turn:turn1.example.test:3478", "turns:turn1.example.test:5349"),
    shared_secret="unit-test-turn-secret-0123456789abcdef",  # noqa: S106 - test fixture
    credential_ttl_seconds=600,
    transport_policy="relay",
    connection_quota=2,
)

PREPARE = {
    "session_id": "sid-0001",
    "device_id": "dev-0001",
    "tenant_id": "tenant-0001",
    "tier": "WEBRTC",
}


# ---- registry: closed-set tier × transport selection ----


def test_registry_maps_the_closed_tier_transport_matrix() -> None:
    registry = default_registry(TURN)
    assert isinstance(registry.select("JPEG_PREVIEW"), JpegHttpsAdapter)
    assert isinstance(registry.select("INTERACTIVE_REMOTE"), JpegHttpsAdapter)
    assert isinstance(registry.select("WEBRTC"), WebRtcAdapter)
    assert isinstance(registry.select("WEBRTC", "WEBRTC"), WebRtcAdapter)


@pytest.mark.parametrize(
    ("tier", "transport"),
    [
        ("JPEG_PREVIEW", "WEBRTC"),
        ("INTERACTIVE_REMOTE", "WEBRTC"),
        ("WEBRTC", "JPEG_WS"),
        ("NO_SUCH_TIER", None),
        ("NO_SUCH_TIER", "JPEG_WS"),
    ],
)
def test_registry_rejects_combinations_outside_the_closed_set(
    tier: str, transport: str | None
) -> None:
    registry = default_registry(TURN)
    with pytest.raises(TransportUnsupported):
        registry.select(tier, transport)


def test_jpeg_adapter_needs_no_turn() -> None:
    adapter = JpegHttpsAdapter()
    plan = adapter.prepare(
        session_id="sid-j",
        device_id="dev-j",
        tenant_id="t-j",
        tier="JPEG_PREVIEW",
    )
    assert plan.kind == "JPEG_WS"
    assert plan.turn_required is False
    assert "iceServers" not in plan.details
    assert plan.details["signaling"] == ["frame", "state", "hello", "input"]
    assert plan.details["caps"]["fps"] <= 5
    assert plan.details["caps"]["longEdge"] <= 720
    assert plan.details["caps"]["quality"] <= 60
    with pytest.raises(TransportUnsupported):
        adapter.prepare(
            session_id="sid-j", device_id="dev-j", tenant_id="t-j", tier="WEBRTC"
        )


def test_webrtc_adapter_refuses_without_turn_config() -> None:
    adapter = WebRtcAdapter(None)
    with pytest.raises(TransportUnavailable, match="TURN"):
        adapter.prepare(**PREPARE)


def test_webrtc_plan_carries_short_lived_credentials_and_quota() -> None:
    adapter = WebRtcAdapter(TURN)
    plan = adapter.prepare(**PREPARE)
    assert plan.kind == "WEBRTC"
    assert plan.turn_required is True
    (ice,) = plan.details["iceServers"]
    assert ice["urls"] == list(TURN.ice_servers)
    assert ice["username"].endswith(":live-sid-0001")
    assert ice["username"].split(":", 1)[0].isdigit()
    assert plan.details["transportPolicy"] == "relay"
    assert plan.details["connectionQuota"] == 2
    assert plan.details["credentialTtlSeconds"] == 600


# ---- TURN credentials ----


def test_minted_credentials_follow_coturn_rest_shape() -> None:
    credentials = mint_turn_credentials(TURN, session_id="sid-0001", now_unix=1_000_000)
    assert credentials.expires_at_unix == 1_000_000 + 600
    assert credentials.username == f"{credentials.expires_at_unix}:live-sid-0001"
    expected = base64.b64encode(
        hmac.new(
            TURN.shared_secret.encode(), credentials.username.encode(), hashlib.sha1
        ).digest()
    ).decode("ascii")
    assert credentials.password == expected


def test_credential_validation_rejects_wrong_expired_and_malformed() -> None:
    credentials = mint_turn_credentials(TURN, session_id="sid-x", now_unix=1_000_000)
    assert validate_turn_credentials(
        TURN, credentials.username, credentials.password, now_unix=1_000_500
    )
    assert not validate_turn_credentials(
        TURN, credentials.username, "wrong-password", now_unix=1_000_500
    )
    assert not validate_turn_credentials(
        TURN, credentials.username, credentials.password, now_unix=1_000_601
    )
    assert not validate_turn_credentials(
        TURN, "not-a-timestamp", credentials.password, now_unix=1_000_500
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"ice_servers": ()},
        {"ice_servers": ("ftp://not-ice",)},
        {"shared_secret": ""},
        {"credential_ttl_seconds": 299},
        {"credential_ttl_seconds": 3601},
        {"transport_policy": "smoke"},
        {"connection_quota": 0},
    ],
)
def test_turn_config_validation_bounds(overrides: dict) -> None:
    with pytest.raises(TurnConfigError):
        replace(TURN, **overrides)


def test_turn_config_from_env_roundtrip_and_missing() -> None:
    assert TurnConfig.from_env({}) is None
    config = TurnConfig.from_env(
        {
            "CLOUDCTL_LIVE_TURN_ICE_SERVERS": "turn:a.test:3478, turns:b.test:5349",
            "CLOUDCTL_LIVE_TURN_SHARED_SECRET": "secret",
            "CLOUDCTL_LIVE_TURN_CREDENTIAL_TTL_SECONDS": "300",
            "CLOUDCTL_LIVE_TURN_TRANSPORT_POLICY": "relay",
            "CLOUDCTL_LIVE_TURN_CONNECTION_QUOTA": "5",
        }
    )
    assert config is not None
    assert config.ice_servers == ("turn:a.test:3478", "turns:b.test:5349")
    assert config.credential_ttl_seconds == 300
    assert config.transport_policy == "relay"
    assert config.connection_quota == 5


# ---- SDP / ICE candidate exchange shapes ----


def test_sdp_exchange_shape_validation() -> None:
    offer = {"type": "offer", "sdp": "v=0\r\no=- 4611731400430051336 2 IN IP4 127.0.0.1"}
    answer = {
        "type": "answer",
        "sdp": "v=0\r\no=- 4611731400430051336 2 IN IP4 127.0.0.1",
        "sessionId": "sdp-session-1",
    }
    validate_sdp_exchange({**offer, "sessionId": "sdp-session-1"}, answer)
    with pytest.raises(TransportError):
        validate_sdp_exchange(
            {**offer, "sessionId": "sdp-session-other"}, answer
        )  # mismatched SDP sessions
    with pytest.raises(TransportError):
        validate_sdp(answer, expected_type="offer")
    with pytest.raises(TransportError):
        validate_sdp({"type": "offer", "sdp": "not-an-sdp"})
    with pytest.raises(TransportError):
        validate_sdp({"type": " renegotiate", "sdp": "v=0"})


def test_ice_candidate_shape_validation() -> None:
    validate_ice_candidate(
        {
            "candidate": "candidate:842163049 1 udp 1677729535 192.0.2.1 54400 typ srflx",
            "sdpMid": "0",
            "sdpMLineIndex": 0,
        }
    )
    with pytest.raises(TransportError):
        validate_ice_candidate({"candidate": "not-a-candidate", "sdpMLineIndex": 0})
    with pytest.raises(TransportError):
        validate_ice_candidate(
            {"candidate": "candidate:1 1 udp 1 192.0.2.1 1 typ host", "sdpMLineIndex": -1}
        )
    with pytest.raises(TransportError):
        validate_ice_candidate(
            {"candidate": "candidate:1 1 udp 1 192.0.2.1 1 typ host", "sdpMid": 3}
        )


# ---- connection quota (GATE_BANDWIDTH_BUDGET accounting) ----


def test_connection_quota_enforces_limit_and_release() -> None:
    quota = ConnectionQuota(limit=2)
    quota.acquire("conn-1")
    quota.acquire("conn-2")
    with pytest.raises(QuotaExceeded):
        quota.acquire("conn-3")
    quota.release("conn-1")
    quota.acquire("conn-3")
    assert quota.in_use() == 2


def test_webrtc_adapter_open_close_connection_tracks_quota() -> None:
    quota = ConnectionQuota(limit=1)
    adapter = WebRtcAdapter(TURN, quota=quota)
    adapter.open_connection("pc-1")
    with pytest.raises(QuotaExceeded):
        adapter.open_connection("pc-2")
    adapter.close_connection("pc-1")
    adapter.open_connection("pc-2")


def test_registry_without_webrtc_adapter_reports_unavailable() -> None:
    registry = FleetLiveTransportRegistry((JpegHttpsAdapter(),))
    with pytest.raises(TransportUnavailable):
        registry.select("WEBRTC")
