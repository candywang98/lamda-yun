#!/usr/bin/env python3
"""delivery-delta/v1 fixture checker: expansion IDs + structural assertions."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACT_DIR = HERE.parent


def delivery_digest(asset_ids: list[str]) -> str:
    return hashlib.sha256("\n".join(f"mediaAssetId={i}" for i in asset_ids).encode()).hexdigest()


def expansion_id(tenant: str, target: str, device: str, media: str) -> str:
    return hashlib.sha256(f"{tenant}:{target}:{device}:{media}".encode()).hexdigest()


def main() -> int:
    pos = json.loads(
        (CONTRACT_DIR / "fixtures/k12-positive-multidevice-expansion.json").read_text()
    )
    req = pos["request"]
    dd = delivery_digest(req["orderedMediaAssetIds"])
    ids = [
        expansion_id(req["tenantId"], req["publishTargetId"], e["deviceId"], dd)
        for e in req["expansions"]
    ]
    if any(pos["expect"]["publishTargetExpansionIds"]):
        assert pos["expect"]["publishTargetExpansionIds"] == ids, "expansion ids mismatch"
    pos["expect"]["publishTargetExpansionIds"] = ids
    pos["expect"]["deliveryDigest"] = dd
    (CONTRACT_DIR / "fixtures/k12-positive-multidevice-expansion.json").write_text(
        json.dumps(pos, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"positive: deliveryDigest={dd[:16]}… expansionIds pinned")
    assert len(set(ids)) == len(ids), "expansion ids must differ per device"

    spray = json.loads((CONTRACT_DIR / "fixtures/k12-negative-account-spray.json").read_text())
    assert spray["expect"]["code"] == "FANOUT_ACCOUNT_UNBOUND" and spray["expect"]["status"] == 422
    accounts = [e["accountId"] for e in spray["request"]["expansions"]]
    assert len(set(accounts)) == 1 and len(accounts) == 2, "spray case must fan one account"

    missing = json.loads(
        (CONTRACT_DIR / "fixtures/k12-negative-missing-field-success.json").read_text()
    )
    assert missing["claim"]["fieldInputProofs"]["price"] == "absent"
    assert missing["expect"]["rejected"] is True

    sku = json.loads(
        (CONTRACT_DIR / "fixtures/k12-negative-sku-claimed-supported.json").read_text()
    )
    assert "sku_variants:SUPPORTED" in sku["recipeRegistration"]["declaredCapabilities"]
    assert sku["expect"]["code"] == "CAPABILITY_PENDING_VERIFICATION"

    print("negative fixtures: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
