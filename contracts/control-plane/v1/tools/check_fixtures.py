#!/usr/bin/env python3
"""control-plane/v1 fixture checker. Exit 0 = pass."""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = HERE.parent / "fixtures"

def main() -> int:
    b = json.loads((D / "k14-positive-control-batch.json").read_text())
    r = b["response"]
    evs = r["events"]
    seqs = [e["seq"] for e in evs]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), "seq must be unique+monotonic"
    assert r["from"] > b["request"]["after"], "from must exceed after"
    assert r["through"] <= r["highWatermark"], "through <= highWatermark"
    assert min(seqs) >= r["from"] and max(seqs) <= r["through"], "events within [from,through]"
    assert {e["type"] for e in evs} == {"CANCEL", "SET_CONFIRM_DEADLINE", "ABANDON"}
    print("positive batch: OK")

    n = json.loads((D / "k14-negative-local-timeout-unblock.json").read_text())
    assert n["expect"]["forbidden"] and "自动解除PAUSED blocker" in n["expect"]["forbidden"]
    assert "SUSPECT_ORPHANED" in json.dumps(n["expect"]["required"], ensure_ascii=False)
    print("negative local-timeout: OK (unblock forbidden, alert-only)")

    c = json.loads((D / "k14-negative-cursor-too-old.json").read_text())
    assert c["expect"]["status"] == 410 and c["expect"]["code"] == "CURSOR_TOO_OLD"
    assert c["expect"]["snapshotRequired"] is True
    print("negative cursor-too-old: OK")

    a = json.loads((D / "k14-positive-cancel-ack.json").read_text())
    branches = {br["branch"]: br for br in a["branches"]}
    assert set(branches) == {"APPLIED", "DEFERRED_RECONCILING"}
    assert branches["APPLIED"]["serverState"] == "CANCELLED"
    assert branches["DEFERRED_RECONCILING"]["serverState"].startswith("RECONCILING")
    print("positive cancel-ack: OK (two branches)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
