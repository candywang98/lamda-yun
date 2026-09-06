from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "operational-acceptance.py"


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("operational_acceptance", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_load_probe_reports_thresholds_and_scope() -> None:
    module = load_module()

    report = asyncio.run(module.run_load(24, 4, p95_latency_ms_maximum=5000.0))

    assert report["softwareStatus"] == "passed"
    assert report["acceptanceStatus"] == "blocked_hardware"
    assert report["hardwareEvidence"] is False
    assert report["metrics"]["statusCounts"] == {"200": 24}
    assert report["metrics"]["errorRate"] == 0
    assert report["parameters"] == {"concurrency": 4, "requestCount": 24}
    assert report["thresholds"]["p95LatencyMsMaximum"] == 5000.0


def test_local_chaos_probe_covers_required_fault_classes() -> None:
    module = load_module()

    report = module.run_chaos()

    assert report["softwareStatus"] == "passed"
    assert report["acceptanceStatus"] == "blocked_hardware"
    assert set(report["checks"]) == {
        "networkOutage",
        "edgeRestart",
        "leaseLoss",
        "diskPressure",
    }
    assert {check["status"] for check in report["checks"].values()} == {"passed"}


def test_local_recovery_drill_requires_all_truth_stores_and_detects_corruption() -> None:
    module = load_module()

    report = module.run_recovery_drill()

    assert report["softwareStatus"] == "passed"
    assert report["acceptanceStatus"] == "pending_external"
    assert set(report["artifacts"]) == {"postgresql", "temporal", "objectStore"}
    assert report["checks"]["corruptionDetection"] == "passed"
    assert report["checks"]["restoredDigests"] == "passed"
