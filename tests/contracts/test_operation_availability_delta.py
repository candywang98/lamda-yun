"""X12 contract tests: the 31-action four-state availability ledger.

Task card (fleet-first-20260916.1 / X12) acceptance:
- every xy-tasks-01..31 action has exactly one ledger state
  (ENABLED / PENDING / POLICY_BLOCKED / OUT_OF_SCOPE) with task + P-package
  references — no "everything lit" completion;
- docs/current/operation-availability.json is the machine-readable twin of
  cloudctl_api.operation_catalog.XY_AVAILABILITY_LEDGER (entry parity);
- the sensitive category (coin spend / promotion / review / message
  deletion) lists budget cap, target authorization, and pinned-version
  platform entry evidence, and none of it is ENABLED;
- SKU / auction / 会玩 / extra platforms each carry an
  accept / keep_blocked / scope_change adjudication record;
- the PENDING → ENABLED transition path exists but stays disabled by
  default (evidence AND a deployed executor are both required; policy and
  scope rows are terminal);
- drift is rejected: unknown operation names, renamed/aliased disabled
  operations, commandType swaps, parameter/target/budget drift all fail
  closed with 4xx (or ValueError at the mint lane).
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.command_factory import (
    PRODUCTION_ALIASES,
    mint_operation_command,
    production_command_type,
    xianyu_operations,
)
from cloudctl_api.operation_catalog import (
    BLOCKED_FEATURE_IDS,
    BY_CATALOG_ID,
    FEATURE_BY_ID,
    LEDGER_STATES,
    XY_AVAILABILITY_LEDGER,
    XY_OUT_OF_SCOPE_IDS,
    XY_POLICY_BLOCKED_IDS,
    XY_SENSITIVE_IDS,
    XY_TASK_CATALOG_IDS,
    evaluate_ledger_transition,
)
from cloudctl_api.operation_parameters import validate_operation_parameters
from cloudctl_api.operation_runtime import BUILTIN_OPERATION_KEYS
from cloudctl_api.settings import Settings
from pydantic import ValidationError as PydanticValidationError

ROOT = Path(__file__).resolve().parents[2]
LEDGER_DOC = ROOT / "docs" / "current" / "operation-availability.json"
VALID_PACKAGE_IDS = frozenset(f"P{index:02d}" for index in range(50))
# X12 task card package membership (docs/current/tasks.json).
X12_PACKAGES = frozenset(
    {"P29", "P30", "P31", "P32", "P33", "P34", "P35", "P36", "P37", "P38", "P39", "P46", "P49"}
)

TENANT = "00000000-0000-7000-8000-000000006111"
USER = "00000000-0000-7000-8000-000000006222"

EXPECTED_STATE_COUNTS = {"ENABLED": 1, "PENDING": 20, "POLICY_BLOCKED": 4, "OUT_OF_SCOPE": 6}


def headers(role: str, *, key: str | None = None) -> dict[str, str]:
    values = {
        "X-Tenant-Id": TENANT,
        "X-User-Id": USER,
        "X-Roles": role,
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }
    if key is not None:
        values["Idempotency-Key"] = key
    return values


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
            yield value


# ---------------------------------------------------------------------------
# Full-catalog consistency: 31 rows, one explicit state each, with references.
# ---------------------------------------------------------------------------


def test_ledger_covers_all_31_actions_with_one_explicit_state() -> None:
    assert set(XY_AVAILABILITY_LEDGER) == set(XY_TASK_CATALOG_IDS)
    counts = Counter(entry.state for entry in XY_AVAILABILITY_LEDGER.values())
    assert dict(counts) == EXPECTED_STATE_COUNTS
    assert sum(counts.values()) == 31
    # "全部点亮" is not a completion state: exactly one row is lit.
    assert counts["ENABLED"] == 1
    lit = [cid for cid, entry in XY_AVAILABILITY_LEDGER.items() if entry.state == "ENABLED"]
    assert lit == ["xy-tasks-01"]
    for entry in XY_AVAILABILITY_LEDGER.values():
        assert entry.state in LEDGER_STATES
        assert entry.reason.strip()
        assert "X12" in entry.task_refs, entry.catalog_id
        assert entry.package_refs
        assert set(entry.package_refs) <= VALID_PACKAGE_IDS
        # Titles must match the feature inventory the UI shows.
        assert entry.title == FEATURE_BY_ID[entry.catalog_id].title


def test_ledger_states_derive_from_registrations_not_hand_waving() -> None:
    # POLICY_BLOCKED rows are exactly the policy-blocked xy features.
    assert XY_POLICY_BLOCKED_IDS == set(XY_TASK_CATALOG_IDS) & BLOCKED_FEATURE_IDS
    assert {cid for cid, e in XY_AVAILABILITY_LEDGER.items() if e.state == "POLICY_BLOCKED"} == (
        XY_POLICY_BLOCKED_IDS
    )
    # OUT_OF_SCOPE rows are exactly the adjudicated shared/guide pages.
    assert {cid for cid, e in XY_AVAILABILITY_LEDGER.items() if e.state == "OUT_OF_SCOPE"} == (
        XY_OUT_OF_SCOPE_IDS
    )
    for catalog_id, entry in XY_AVAILABILITY_LEDGER.items():
        availability = BY_CATALOG_ID[catalog_id].availability
        if entry.state == "ENABLED":
            assert availability == "executable", catalog_id
            # The only lit row must be a genuinely deployed builtin lane.
            assert entry.operation_key in BUILTIN_OPERATION_KEYS, catalog_id
        else:
            assert availability != "executable", catalog_id
            assert entry.operation_key not in BUILTIN_OPERATION_KEYS, catalog_id
    # No xy registration outside the lit row has a production mint alias.
    xy_command_types = {
        spec.get("commandType") for spec in xianyu_operations()
    }
    aliased = {
        command
        for command in xy_command_types
        if command and production_command_type(command) is not None
    }
    assert aliased == {"xianyu.publish_goods"}


# ---------------------------------------------------------------------------
# Document parity: docs/current/operation-availability.json is the twin ledger.
# ---------------------------------------------------------------------------


def _document() -> dict:
    assert LEDGER_DOC.is_file(), "docs/current/operation-availability.json is missing"
    return json.loads(LEDGER_DOC.read_text(encoding="utf-8"))


def test_availability_document_matches_python_ledger() -> None:
    document = _document()
    entries = document["entries"]
    assert [entry["catalog_id"] for entry in entries] == sorted(XY_TASK_CATALOG_IDS)
    for entry in entries:
        ledger_entry = XY_AVAILABILITY_LEDGER[entry["catalog_id"]]
        assert entry["operation_key"] == ledger_entry.operation_key
        assert entry["title"] == ledger_entry.title
        assert entry["state"] == ledger_entry.state
        assert entry["reason"] == ledger_entry.reason
        assert entry["task_refs"] == list(ledger_entry.task_refs)
        assert entry["package_refs"] == list(ledger_entry.package_refs)
        assert entry["enable_requires"] == list(ledger_entry.enable_requires)
        if ledger_entry.sensitive is None:
            assert entry["sensitive_discipline"] is None
        else:
            assert entry["sensitive_discipline"] == {
                "budget_cap": ledger_entry.sensitive.budget_cap,
                "target_authorization": ledger_entry.sensitive.target_authorization,
                "platform_entry_evidence": ledger_entry.sensitive.platform_entry_evidence,
            }
    counts = Counter(entry["state"] for entry in entries)
    assert document["state_counts"] == EXPECTED_STATE_COUNTS == dict(counts)
    # Every X12 P package is referenced somewhere (entries + adjudications).
    referenced = {
        package
        for entry in entries
        for package in entry["package_refs"]
    } | {
        package
        for adjudication in document["scope_adjudications"]
        for package in adjudication["package_refs"]
    }
    assert X12_PACKAGES <= referenced


# ---------------------------------------------------------------------------
# Sensitive category discipline (coin spend / promotion / review / deletion).
# ---------------------------------------------------------------------------


def test_sensitive_rows_carry_budget_target_and_evidence_discipline() -> None:
    assert XY_SENSITIVE_IDS == {
        "xy-tasks-09",
        "xy-tasks-10",
        "xy-tasks-11",
        "xy-tasks-14",
        "xy-tasks-16",
        "xy-tasks-17",
        "xy-tasks-18",
    }
    for catalog_id in sorted(XY_SENSITIVE_IDS):
        entry = XY_AVAILABILITY_LEDGER[catalog_id]
        # Unverified rows stay disabled — never marked as a success.
        assert entry.state in {"PENDING", "POLICY_BLOCKED"}, catalog_id
        assert entry.sensitive is not None, catalog_id
        assert entry.sensitive.budget_cap.strip()
        assert entry.sensitive.target_authorization.strip()
        assert entry.sensitive.platform_entry_evidence.startswith("unverified"), catalog_id
        # The UI-facing reason must surface the discipline blocker.
        assert "sensitive category" in entry.reason, catalog_id


# ---------------------------------------------------------------------------
# Scope adjudications: SKU / auction / 会玩 / extra platforms.
# ---------------------------------------------------------------------------

REQUIRED_ADJUDICATION_TOPICS = ("SKU", "拍卖", "会玩", "额外平台")


def test_scope_adjudications_are_recorded_per_topic() -> None:
    document = _document()
    adjudications = document["scope_adjudications"]
    decisions = {item["decision"] for item in adjudications}
    assert decisions <= {"accept", "keep_blocked", "scope_change"}
    assert {"accept", "keep_blocked", "scope_change"} <= decisions
    topics = "".join(item["topic"] for item in adjudications)
    for required in REQUIRED_ADJUDICATION_TOPICS:
        assert required in topics
    for item in adjudications:
        assert item["record"].strip()
        assert item["task_refs"]
        assert item["package_refs"]
        assert set(item["package_refs"]) <= VALID_PACKAGE_IDS
    keep_blocked = [item for item in adjudications if item["decision"] == "keep_blocked"]
    assert keep_blocked
    for item in keep_blocked:
        assert "K12" in item["task_refs"] or "K12" in item["record"]
        assert "PENDING_VERIFICATION" in item["record"]
    huiwan = next(item for item in adjudications if "会玩" in item["topic"])
    assert huiwan["decision"] == "scope_change"
    assert "7.18.92" in huiwan["record"]


# ---------------------------------------------------------------------------
# Transition gate: path exists, default disabled, policy/scope terminal.
# ---------------------------------------------------------------------------


def test_pending_transition_path_exists_but_is_disabled_by_default() -> None:
    pending = XY_AVAILABILITY_LEDGER["xy-tasks-03"]
    assert pending.state == "PENDING"
    # Default (no evidence, no executor): stays disabled.
    assert evaluate_ledger_transition(pending, {}, executor_available=False) == "PENDING"
    assert evaluate_ledger_transition(pending, {}, executor_available=True) == "PENDING"
    # Evidence alone is not enough without a deployed executor.
    evidence = {key: True for key in pending.enable_requires}
    assert evaluate_ledger_transition(pending, evidence, executor_available=False) == "PENDING"
    # Both gates open is the only path to ENABLED.
    assert evaluate_ledger_transition(pending, evidence, executor_available=True) == "ENABLED"
    # Partial evidence never flips.
    partial = dict(evidence)
    partial[pending.enable_requires[-1]] = False
    assert evaluate_ledger_transition(pending, partial, executor_available=True) == "PENDING"

    # Sensitive deletion rows need the full three-part discipline too.
    sensitive = XY_AVAILABILITY_LEDGER["xy-tasks-16"]
    assert "budget_cap" in sensitive.enable_requires
    assert "target_authorization" in sensitive.enable_requires
    assert "platform_entry_evidence" in sensitive.enable_requires
    assert (
        evaluate_ledger_transition(sensitive, {}, executor_available=True) == "PENDING"
    )

    # Policy and scope rows are terminal for evidence.
    blocked = XY_AVAILABILITY_LEDGER["xy-tasks-09"]
    everything = {
        key: True
        for key in (
            "command_v1_lane",
            "t102_verification",
            "budget_cap",
            "target_authorization",
            "platform_entry_evidence",
        )
    }
    assert (
        evaluate_ledger_transition(blocked, everything, executor_available=True)
        == "POLICY_BLOCKED"
    )
    out_of_scope = XY_AVAILABILITY_LEDGER["xy-tasks-25"]
    assert (
        evaluate_ledger_transition(out_of_scope, everything, executor_available=True)
        == "OUT_OF_SCOPE"
    )


# ---------------------------------------------------------------------------
# Drift rejection: parameter / target / budget drift fails validation.
# ---------------------------------------------------------------------------


def test_parameter_target_and_budget_drift_are_rejected() -> None:
    # Budget drift: an undeclared promotion package tier is rejected.
    with pytest.raises(PydanticValidationError):
        validate_operation_parameters(
            "xianyu.coin_promote",
            None,
            {"promoteItem": "manually_selected", "promotePackage": "coins_999"},
        )
    # Target drift: an undeclared deletion selection is rejected.
    with pytest.raises(PydanticValidationError):
        validate_operation_parameters(
            "xianyu.delete_goods", None, {"target": "someone_elses_listings"}
        )
    # Parameter drift: interval below the declared floor is rejected.
    with pytest.raises(PydanticValidationError):
        validate_operation_parameters(
            "xianyu.polish_goods", None, {"intervalSeconds": 1}
        )
    # Unknown parameter on a strict contract is rejected.
    with pytest.raises(PydanticValidationError):
        validate_operation_parameters(
            "xianyu.bargain", None, {"xiaodaoType": "gentle", "jumpTask": True}
        )
    # Sanity: the declared values themselves validate.
    validated = validate_operation_parameters(
        "xianyu.coin_promote",
        None,
        {"promoteItem": "manually_selected", "promotePackage": "coins_60"},
    )
    assert validated["promotePackage"] == "coins_60"


def test_disabled_operations_cannot_be_enabled_by_alias_or_rename() -> None:
    # The mint lane: no xy command type outside the publish lane has an alias.
    assert production_command_type("xianyu.review") is None
    assert production_command_type("xianyu.coin_promote") is None
    assert production_command_type("xianyu.delete_message") is None
    assert set(PRODUCTION_ALIASES.values()) == {
        "xianyu.publish_listing.v1",
        "xianyu.collect_orders.v1",
        "xiaohongshu.publish_note.v1",
        "device.probe_capabilities.v1",
    }
    # A catalogued-but-disabled action cannot mint a production command.
    with pytest.raises(ValueError, match="not enabled for production CommandV1 claim"):
        mint_operation_command(
            "xy-tasks-14",
            {"reviewBody": "great buyer", "reviewTarget": "recent_buyers"},
        )
    # Renaming the operationId is unknown, not an alias.
    with pytest.raises(ValueError, match="unknown operationId"):
        mint_operation_command("xy-tasks-14-v2", {})
    # commandType cannot be smuggled through parameters (drift + forbidden).
    with pytest.raises(ValueError):
        mint_operation_command(
            "xy-tasks-01",
            {"commandType": "xianyu.coin_promote", "listingBody": "x"},
        )


@pytest.mark.asyncio
async def test_unknown_and_disabled_operations_are_rejected_over_http(
    client: httpx.AsyncClient,
) -> None:
    # Unknown (renamed) operation key → 422.
    unknown = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("device_operator", key="x12-unknown-op"),
        json={"operationKey": "xianyu.coin_promote_v2", "resourceId": "device-1"},
    )
    assert unknown.status_code == 422
    assert "not in the approved catalog" in unknown.text

    # Registered but disabled (no deployed executor) → 409, even with valid
    # parameters: registration never means enabled.
    disabled = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("device_operator", key="x12-disabled-op"),
        json={
            "operationKey": "xianyu.coin_promote",
            "resourceId": "device-1",
            "parameters": {"promoteItem": "manually_selected", "promotePackage": "coins_60"},
        },
    )
    assert disabled.status_code == 409
    assert "no deployed executor" in disabled.text

    # Policy-blocked feature cannot ride any lane, including an enabled one.
    blocked_alias = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("device_operator", key="x12-blocked-alias"),
        json={
            "operationKey": "xianyu.listing.publish",
            "featureId": "xy-tasks-09",
            "resourceId": "device-1",
        },
    )
    assert blocked_alias.status_code == 403

    # A disabled sibling cannot be reached by pointing another featureId at
    # the enabled operation key either (mapping mismatch → 422).
    mapping_drift = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("device_operator", key="x12-mapping-drift"),
        json={
            "operationKey": "xianyu.listing.publish",
            "featureId": "xy-tasks-03",
            "resourceId": "device-1",
        },
    )
    assert mapping_drift.status_code == 422

    # Parameter drift on the single ENABLED row is still a 4xx.
    drift = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("device_operator", key="x12-param-drift"),
        json={
            "operationKey": "xianyu.listing.publish",
            "resourceId": "device-1",
            "parameters": {
                "listingBody": "drift probe",
                "mediaAssetIds": [f"asset-{index}" for index in range(50)],
            },
        },
    )
    assert drift.status_code == 422


@pytest.mark.asyncio
async def test_features_surface_ledger_state_and_reason(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/operations/features", headers=headers("viewer"))
    assert response.status_code == 200
    features = {entry["featureId"]: entry for entry in response.json()}
    for catalog_id, entry in XY_AVAILABILITY_LEDGER.items():
        feature = features[catalog_id]
        if entry.state == "ENABLED":
            # The deployed-executor message; executable still depends on RBAC.
            assert feature["reason"].startswith("A deployed, policy-restricted executor")
        else:
            assert feature["reason"].startswith(f"[{entry.state}] "), catalog_id
            assert entry.reason in feature["reason"], catalog_id
            assert feature["executable"] is False, catalog_id
    blocked = features["xy-tasks-09"]
    # The policy view is blocked; executionState stays the executor-lane view
    # (contract_only) because the operation contract itself is registered.
    assert blocked["policy"] == "blocked"
    assert blocked["executionState"] == "contract_only"
    assert blocked["executable"] is False
    assert blocked["reason"].startswith("[POLICY_BLOCKED]")
    pending = features["xy-tasks-03"]
    assert pending["reason"].startswith("[PENDING]")
    out_of_scope = features["xy-tasks-25"]
    assert out_of_scope["reason"].startswith("[OUT_OF_SCOPE]")
