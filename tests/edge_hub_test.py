from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
for source in ("packages/edge-protocol/src", "services/edge-hub/src"):
    sys.path.insert(0, str(ROOT / source))

from cloudctl_edge_hub.ca import LocalCertificateAuthority
from cloudctl_edge_hub.enrollment import EnrollmentError, EnrollmentRegistry
from cloudctl_edge_hub.identity import IdentityError, PeerIdentityVerifier
from cloudctl_edge_hub.session import EdgeHub, InMemoryHubStore, SessionError
from cloudctl_edge_protocol import edge_control_pb2 as pb


class FakeIssuer:
    def issue(self, *, edge_id: str, csr_pem: bytes, lifetime: timedelta) -> tuple[bytes, bytes]:
        assert edge_id == "edge-a"
        assert csr_pem.startswith(b"-----BEGIN CERTIFICATE REQUEST-----")
        return b"certificate", b"chain"


def test_enrollment_token_is_digest_only_and_one_time() -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    registry = EnrollmentRegistry(FakeIssuer())
    token = registry.create(edge_id="edge-a", tenant_id="tenant-a", site_id="site-a", now=now)
    result = registry.exchange(
        token=token,
        csr_pem=b"-----BEGIN CERTIFICATE REQUEST-----\nfixture",
        now=now + timedelta(seconds=1),
    )
    assert result.edge_id == "edge-a"
    assert token not in registry._tokens
    with pytest.raises(EnrollmentError, match="already consumed"):
        registry.exchange(
            token=token,
            csr_pem=b"-----BEGIN CERTIFICATE REQUEST-----\nfixture",
            now=now + timedelta(seconds=2),
        )


def test_peer_identity_requires_mtls_and_matching_edge() -> None:
    verifier = PeerIdentityVerifier()
    certificate = LocalCertificateAuthority.create().certificate_pem()
    context = {
        "transport_security_type": [b"ssl"],
        "x509_common_name": [b"edge:edge-a"],
        "x509_pem_cert": [certificate],
    }
    identity = verifier.verify(context, "edge-a")
    assert identity.edge_id == "edge-a"
    verifier.revoke([identity.certificate_fingerprint])
    with pytest.raises(IdentityError, match="revoked"):
        verifier.verify(context, "edge-a")


def test_control_plane_identity_rejects_edge_certificate() -> None:
    verifier = PeerIdentityVerifier()
    certificate = LocalCertificateAuthority.create().certificate_pem()
    control_context = {
        "transport_security_type": [b"ssl"],
        "x509_common_name": [b"control:outbox"],
        "x509_pem_cert": [certificate],
    }
    assert verifier.verify_control_plane(control_context) == "outbox"
    edge_context = {**control_context, "x509_common_name": [b"edge:edge-a"]}
    with pytest.raises(IdentityError, match="control-plane"):
        verifier.verify_control_plane(edge_context)


@pytest.mark.asyncio
async def test_hub_replays_cloud_gap_and_rejects_edge_sequence_gap() -> None:
    store = InMemoryHubStore()
    hub = EdgeHub(store)
    first = await hub.queue(
        "edge-a",
        pb.CloudToEdge(cancel=pb.CancelCommand(command_id="cmd-1", reason="operator")),
    )
    second = await hub.queue(
        "edge-a",
        pb.CloudToEdge(cancel=pb.CancelCommand(command_id="cmd-2", reason="operator")),
    )
    assert (first.sequence, second.sequence) == (1, 2)
    stream = hub.open("edge-a", last_cloud_sequence_acked=1)
    hello = await anext(stream)
    replay = await anext(stream)
    await stream.aclose()
    assert hello.sequence == 0
    assert replay.sequence == 2

    with pytest.raises(SessionError, match="expected 1"):
        await hub.accept(
            "edge-a",
            pb.EdgeToCloud(
                sequence=2,
                command_ack=pb.CommandAck(command_id="cmd", state="RECEIVED"),
            ),
        )
