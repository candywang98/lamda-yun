from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "edge/gateway/src"))

from cloudctl_edge.__main__ import main
from cloudctl_edge.settings import GatewaySettings, SettingsError


def test_cli_check_is_network_free(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--check"]) == 0
    assert '"status": "ok"' in capsys.readouterr().out


def test_production_settings_require_companion_tls(tmp_path: Path) -> None:
    settings = GatewaySettings(
        edge_id="edge-a",
        hub_endpoint="https://hub.example:443",
        state_dir=tmp_path / "state",
        artifact_staging_root=tmp_path / "artifacts",
        edge_credentials_dir=tmp_path / "credentials",
        companion_tls_certificate=tmp_path / "missing.crt",
        companion_tls_private_key=tmp_path / "missing.key",
        companion_bind_host="127.0.0.1",
        companion_bind_port=8443,
        device_profiles_path=tmp_path / "devices.json",
        enrollment_path=tmp_path / "enrollment.json",
    )
    with pytest.raises(SettingsError, match="Companion TLS"):
        settings.validate_runtime()


def test_production_settings_require_isolated_lamda_runtime(tmp_path: Path) -> None:
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    for name in ("edge.crt", "edge.key", "ca.crt"):
        (credentials / name).write_text("fixture", encoding="utf-8")
    companion_certificate = tmp_path / "companion.crt"
    companion_key = tmp_path / "companion.key"
    profiles = tmp_path / "devices.json"
    enrollment = tmp_path / "enrollment.json"
    for path in (companion_certificate, companion_key, profiles, enrollment):
        path.write_text("fixture", encoding="utf-8")
    settings = GatewaySettings(
        edge_id="edge-a",
        hub_endpoint="https://hub.example:443",
        state_dir=tmp_path / "state",
        artifact_staging_root=tmp_path / "artifacts",
        edge_credentials_dir=credentials,
        companion_tls_certificate=companion_certificate,
        companion_tls_private_key=companion_key,
        companion_bind_host="127.0.0.1",
        companion_bind_port=8443,
        device_profiles_path=profiles,
        enrollment_path=enrollment,
    )
    with pytest.raises(SettingsError, match="sidecar Python"):
        settings.validate_runtime()
