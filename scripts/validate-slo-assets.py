#!/usr/bin/env python3
"""Validate provisioned SLO, alert, on-call, and dashboard assets."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ALERTS = {
    "CloudCtlControlApiAvailabilityBurn",
    "CloudCtlDeviceHeartbeatStale",
    "CloudCtlEdgeCommandAckSlow",
    "CloudCtlEdgeSpoolGrowing",
    "CloudCtlEvidenceIncomplete",
    "CloudCtlLamdaLockRefreshFailed",
    "CloudCtlTelemetryPipelineDown",
    "CloudCtlUnknownCommitResult",
}


class SloValidationError(RuntimeError):
    """Raised when an operational observability asset is incomplete."""


def _yaml(path: str) -> dict[str, Any]:
    value = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SloValidationError(f"{path} must contain a YAML object")
    return value


def validate_assets() -> dict[str, Any]:
    prometheus = _yaml("infra/otel/prometheus.yml")
    rules = _yaml("infra/otel/slo-rules.yml")
    alertmanager = _yaml("infra/otel/alertmanager.yml")
    oncall_example = _yaml("infra/otel/alertmanager-oncall.example.yml")
    provider = _yaml("infra/otel/grafana-dashboards.yaml")
    compose = _yaml("infra/compose/docker-compose.yml")
    dashboard = json.loads(
        (ROOT / "infra/otel/dashboards/cloudctl-slo.json").read_text(encoding="utf-8")
    )

    alerts = [
        rule
        for group in rules.get("groups", [])
        for rule in group.get("rules", [])
        if "alert" in rule
    ]
    alert_names = {str(alert["alert"]) for alert in alerts}
    missing = REQUIRED_ALERTS - alert_names
    if missing:
        raise SloValidationError(f"required alerts are missing: {sorted(missing)}")
    for alert in alerts:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        if labels.get("severity") not in {"page", "ticket"} or not labels.get("service"):
            raise SloValidationError(f"alert lacks severity/service ownership: {alert['alert']}")
        if not str(annotations.get("runbook", "")).startswith("docs/runbooks/on-call.md#"):
            raise SloValidationError(f"alert lacks a local runbook link: {alert['alert']}")

    targets = prometheus["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"]
    if targets != ["alertmanager:9093"]:
        raise SloValidationError("Prometheus is not routed to Alertmanager")
    if alertmanager["route"]["receiver"] != "local-observation-only":
        raise SloValidationError("local Alertmanager must remain observation-only")
    if oncall_example["route"]["receiver"] != "cloudctl-oncall":
        raise SloValidationError("on-call example route is missing")
    if provider["providers"][0]["options"]["path"] != "/var/lib/grafana/dashboards":
        raise SloValidationError("Grafana dashboard provisioning path is invalid")
    if dashboard.get("uid") != "cloudctl-slo" or len(dashboard.get("panels", [])) < 7:
        raise SloValidationError("CloudCtl SLO dashboard is incomplete")
    services = compose.get("services", {})
    if not {"prometheus", "alertmanager", "grafana"} <= set(services):
        raise SloValidationError("compose does not provision the complete observability stack")

    return {
        "acceptanceStatus": "pending_external",
        "alertCount": len(alerts),
        "alerts": sorted(alert_names),
        "dashboardPanelCount": len(dashboard["panels"]),
        "evidenceClass": "local_configuration_validation",
        "externalOnCallReceiverConfigured": False,
        "generatedAt": datetime.now(UTC).isoformat(),
        "schemaVersion": 1,
        "softwareStatus": "passed",
        "taskId": "P5-004",
        "warning": (
            "Local configuration validation does not prove production metric emission, "
            "external page delivery, acknowledgment, or escalation."
        ),
    }


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.next")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "artifacts" / "tasks" / "P5-004" / "validation-report.json",
    )
    args = parser.parse_args()
    report = validate_assets()
    output = args.report.resolve()
    _atomic_json(output, report)
    print(f"PASS {output}")


if __name__ == "__main__":
    main()
