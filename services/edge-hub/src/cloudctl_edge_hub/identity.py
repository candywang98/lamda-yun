from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from cryptography import x509
from cryptography.hazmat.primitives import hashes


class IdentityError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class PeerIdentity:
    edge_id: str
    certificate_fingerprint: str


class PeerIdentityVerifier:
    """Maps an authenticated gRPC peer certificate to exactly one edge identity."""

    def __init__(self) -> None:
        self._revoked: set[str] = set()

    def revoke(self, fingerprints: Sequence[str]) -> None:
        self._revoked.update(value.lower() for value in fingerprints)

    def verify(
        self, auth_context: Mapping[str, Iterable[bytes]], claimed_edge_id: str
    ) -> PeerIdentity:
        transport = self._first(auth_context, "transport_security_type")
        if transport != b"ssl":
            raise IdentityError("Edge connection requires mTLS")
        common_name = self._first(auth_context, "x509_common_name").decode("utf-8")
        if not common_name.startswith("edge:"):
            raise IdentityError("certificate subject is not an Edge identity")
        edge_id = common_name.removeprefix("edge:")
        if edge_id != claimed_edge_id:
            raise IdentityError("certificate identity does not match Edge hello")
        pem = self._first(auth_context, "x509_pem_cert")
        try:
            fingerprint = x509.load_pem_x509_certificate(pem).fingerprint(hashes.SHA256()).hex()
        except ValueError as exc:
            raise IdentityError("authenticated peer certificate is malformed") from exc
        if fingerprint.lower() in self._revoked:
            raise IdentityError("certificate is revoked")
        return PeerIdentity(edge_id=edge_id, certificate_fingerprint=fingerprint)

    def verify_control_plane(self, auth_context: Mapping[str, Iterable[bytes]]) -> str:
        """Require a dedicated control-plane certificate for unary admin RPCs."""
        transport = self._first(auth_context, "transport_security_type")
        if transport != b"ssl":
            raise IdentityError("control-plane delivery requires mTLS")
        common_name = self._first(auth_context, "x509_common_name").decode("utf-8")
        if not common_name.startswith("control:"):
            raise IdentityError("certificate subject is not a control-plane identity")
        identity = common_name.removeprefix("control:")
        if not identity:
            raise IdentityError("control-plane identity is empty")
        pem = self._first(auth_context, "x509_pem_cert")
        try:
            fingerprint = x509.load_pem_x509_certificate(pem).fingerprint(hashes.SHA256()).hex()
        except ValueError as exc:
            raise IdentityError("authenticated peer certificate is malformed") from exc
        if fingerprint.lower() in self._revoked:
            raise IdentityError("certificate is revoked")
        return identity

    @staticmethod
    def _first(context: Mapping[str, Iterable[bytes]], key: str) -> bytes:
        values = context.get(key)
        if values is None:
            raise IdentityError(f"missing authenticated peer property: {key}")
        value = next(iter(values), None)
        if value is None:
            raise IdentityError(f"missing authenticated peer property: {key}")
        return value
