"""Fleet live transport registry (L10, live-capabilities/v1).

Selects the explicit transport adapter for a session at establishment time:
tier × transport must be inside the K13 §1 closed set; the JPEG tiers never
require TURN, the WEBRTC tier refuses to establish without TURN configuration
(no silent downgrade — callers map that to 503 LIVE_TURN_UNAVAILABLE).
"""

from __future__ import annotations

from fleet_live_transport.base import (
    JPEG_WS,
    TIER_TRANSPORT_MATRIX,
    VALID_TRANSPORT_KINDS,  # noqa: F401 - re-exported for callers
    WEBRTC,
    TransportError,
    TransportPlan,
    TransportUnavailable,
    TransportUnsupported,
)
from fleet_live_transport.jpeg import JpegHttpsAdapter
from fleet_live_transport.webrtc import (
    ConnectionQuota,
    QuotaExceeded,
    TurnConfig,
    TurnConfigError,
    TurnCredentials,
    WebRtcAdapter,
    mint_turn_credentials,
    validate_ice_candidate,
    validate_sdp,
    validate_sdp_exchange,
    validate_turn_credentials,
)

__all__ = [
    "JPEG_WS",
    "WEBRTC",
    "VALID_TRANSPORT_KINDS",
    "TIER_TRANSPORT_MATRIX",
    "ConnectionQuota",
    "FleetLiveTransportRegistry",
    "JpegHttpsAdapter",
    "QuotaExceeded",
    "TransportError",
    "TransportPlan",
    "TransportUnavailable",
    "TransportUnsupported",
    "TurnConfig",
    "TurnConfigError",
    "TurnCredentials",
    "WebRtcAdapter",
    "default_registry",
    "mint_turn_credentials",
    "validate_ice_candidate",
    "validate_sdp",
    "validate_sdp_exchange",
    "validate_turn_credentials",
]


class FleetLiveTransportRegistry:
    """Explicit per-tier adapter selection with closed-set enforcement."""

    def __init__(self, adapters: tuple[JpegHttpsAdapter | WebRtcAdapter, ...]) -> None:
        self._adapters = {adapter.kind: adapter for adapter in adapters}

    def adapters(self) -> tuple[JpegHttpsAdapter | WebRtcAdapter, ...]:
        return tuple(self._adapters.values())

    def select(
        self, tier: str, transport: str | None = None
    ) -> JpegHttpsAdapter | WebRtcAdapter:
        expected = TIER_TRANSPORT_MATRIX.get(tier)
        if expected is None:
            raise TransportUnsupported(f"unknown live tier: {tier!r}")
        if transport is not None and transport != expected:
            raise TransportUnsupported(
                f"tier {tier} only rides {expected}, refusing {transport}"
            )
        adapter = self._adapters.get(expected)
        if adapter is None:
            raise TransportUnavailable(f"no adapter registered for {expected}")
        return adapter


def default_registry(
    turn_config: TurnConfig | None = None,
    quota: ConnectionQuota | None = None,
) -> FleetLiveTransportRegistry:
    """JPEG default + WebRTC (TURN-gated) adapters."""
    return FleetLiveTransportRegistry(
        (JpegHttpsAdapter(), WebRtcAdapter(turn_config, quota=quota))
    )
