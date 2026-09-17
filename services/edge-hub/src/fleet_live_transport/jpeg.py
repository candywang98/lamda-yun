"""JPEG-over-HTTPS/WS transport adapter (default; no TURN dependency).

Carries the slice1 (p10-live/20260913.1) WS JSON signaling shape
``{t:"frame"|"state"|"hello"|"input"}`` over the existing pinned HTTPS
channel. Serves ``JPEG_PREVIEW`` and ``INTERACTIVE_REMOTE`` only; per K13 §7
the WEBRTC tier must not ride this adapter silently.
"""

from __future__ import annotations

from fleet_live_transport.base import (
    JPEG_WS,
    TransportPlan,
    TransportUnsupported,
)

# GATE_JPEG_TRANSPORT constants (K13 §8): <=5 fps, long edge <=720, JPEG
# quality <=60; pure viewing may degrade to <=1 fps.
JPEG_FPS_CAP = 5
JPEG_IDLE_FPS_CAP = 1
JPEG_LONG_EDGE_CAP = 720
JPEG_QUALITY_CAP = 60


class JpegHttpsAdapter:
    """Default adapter; works with zero TURN configuration."""

    kind = JPEG_WS

    def supports(self, tier: str) -> bool:
        return tier in {"JPEG_PREVIEW", "INTERACTIVE_REMOTE"}

    def prepare(
        self, *, session_id: str, device_id: str, tenant_id: str, tier: str
    ) -> TransportPlan:
        if not self.supports(tier):
            # Closed-set violation; the registry maps this to 422 upstream.
            raise TransportUnsupported(f"{tier} cannot ride the JPEG transport")
        return TransportPlan(
            kind=JPEG_WS,
            turn_required=False,
            details={
                # Slice1-compatible operator stream endpoint (frames down,
                # input up once the session is REMOTE).
                "operatorStreamPath": f"/api/v1/devices/{device_id}/live/{session_id}/stream",
                "signaling": ["frame", "state", "hello", "input"],
                "caps": {
                    "fps": JPEG_FPS_CAP,
                    "idleFps": JPEG_IDLE_FPS_CAP,
                    "longEdge": JPEG_LONG_EDGE_CAP,
                    "quality": JPEG_QUALITY_CAP,
                },
                "tenantId": tenant_id,
            },
        )
