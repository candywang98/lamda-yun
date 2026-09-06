from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def yaml_document(path: str) -> dict:
    value = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_prometheus_loads_rules_and_routes_alerts_to_alertmanager() -> None:
    prometheus = yaml_document("infra/otel/prometheus.yml")
    compose = yaml_document("infra/compose/docker-compose.yml")

    assert "/etc/prometheus/rules/*.yml" in prometheus["rule_files"]
    targets = prometheus["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"]
    assert targets == ["alertmanager:9093"]
    assert "alertmanager" in compose["services"]
    mounts = compose["services"]["prometheus"]["volumes"]
    assert any("slo-rules.yml" in mount for mount in mounts)


def test_slo_alerts_have_ownership_severity_and_runbooks() -> None:
    rules = yaml_document("infra/otel/slo-rules.yml")
    alerts = [rule for group in rules["groups"] for rule in group["rules"] if "alert" in rule]
    names = {alert["alert"] for alert in alerts}

    assert {
        "CloudCtlControlApiAvailabilityBurn",
        "CloudCtlEdgeCommandAckSlow",
        "CloudCtlDeviceHeartbeatStale",
        "CloudCtlLamdaLockRefreshFailed",
        "CloudCtlUnknownCommitResult",
        "CloudCtlEvidenceIncomplete",
        "CloudCtlEdgeSpoolGrowing",
        "CloudCtlTelemetryPipelineDown",
    } <= names
    for alert in alerts:
        assert alert["labels"]["severity"] in {"page", "ticket"}
        assert alert["labels"]["service"]
        assert alert["annotations"]["runbook"].startswith("docs/runbooks/on-call.md#")


def test_local_alertmanager_is_observation_only_and_example_has_oncall_route() -> None:
    local = yaml_document("infra/otel/alertmanager.yml")
    example = yaml_document("infra/otel/alertmanager-oncall.example.yml")

    assert local["route"]["receiver"] == "local-observation-only"
    local_receiver = next(
        receiver for receiver in local["receivers"] if receiver["name"] == "local-observation-only"
    )
    assert set(local_receiver) == {"name"}
    oncall = next(
        receiver for receiver in example["receivers"] if receiver["name"] == "cloudctl-oncall"
    )
    assert oncall["webhook_configs"][0]["url"].startswith("https://")


def test_grafana_dashboard_is_provisioned_with_slo_panels() -> None:
    provider = yaml_document("infra/otel/grafana-dashboards.yaml")
    compose = yaml_document("infra/compose/docker-compose.yml")
    dashboard = json.loads(
        (ROOT / "infra/otel/dashboards/cloudctl-slo.json").read_text(encoding="utf-8")
    )

    assert provider["providers"][0]["options"]["path"] == "/var/lib/grafana/dashboards"
    mounts = compose["services"]["grafana"]["volumes"]
    assert any("grafana-dashboards.yaml" in mount for mount in mounts)
    assert any("/var/lib/grafana/dashboards" in mount for mount in mounts)
    assert dashboard["uid"] == "cloudctl-slo"
    assert len(dashboard["panels"]) >= 7
    assert all(panel["targets"] for panel in dashboard["panels"])
