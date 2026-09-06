from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate-slo-assets.py"


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_slo_assets", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validator_reports_local_only_operational_assets() -> None:
    report = load_module().validate_assets()

    assert report["softwareStatus"] == "passed"
    assert report["acceptanceStatus"] == "pending_external"
    assert report["externalOnCallReceiverConfigured"] is False
    assert report["alertCount"] >= 8
    assert report["dashboardPanelCount"] >= 7
