"""WebRTC transport adapter (tier WEBRTC only; requires deployed TURN).

Honesty boundary (L10 task card): this adapter implements the configuration
model, short-lived TURN credential minting/validation (coturn REST style),
SDP offer/answer + ICE candidate exchange *shape* validation, and connection
quota accounting. Real ICE/TURN connectivity is NOT exercised locally — it
is an explicit deploy-verification seam (NOT_TESTED_LOCALLY).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from fleet_live_transport.base import (
    WEBRTC,
    TransportError,
    TransportPlan,
    TransportUnavailable,
    TransportUnsupported,
)

TTL_MIN_SECONDS = 300
TTL_MAX_SECONDS = 3600
_ICE_URL_PATTERN = re.compile(r"^(stun|turn|turns):\S+$")
_SDP_TYPES = {"offer", "answer", "pranswer", "rollback"}


class TurnConfigError(ValueError):
    """Invalid TURN deployment configuration (GATE_TURN_DEPLOY)."""


@dataclass(frozen=True, slots=True)
class TurnConfig:
    """GATE_TURN_DEPLOY + GATE_BANDWIDTH_BUDGET inputs (K13 §8).

    ``shared_secret`` is the coturn `static-auth-secret`; credentials are
    minted per session with a bounded lifetime (<= 1h, >= 5min).
    """

    ice_servers: tuple[str, ...]
    shared_secret: str
    credential_ttl_seconds: int = TTL_MAX_SECONDS
    transport_policy: str = "all"
    connection_quota: int = 2

    def __post_init__(self) -> None:
        if not self.ice_servers or not all(
            _ICE_URL_PATTERN.match(url) for url in self.ice_servers
        ):
            raise TurnConfigError(
                "at least one stun:/turn:/turns: ICE server URL is required"
            )
        if not self.shared_secret:
            raise TurnConfigError("TURN shared secret must not be empty")
        if not TTL_MIN_SECONDS <= self.credential_ttl_seconds <= TTL_MAX_SECONDS:
            raise TurnConfigError(
                f"credential TTL must be within [{TTL_MIN_SECONDS}, {TTL_MAX_SECONDS}] seconds"
            )
        if self.transport_policy not in {"all", "relay"}:
            raise TurnConfigError("transport policy must be 'all' or 'relay'")
        if self.connection_quota < 1:
            raise TurnConfigError("connection quota must be >= 1")

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> TurnConfig | None:
        """Build from ``CLOUDCTL_LIVE_TURN_*`` variables; None when unconfigured."""
        servers = tuple(
            url.strip()
            for url in (environ.get("CLOUDCTL_LIVE_TURN_ICE_SERVERS") or "").split(",")
            if url.strip()
        )
        secret = environ.get("CLOUDCTL_LIVE_TURN_SHARED_SECRET") or ""
        if not servers or not secret:
            return None
        ttl_raw = environ.get("CLOUDCTL_LIVE_TURN_CREDENTIAL_TTL_SECONDS") or ""
        quota_raw = environ.get("CLOUDCTL_LIVE_TURN_CONNECTION_QUOTA") or ""
        return cls(
            ice_servers=servers,
            shared_secret=secret,
            credential_ttl_seconds=int(ttl_raw) if ttl_raw else TTL_MAX_SECONDS,
            transport_policy=environ.get("CLOUDCTL_LIVE_TURN_TRANSPORT_POLICY") or "all",
            connection_quota=int(quota_raw) if quota_raw else 2,
        )


@dataclass(frozen=True, slots=True)
class TurnCredentials:
    username: str
    password: str
    expires_at_unix: int


def mint_turn_credentials(
    config: TurnConfig, *, session_id: str, now_unix: int | None = None
) -> TurnCredentials:
    """Mint short-lived coturn REST-style credentials for one session.

    username = "<expiry-unix>:<session-scoped-id>"; password =
    base64(HMAC-SHA1(shared_secret, username)). coturn validates exactly this
    pair, so expiry is enforced by the TURN deployment itself.
    """
    now = int(time.time()) if now_unix is None else now_unix
    expires_at = now + config.credential_ttl_seconds
    username = f"{expires_at}:live-{session_id[:32]}"
    digest = hmac.new(
        config.shared_secret.encode("utf-8"), username.encode("utf-8"), hashlib.sha1
    ).digest()
    return TurnCredentials(
        username=username, password=base64.b64encode(digest).decode("ascii"),
        expires_at_unix=expires_at,
    )


def validate_turn_credentials(
    config: TurnConfig, username: str, password: str, *, now_unix: int | None = None
) -> bool:
    """True when the credential pair is well-formed, signed, and unexpired."""
    now = int(time.time()) if now_unix is None else now_unix
    expiry_text, _, _ = username.partition(":")
    if not expiry_text.isdigit():
        return False
    if int(expiry_text) <= now:
        return False
    digest = hmac.new(
        config.shared_secret.encode("utf-8"), username.encode("utf-8"), hashlib.sha1
    ).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, password)


class QuotaExceeded(TransportError):
    """GATE_BANDWIDTH_BUDGET: connection quota for the scope is exhausted."""


@dataclass
class ConnectionQuota:
    """Bounded connection accounting per quota scope (e.g. one tenant)."""

    limit: int
    _active: set[str] = field(default_factory=set)

    def acquire(self, connection_id: str) -> None:
        if connection_id in self._active:
            return
        if len(self._active) >= self.limit:
            raise QuotaExceeded(
                f"WebRTC connection quota exhausted ({len(self._active)}/{self.limit})"
            )
        self._active.add(connection_id)

    def release(self, connection_id: str) -> None:
        self._active.discard(connection_id)

    def in_use(self) -> int:
        return len(self._active)


def validate_sdp(description: Mapping[str, Any], *, expected_type: str | None = None) -> None:
    """Shape-check one SDP description (offer/answer/pranswer/rollback)."""
    if not isinstance(description, Mapping):
        raise TransportError("SDP description must be an object")
    sdp_type = description.get("type")
    if sdp_type not in _SDP_TYPES:
        raise TransportError(f"SDP type must be one of {sorted(_SDP_TYPES)}")
    if expected_type is not None and sdp_type != expected_type:
        raise TransportError(f"expected SDP type {expected_type}, got {sdp_type}")
    sdp = description.get("sdp")
    if not isinstance(sdp, str) or not sdp.lstrip().startswith("v=0"):
        raise TransportError("SDP body must be a string starting with 'v=0'")


def validate_sdp_exchange(offer: Mapping[str, Any], answer: Mapping[str, Any]) -> None:
    """Shape-check an offer/answer pair exchanged through the signaling path."""
    validate_sdp(offer, expected_type="offer")
    validate_sdp(answer, expected_type="answer")
    offer_id = offer.get("sessionId")
    answer_id = answer.get("sessionId")
    if isinstance(offer_id, str) and isinstance(answer_id, str) and offer_id != answer_id:
        raise TransportError("offer and answer belong to different SDP sessions")


def validate_ice_candidate(candidate: Mapping[str, Any]) -> None:
    """Shape-check one ICE candidate trickle message."""
    if not isinstance(candidate, Mapping):
        raise TransportError("ICE candidate must be an object")
    text = candidate.get("candidate")
    if not isinstance(text, str) or not text.startswith("candidate:"):
        raise TransportError("ICE candidate line must start with 'candidate:'")
    mid = candidate.get("sdpMid")
    line_index = candidate.get("sdpMLineIndex")
    if mid is not None and not isinstance(mid, str):
        raise TransportError("sdpMid must be a string when present")
    if not isinstance(line_index, int) or line_index < 0:
        raise TransportError("sdpMLineIndex must be a non-negative integer")


class WebRtcAdapter:
    """Production-tier adapter; refuses to run without TURN configuration."""

    kind = WEBRTC

    def __init__(
        self,
        turn_config: TurnConfig | None = None,
        *,
        quota: ConnectionQuota | None = None,
    ) -> None:
        self._turn_config = turn_config
        self._quota = quota

    @property
    def turn_config(self) -> TurnConfig | None:
        return self._turn_config

    def supports(self, tier: str) -> bool:
        return tier == "WEBRTC"

    def prepare(
        self, *, session_id: str, device_id: str, tenant_id: str, tier: str
    ) -> TransportPlan:
        if not self.supports(tier):
            raise TransportUnsupported(f"{tier} cannot ride the WebRTC transport")
        config = self._turn_config
        if config is None:
            # K13 §8: refuse rather than silently downgrade to JPEG.
            raise TransportUnavailable(
                "WEBRTC tier requires deployed TURN (GATE_TURN_DEPLOY unsatisfied)"
            )
        credentials = mint_turn_credentials(config, session_id=session_id)
        return TransportPlan(
            kind=WEBRTC,
            turn_required=True,
            details={
                "iceServers": [
                    {"urls": list(config.ice_servers), "username": credentials.username,
                     "credential": credentials.password}
                ],
                "transportPolicy": config.transport_policy,
                "connectionQuota": config.connection_quota,
                "credentialTtlSeconds": config.credential_ttl_seconds,
                "credentialExpiresAtUnix": credentials.expires_at_unix,
                "tenantId": tenant_id,
            },
        )

    def open_connection(self, connection_id: str) -> None:
        """Account one WebRTC connection against the bandwidth-budget quota."""
        if self._quota is None:
            return
        self._quota.acquire(connection_id)

    def close_connection(self, connection_id: str) -> None:
        if self._quota is not None:
            self._quota.release(connection_id)
