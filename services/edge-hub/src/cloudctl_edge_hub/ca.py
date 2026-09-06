from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .enrollment import EnrollmentError


class LocalCertificateAuthority:
    """Small CA adapter suitable for tests or a protected Edge Hub deployment."""

    def __init__(self, certificate: x509.Certificate, private_key: ec.EllipticCurvePrivateKey):
        self._certificate = certificate
        self._private_key = private_key

    @classmethod
    def create(cls, common_name: str = "CloudCtl Edge CA") -> LocalCertificateAuthority:
        now = datetime.now(UTC)
        private_key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=False,
                    key_cert_sign=True,
                    key_agreement=False,
                    content_commitment=False,
                    data_encipherment=False,
                    encipher_only=False,
                    decipher_only=False,
                    crl_sign=True,
                ),
                critical=True,
            )
            .sign(private_key, hashes.SHA256())
        )
        return cls(certificate, private_key)

    def issue(self, *, edge_id: str, csr_pem: bytes, lifetime: timedelta) -> tuple[bytes, bytes]:
        try:
            csr = x509.load_pem_x509_csr(csr_pem)
        except ValueError as exc:
            raise EnrollmentError("invalid PKCS#10 CSR") from exc
        if not csr.is_signature_valid:
            raise EnrollmentError("CSR signature is invalid")
        common_names = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if len(common_names) != 1 or common_names[0].value != f"edge:{edge_id}":
            raise EnrollmentError("CSR subject does not match enrollment identity")
        if lifetime <= timedelta(0) or lifetime > timedelta(days=90):
            raise EnrollmentError("Edge certificate lifetime must be between 1 second and 90 days")
        now = datetime.now(UTC)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(self._certificate.subject)
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + lifetime)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=True)
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.UniformResourceIdentifier(f"spiffe://cloudctl/edge/{edge_id}")]
                ),
                critical=False,
            )
            .sign(self._private_key, hashes.SHA256())
        )
        return (
            certificate.public_bytes(serialization.Encoding.PEM),
            self._certificate.public_bytes(serialization.Encoding.PEM),
        )

    def certificate_pem(self) -> bytes:
        return self._certificate.public_bytes(serialization.Encoding.PEM)

    def private_key_pem(self) -> bytes:
        return self._private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
