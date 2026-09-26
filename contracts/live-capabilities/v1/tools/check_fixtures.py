#!/usr/bin/env python3
"""live-capabilities/v1 fixture checker. Exit 0 = pass.

Mode:
- jsonschema  — every fixture.doc is validated against
                ../live-capabilities-v1.schema.json (draft 2020-12) when the
                `jsonschema` package is importable (honors PYTHONPATH).
- structural  — fallback when jsonschema is unavailable: hand-rolled
                structural assertions over the same invariants.

The mode actually used is printed as `mode=<jsonschema|structural>`; per the
K13 task card the mode must be reported honestly, never silently swapped.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V1 = HERE.parent
FIXTURES = V1 / "fixtures"
SCHEMA_PATH = V1 / "live-capabilities-v1.schema.json"
CONTRACT = "live-capabilities/v1@20260917.1"

try:
    import jsonschema  # noqa: F401

    MODE = "jsonschema"
except ImportError:
    jsonschema = None
    MODE = "structural"

EXPECTED_FIXTURES = {
    "k13-positive-session-jpeg-preview.json",
    "k13-positive-session-interactive-remote.json",
    "k13-positive-session-webrtc.json",
    "k13-positive-handover-remote-to-viewing.json",
    "k13-negative-gesture-expired.json",
    "k13-negative-input-in-preview.json",
    "k13-negative-input-seq-regression.json",
    "k13-negative-resume-after-reboot.json",
}

TIER_GATES = {
    "JPEG_PREVIEW": [
        "GATE_LIVE_LEASE",
        "GATE_MEDIAPROJECTION_AUTH",
        "GATE_JPEG_TRANSPORT",
    ],
    "INTERACTIVE_REMOTE": [
        "GATE_LIVE_LEASE",
        "GATE_MEDIAPROJECTION_AUTH",
        "GATE_JPEG_TRANSPORT",
        "GATE_OPERATOR_WRITE",
        "GATE_INPUT_RATELIMIT",
    ],
    "WEBRTC": [
        "GATE_LIVE_LEASE",
        "GATE_MEDIAPROJECTION_AUTH",
        "GATE_OPERATOR_WRITE",
        "GATE_INPUT_RATELIMIT",
        "GATE_TURN_DEPLOY",
        "GATE_BANDWIDTH_BUDGET",
        "GATE_SECURITY_REVIEW",
    ],
}

TIER_CAPS = {
    "JPEG_PREVIEW": {"allowsInput": False, "uiLabel": "preview", "turnRequired": False},
    "INTERACTIVE_REMOTE": {"allowsInput": True, "uiLabel": "interactive", "turnRequired": False},
    "WEBRTC": {"allowsInput": True, "uiLabel": "interactive-hd", "turnRequired": True},
}


def structural_validate(doc: dict) -> None:
    """Minimal structural invariants mirroring the schema (fallback mode)."""
    assert doc.get("doc") in {"session", "input_rejection", "handover", "terminal"}
    for key in ("sessionId", "tenantId"):
        assert isinstance(doc.get(key), str) and doc[key], f"missing {key}"
    if doc["doc"] == "session":
        assert doc["tier"] in TIER_GATES
        assert doc["transport"] in {"JPEG_WS", "WEBRTC"}
        assert doc["state"] in {"VIEWING", "REMOTE"}
        assert doc["gates"] == TIER_GATES[doc["tier"]]
        caps = doc["capabilities"]
        for key, value in TIER_CAPS[doc["tier"]].items():
            assert caps[key] == value, f"capability {key} must be {value!r} on {doc['tier']}"
        assert caps["frameDownlink"] is True
        lease = doc["lease"]
        assert (
            lease["purpose"] == "LIVE" and isinstance(lease["epoch"], int) and lease["epoch"] >= 1
        )
        assert doc["authorization"]["persistsAcrossReboot"] is False
        assert doc["authorization"]["silentResumeAllowed"] is False
        assert doc["maxDurationMinutes"] == 30
        # input channel only on control tiers; TURN only on WEBRTC
        assert ("inputPolicy" in doc) == (doc["tier"] != "JPEG_PREVIEW")
        assert ("turn" in doc) == (doc["tier"] == "WEBRTC")
    elif doc["doc"] == "input_rejection":
        assert doc["code"] in {
            "INPUT_EXPIRED",
            "INPUT_SEQ_REGRESSION",
            "LIVE_INPUT_FORBIDDEN",
            "LIVE_RATE_LIMITED",
        }
        assert doc["input"]["kind"] in {"tap", "swipe", "text"}
        assert doc["audited"] is True
    elif doc["doc"] == "handover":
        assert doc["from"] == "REMOTE" and doc["to"] == "VIEWING"
        assert doc["singleWriterRestored"] is True and doc["frameDownlinkContinues"] is True
        for t in doc["affectedTasks"]:
            assert t["pauseState"] == "PAUSED_WAITING_USER"
            assert t["resumeMode"] in {"REQUEUE_AUTO", "CONFIRM_REQUIRED"}
    else:  # terminal
        assert doc["state"] == "CLOSED"
        assert doc["cause"] in {
            "OPERATOR_STOP",
            "TIMEOUT_30M",
            "DISCONNECT_GRACE_EXPIRED",
            "DEVICE_REBOOT",
            "PROJECTION_REVOKED",
            "SERVICE_CRASH",
            "SERVER_CLOSED",
        }
        assert doc["resumable"] is False and doc["reauthorizationRequired"] is True


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def main() -> int:
    found = {p.name for p in FIXTURES.glob("k13-*.json")}
    assert found == EXPECTED_FIXTURES, f"fixture set mismatch: {sorted(found ^ EXPECTED_FIXTURES)}"

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if MODE == "jsonschema":
        validator_cls = jsonschema.validators.validator_for(schema)
        validator_cls.check_schema(schema)
        validator = validator_cls(schema)

    for name in sorted(EXPECTED_FIXTURES):
        bundle = load(name)
        assert bundle["contract"] == CONTRACT, f"{name}: contract tag mismatch"
        doc = bundle["doc"]
        if MODE == "jsonschema":
            validator.validate(doc)
        else:
            structural_validate(doc)

    # --- semantic assertions beyond schema shape -----------------------------
    p = load("k13-positive-session-jpeg-preview.json")["doc"]
    assert p["tier"] == "JPEG_PREVIEW" and p["transport"] == "JPEG_WS"
    assert p["capabilities"]["allowsInput"] is False
    assert "inputPolicy" not in p and "turn" not in p
    assert "GATE_TURN_DEPLOY" not in p["gates"]
    print("positive jpeg-preview session: OK (read-only, no TURN dependency, Q14 not blocked)")

    i = load("k13-positive-session-interactive-remote.json")["doc"]
    assert i["capabilities"]["allowsInput"] is True
    assert i["transport"] == "JPEG_WS" and i["capabilities"]["turnRequired"] is False
    assert i["inputPolicy"]["maxInputRatePerSecond"] <= 10
    assert 500 <= i["inputPolicy"]["ttlExpiryMs"] <= 5000
    print("positive interactive-remote session: OK (control over JPEG, rate-limited input)")

    w = load("k13-positive-session-webrtc.json")["doc"]
    assert w["transport"] == "WEBRTC" and w["capabilities"]["turnRequired"] is True
    assert "GATE_JPEG_TRANSPORT" not in w["gates"]
    for gate in ("GATE_TURN_DEPLOY", "GATE_BANDWIDTH_BUDGET", "GATE_SECURITY_REVIEW"):
        assert gate in w["gates"]
    assert w["turn"]["credentialTtlSeconds"] <= 3600 and w["turn"]["connectionQuota"] >= 1
    print("positive webrtc session: OK (independent production gates, not a Q14 dependency)")

    h = load("k13-positive-handover-remote-to-viewing.json")["doc"]
    assert h["from"] == "REMOTE" and h["to"] == "VIEWING"
    assert h["singleWriterRestored"] is True and h["frameDownlinkContinues"] is True
    modes = {t["resumeMode"] for t in h["affectedTasks"]}
    assert modes == {"REQUEUE_AUTO", "CONFIRM_REQUIRED"}
    print(
        "positive handover: OK (queue eligibility restored, destructive windows need human confirm)"
    )

    g = load("k13-negative-gesture-expired.json")["doc"]
    assert g["code"] == "INPUT_EXPIRED" and g["sessionState"] == "REMOTE"
    assert g["latestFrameSeq"] - g["input"]["frameSeq"] > 10  # stale frame threshold
    assert g["input"]["seq"] > g["inputWatermark"]  # expiry, not watermark regression
    print("negative gesture-expired: OK (stale frameSeq rejected, never executed)")

    f = load("k13-negative-input-in-preview.json")["doc"]
    assert f["code"] == "LIVE_INPUT_FORBIDDEN" and f["tier"] == "JPEG_PREVIEW"
    assert f["sessionState"] == "VIEWING"
    print("negative input-in-preview: OK (read-only tier has no input channel)")

    r = load("k13-negative-input-seq-regression.json")["doc"]
    assert r["code"] == "INPUT_SEQ_REGRESSION"
    assert r["input"]["seq"] <= r["inputWatermark"]
    assert (
        r["latestFrameSeq"] - r["input"]["frameSeq"] <= 10
    )  # frame fresh: pure watermark violation
    print("negative input-seq-regression: OK (seq <= watermark dropped)")

    t = load("k13-negative-resume-after-reboot.json")["doc"]
    assert t["cause"] == "DEVICE_REBOOT" and t["state"] == "CLOSED"
    assert t["resumable"] is False and t["reauthorizationRequired"] is True
    assert t["tokenInvalidated"] is True
    exp = load("k13-negative-resume-after-reboot.json")["expect"]
    assert exp["reconnectOnOldSession"] == {"status": 410, "code": "LIVE_SESSION_TERMINAL"}
    assert "fresh-mediaprojection-authorization" in exp["reEstablishRequires"]
    print("negative resume-after-reboot: OK (terminal, silent resume forbidden)")

    print(f"all 8 fixtures: OK (mode={MODE})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
