"""L10 fleet live transport adapter contracts (live-capabilities/v1, K13).

The adapter layer is deliberately transport-shaped only: session semantics
(state machine, leases, audits, input authorization) live in the control API
(``cloudctl_api.fleet_live``) and are transport independent per K13 §1.
Adapters describe how frames and input events are carried once a session is
established; they never grant or extend authorization on their own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

JPEG_WS = "JPEG_WS"
WEBRTC = "WEBRTC"
VALID_TRANSPORT_KINDS = (JPEG_WS, WEBRTC)

# K13 §1 closed set: legal tier × transport combinations, nothing else.
TIER_TRANSPORT_MATRIX: dict[str, str] = {
    "JPEG_PREVIEW": JPEG_WS,
    "INTERACTIVE_REMOTE": JPEG_WS,
    "WEBRTC": WEBRTC,
}


class TransportError(Exception):
    """Base class for transport selection/prepare failures."""


class TransportUnsupported(TransportError):
    """Tier × transport combination outside the K13 closed set (→ 422)."""


class TransportUnavailable(TransportError):
    """Adapter cannot honestly serve the tier, e.g. WEBRTC without TURN (→ 503).

    Adapters must raise instead of silently downgrading to another transport:
    K13 §8 forbids pretending a WEBRTC session is fine over JPEG.
    """


@dataclass(frozen=True, slots=True)
class TransportPlan:
    """Adapter output attached to a live session at establishment.

    ``turn_required`` mirrors the tier-derived constant; JPEG plans always
    carry ``False`` and never reference TURN servers.
    """

    kind: str
    turn_required: bool
    details: dict[str, Any] = field(default_factory=dict)


class LiveTransportAdapter(Protocol):
    """A transport implementation for fleet live sessions."""

    kind: str

    def supports(self, tier: str) -> bool: ...

    def prepare(
        self, *, session_id: str, device_id: str, tenant_id: str, tier: str
    ) -> TransportPlan: ...
