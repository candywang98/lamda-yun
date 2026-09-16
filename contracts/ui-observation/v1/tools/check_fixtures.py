#!/usr/bin/env python3
"""ui-observation/v1 fixture checker.

Computes treeDigest/nodeDigest with the frozen canonicalization (same style as
canonical_steps: stable node order, k=v lines, sorted keys, lowercase bools)
and validates K11 fixtures. Exit 0 = pass.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACT_DIR = HERE.parent

NODE_FIELDS = ("class", "resourceId", "text", "contentDesc", "bounds", "clickable")


def canonical_tree(nodes: list[dict]) -> str:
    ordered = sorted(nodes, key=lambda n: (n["depth"], n["index"]))
    lines = []
    for n in ordered:
        for k in sorted(NODE_FIELDS):
            v = n[k]
            if isinstance(v, bool):
                v = "true" if v else "false"
            lines.append(f"{k}={v}")
    return "\n".join(lines)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> int:
    pos = json.loads((CONTRACT_DIR / "fixtures/k11-positive-observation.json").read_text())
    obs = pos["observation"]
    tree = digest(canonical_tree(obs["nodes"]))
    if pos.get("expectedTreeDigest"):
        assert pos["expectedTreeDigest"] == tree, "treeDigest mismatch"
    pos["expectedTreeDigest"] = tree
    proof = pos["resolution"]["identityProof"]
    first = sorted(obs["nodes"], key=lambda n: (n["depth"], n["index"]))[0]
    node_digest = digest(
        "\n".join(
            f"{k}={'true' if first[k] is True else 'false' if first[k] is False else first[k]}"
            for k in sorted(NODE_FIELDS)
        )
    )
    if proof.get("nodeDigest"):
        assert proof["nodeDigest"] == node_digest, "nodeDigest mismatch"
    proof["nodeDigest"] = node_digest
    (CONTRACT_DIR / "fixtures/k11-positive-observation.json").write_text(
        json.dumps(pos, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"positive: treeDigest={tree[:16]}… nodeDigest={node_digest[:16]}… pinned")

    same_name = json.loads((CONTRACT_DIR / "fixtures/k11-negative-samename-ambiguous.json").read_text())
    assert same_name["expect"]["result"] == "Ambiguous" and len(same_name["candidates"]) == 2
    assert same_name["expect"]["forbidden"], "forbidden strategies must be explicit"

    wrapper = json.loads((CONTRACT_DIR / "fixtures/k11-negative-fullheight-wrapper.json").read_text())
    chosen = [c for c in wrapper["candidates"] if c["index"] == wrapper["expect"]["selectedIndex"]][0]
    wrapper_node = wrapper["candidates"][0]
    def height(b: str) -> int:
        _, _, _, y1 = (int(x) for x in b.split(","))
        return y1
    assert height(wrapper_node["bounds"]) > height(chosen["bounds"]), "wrapper must be taller"

    banner = json.loads((CONTRACT_DIR / "fixtures/k11-negative-banner-displacement.json").read_text())
    assert banner["frames"][0]["businessDigest"] == banner["frames"][1]["businessDigest"]
    assert banner["frames"][0]["treeDigest"] != banner["frames"][1]["treeDigest"]

    redraw = json.loads((CONTRACT_DIR / "fixtures/k11-negative-input-redraw-lost.json").read_text())
    ip = redraw["inputProof"]
    assert ip["imeCommitted"] is False and ip["inconclusive"] is True
    assert redraw["expect"]["treatedAs"] == "FAILURE"

    print("negative fixtures: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
