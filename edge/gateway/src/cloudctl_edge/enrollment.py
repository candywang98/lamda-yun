from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509 import CertificateSigningRequestBuilder, Name, NameAttribute
from cryptography.x509.oid import NameOID

from .cert_store import CertificateStore, EdgeCredentials


@dataclass(frozen=True, slots=True)
class EnrollmentResponse:
    certificate_pem: bytes
    certificate_chain_pem: bytes


class EnrollmentClient(Protocol):
    async def exchange(self, *, token: str, csr_pem: bytes) -> EnrollmentResponse: ...


class EdgeEnroller:
    def __init__(self, edge_id: str, store: CertificateStore, client: EnrollmentClient):
        self._edge_id = edge_id
        self._store = store
        self._client = client

    async def enroll(self, token: str) -> EdgeCredentials:
        private_key = ec.generate_private_key(ec.SECP256R1())
        csr = (
            CertificateSigningRequestBuilder()
            .subject_name(Name([NameAttribute(NameOID.COMMON_NAME, f"edge:{self._edge_id}")]))
            .sign(private_key, hashes.SHA256())
        )
        key_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        response = await self._client.exchange(
            token=token, csr_pem=csr.public_bytes(serialization.Encoding.PEM)
        )
        credentials = EdgeCredentials(
            certificate=response.certificate_pem,
            private_key=key_pem,
            certificate_chain=response.certificate_chain_pem,
        )
        self._store.write(credentials)
        return credentials
