from __future__ import annotations

import hashlib
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol


class EnrollmentError(ValueError):
    """A one-time enrollment request could not be accepted."""


class CertificateIssuer(Protocol):
    def issue(
        self, *, edge_id: str, csr_pem: bytes, lifetime: timedelta
    ) -> tuple[bytes, bytes]: ...


@dataclass(frozen=True, slots=True)
class EnrollmentResult:
    edge_id: str
    tenant_id: str
    site_id: str
    certificate_pem: bytes
    certificate_chain_pem: bytes
    expires_at: datetime


@dataclass(slots=True)
class _Enrollment:
    edge_id: str
    tenant_id: str
    site_id: str
    expires_at: datetime
    consumed_at: datetime | None = None


class EnrollmentRegistry:
    """Stores only token digests and consumes a token before certificate issuance."""

    def __init__(
        self, issuer: CertificateIssuer, *, certificate_lifetime: timedelta = timedelta(days=90)
    ):
        self._issuer = issuer
        self._certificate_lifetime = certificate_lifetime
        self._tokens: dict[str, _Enrollment] = {}
        self._lock = threading.Lock()

    def create(
        self,
        *,
        edge_id: str,
        tenant_id: str,
        site_id: str,
        ttl: timedelta = timedelta(minutes=15),
        now: datetime | None = None,
    ) -> str:
        if not edge_id or not tenant_id or not site_id:
            raise EnrollmentError("edge_id, tenant_id and site_id are required")
        issued_at = now or datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        digest = self._digest(token)
        with self._lock:
            self._tokens[digest] = _Enrollment(
                edge_id=edge_id,
                tenant_id=tenant_id,
                site_id=site_id,
                expires_at=issued_at + ttl,
            )
        return token

    def exchange(
        self,
        *,
        token: str,
        csr_pem: bytes,
        now: datetime | None = None,
    ) -> EnrollmentResult:
        if not csr_pem.startswith(b"-----BEGIN CERTIFICATE REQUEST-----"):
            raise EnrollmentError("a PEM encoded PKCS#10 CSR is required")
        exchanged_at = now or datetime.now(UTC)
        digest = self._digest(token)
        with self._lock:
            enrollment = self._tokens.get(digest)
            if enrollment is None:
                raise EnrollmentError("invalid enrollment token")
            if enrollment.consumed_at is not None:
                raise EnrollmentError("enrollment token was already consumed")
            if enrollment.expires_at <= exchanged_at:
                raise EnrollmentError("enrollment token expired")
            enrollment.consumed_at = exchanged_at

        try:
            certificate, chain = self._issuer.issue(
                edge_id=enrollment.edge_id,
                csr_pem=csr_pem,
                lifetime=self._certificate_lifetime,
            )
        except Exception:
            # Consumption is intentionally not rolled back. A failed exchange needs a new token.
            raise
        return EnrollmentResult(
            edge_id=enrollment.edge_id,
            tenant_id=enrollment.tenant_id,
            site_id=enrollment.site_id,
            certificate_pem=certificate,
            certificate_chain_pem=chain,
            expires_at=exchanged_at + self._certificate_lifetime,
        )

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
