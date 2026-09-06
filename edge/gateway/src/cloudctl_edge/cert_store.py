from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization


@dataclass(frozen=True, slots=True)
class EdgeCredentials:
    certificate: bytes
    private_key: bytes
    certificate_chain: bytes


class CertificateStore:
    def __init__(self, root: Path):
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self._root, 0o700)

    def write(self, credentials: EdgeCredentials) -> None:
        self._validate(credentials)
        self._atomic_write("edge.crt", credentials.certificate)
        self._atomic_write("edge.key", credentials.private_key)
        self._atomic_write("ca.crt", credentials.certificate_chain)

    def read(self) -> EdgeCredentials:
        return EdgeCredentials(
            certificate=(self._root / "edge.crt").read_bytes(),
            private_key=(self._root / "edge.key").read_bytes(),
            certificate_chain=(self._root / "ca.crt").read_bytes(),
        )

    def _atomic_write(self, name: str, payload: bytes) -> None:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}-", dir=self._root)
        try:
            with os.fdopen(descriptor, "wb") as destination:
                destination.write(payload)
                destination.flush()
                os.fsync(destination.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self._root / name)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    @staticmethod
    def _validate(credentials: EdgeCredentials) -> None:
        try:
            certificate = x509.load_pem_x509_certificate(credentials.certificate)
            private_key = serialization.load_pem_private_key(credentials.private_key, password=None)
            x509.load_pem_x509_certificate(credentials.certificate_chain)
        except (TypeError, ValueError) as exc:
            raise ValueError("Edge credentials must contain valid PEM material") from exc
        certificate_public = certificate.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        private_public = private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        if certificate_public != private_public:
            raise ValueError("Edge certificate does not match the private key")
