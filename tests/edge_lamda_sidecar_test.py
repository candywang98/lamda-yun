from __future__ import annotations

import hashlib
import json
import sys
from io import StringIO
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "packages/lamda-driver/src"))

from cloudctl_lamda_driver.errors import DeviceDriverError, DriverErrorCode
from cloudctl_lamda_driver.session import LamdaSession
from cloudctl_lamda_driver.sidecar import (
    SIDECAR_PROTOCOL_VERSION,
    _decode_response,
    _read_runtime_info,
    build_sidecar_command,
)
from cloudctl_lamda_driver.sidecar_server import run_server


class FakeElement:
    def exists(self) -> bool:
        return True

    def text(self) -> str:
        return "ready"

    def click(self) -> None:
        return None


class FakeBackend:
    def __init__(self) -> None:
        self.closed = 0
        self.pushed: list[tuple[bytes, str, str]] = []

    def close(self) -> None:
        self.closed += 1

    def capabilities(self) -> dict[str, object]:
        return {"ui_automation": True, "screenshot": True}

    def identity(self) -> str:
        return "device-a"

    def select(self, _attributes: object, _timeout_seconds: float) -> FakeElement:
        return FakeElement()

    def push_file(self, source: object, remote_path: str, sha256: str) -> None:
        self.pushed.append((source.read(), remote_path, sha256))  # type: ignore[attr-defined]


def _serve(requests: list[dict[str, object]], factory: object) -> list[dict[str, object]]:
    source = StringIO("".join(json.dumps(request) + "\n" for request in requests))
    destination = StringIO()
    run_server(source, destination, backend_factory=factory, sdk_version="10.8")  # type: ignore[arg-type]
    return [json.loads(line) for line in destination.getvalue().splitlines()]


def test_sidecar_reports_protocol_python_and_lamda_versions() -> None:
    responses = _serve(
        [
            {"id": 1, "op": "hello", "args": {}},
            {"id": 2, "op": "close", "args": {}},
        ],
        lambda **_kwargs: FakeBackend(),
    )
    result = responses[0]["result"]
    assert result["protocolVersion"] == SIDECAR_PROTOCOL_VERSION
    assert result["sdkVersion"] == "10.8"
    assert result["pythonVersion"] == sys.version.split()[0]


def test_sidecar_maps_connection_failures_to_stable_driver_error(tmp_path: Path) -> None:
    certificate = tmp_path / "device.pem"
    certificate.write_text("fixture", encoding="utf-8")
    artifact_root = tmp_path / "objects"
    artifact_root.mkdir()

    def fail(**_kwargs: object) -> FakeBackend:
        raise ConnectionError("private endpoint detail")

    response = _serve(
        [
            {
                "id": 7,
                "op": "connect",
                "args": {
                    "host": "10.0.0.20",
                    "port": 65000,
                    "certificatePath": str(certificate),
                    "artifactRoot": str(artifact_root),
                },
            }
        ],
        fail,
    )[0]
    assert response["error"] == {
        "code": DriverErrorCode.CONNECTION_FAILED.value,
        "detail": "device connection failed",
        "retryable": True,
        "reconcileRequired": False,
    }
    assert "private endpoint" not in json.dumps(response)


def test_sidecar_rejects_missing_certificate_before_backend_start(tmp_path: Path) -> None:
    started = False
    artifact_root = tmp_path / "objects"
    artifact_root.mkdir()

    def factory(**_kwargs: object) -> FakeBackend:
        nonlocal started
        started = True
        return FakeBackend()

    response = _serve(
        [
            {
                "id": 8,
                "op": "connect",
                "args": {
                    "host": "10.0.0.20",
                    "port": 65000,
                    "certificatePath": str(tmp_path / "missing.pem"),
                    "artifactRoot": str(artifact_root),
                },
            }
        ],
        factory,
    )[0]
    assert response["error"]["code"] == DriverErrorCode.CERTIFICATE_REJECTED.value
    assert started is False


def test_sidecar_allows_only_explicit_operations(tmp_path: Path) -> None:
    certificate = tmp_path / "device.pem"
    certificate.write_text("fixture", encoding="utf-8")
    artifact_root = tmp_path / "objects"
    artifact_root.mkdir()
    responses = _serve(
        [
            {
                "id": 1,
                "op": "connect",
                "args": {
                    "host": "10.0.0.20",
                    "port": 65000,
                    "certificatePath": str(certificate),
                    "artifactRoot": str(artifact_root),
                },
            },
            {"id": 2, "op": "shell", "args": {"backendHandle": 0}},
            {"id": 3, "op": "close", "args": {}},
        ],
        lambda **_kwargs: FakeBackend(),
    )
    assert responses[0]["result"] == {"backendHandle": 0}
    assert responses[1]["error"]["code"] == DriverErrorCode.CAPABILITY_DENIED.value


def test_client_decodes_remote_error_without_sdk_exception_detail() -> None:
    response = json.dumps(
        {
            "id": 4,
            "ok": False,
            "error": {
                "code": DriverErrorCode.LOCK_LOST.value,
                "detail": "LAMDA API lock refresh failed",
                "retryable": False,
                "reconcileRequired": False,
            },
        }
    )
    with pytest.raises(DeviceDriverError) as captured:
        _decode_response(response, 4)
    assert captured.value.code is DriverErrorCode.LOCK_LOST
    assert captured.value.retryable is False


@pytest.mark.parametrize(
    ("sdk_version", "python_version", "message"),
    [
        ("10.7", "3.12.14", "SDK version"),
        ("10.8", "3.14.4", "Python 3.12"),
    ],
)
def test_client_rejects_sidecar_runtime_version_skew(
    sdk_version: str, python_version: str, message: str
) -> None:
    with pytest.raises(DeviceDriverError, match=message):
        _read_runtime_info(
            {
                "protocolVersion": SIDECAR_PROTOCOL_VERSION,
                "sdkVersion": sdk_version,
                "pythonVersion": python_version,
            }
        )


def test_sidecar_reads_only_verified_content_addressed_artifacts(tmp_path: Path) -> None:
    certificate = tmp_path / "device.pem"
    certificate.write_text("fixture", encoding="utf-8")
    payload = b"approved-media"
    digest = hashlib.sha256(payload).hexdigest()
    artifact_root = tmp_path / "objects"
    artifact = artifact_root / digest[:2] / digest
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(payload)
    backend = FakeBackend()
    responses = _serve(
        [
            {
                "id": 1,
                "op": "connect",
                "args": {
                    "host": "10.0.0.20",
                    "port": 65000,
                    "certificatePath": str(certificate),
                    "artifactRoot": str(artifact_root),
                },
            },
            {
                "id": 2,
                "op": "push_file",
                "args": {
                    "backendHandle": 0,
                    "sha256": digest,
                    "size": len(payload),
                    "remotePath": "/sdcard/approved-media.bin",
                },
            },
            {"id": 3, "op": "close", "args": {}},
        ],
        lambda **_kwargs: backend,
    )
    assert responses[1]["ok"] is True
    assert backend.pushed == [(payload, "/sdcard/approved-media.bin", digest)]


def test_certificate_path_is_not_exposed_in_sidecar_process_arguments(tmp_path: Path) -> None:
    python = (tmp_path / "python").resolve()
    certificate = (tmp_path / "private" / "device.pem").resolve()
    command = build_sidecar_command(python)
    assert str(certificate) not in command
    assert command == [str(python), "-s", "-m", "cloudctl_lamda_driver.sidecar_server"]


def test_stale_fence_prevents_sidecar_backend_start(tmp_path: Path) -> None:
    certificate = tmp_path / "device.pem"
    certificate.write_text("fixture", encoding="utf-8")
    started = False

    class StaleFence:
        def verify(self, **_kwargs: object) -> None:
            raise LookupError("stale")

    def factory(**_kwargs: object) -> FakeBackend:
        nonlocal started
        started = True
        return FakeBackend()

    session = LamdaSession(
        device_id="device-a",
        host="10.0.0.20",
        certificate_path=certificate,
        lease_id="lease-a",
        fencing_token=7,
        fencing_verifier=StaleFence(),
        backend_factory=factory,
    )
    with pytest.raises(DeviceDriverError) as captured:
        session.__enter__()
    assert captured.value.code is DriverErrorCode.STALE_FENCE
    assert started is False
