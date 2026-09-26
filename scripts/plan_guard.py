#!/usr/bin/env python3
"""Read-only plan audit. No agent spawning, task promotion or repository changes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath

COMPLETE = {"SOFTWARE_DONE", "SOFTWARE_ACCEPTED", "ACCEPTED"}


def topology(tasks: list[dict], fields: tuple[str, ...]) -> dict:
    ids = [t["id"] for t in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate task id")
    known = set(ids)
    indegree = {i: 0 for i in ids}
    children = defaultdict(list)
    for t in tasks:
        deps = []
        for field in fields:
            x = t.get(field, [])
            if len(x) != len(set(x)):
                raise ValueError(f"duplicate dependency: {t['id']}.{field}")
            deps.extend(x)
        for d in set(deps):
            if d not in known:
                raise ValueError(f"missing dependency {t['id']} -> {d}")
            if d == t["id"]:
                raise ValueError(f"self dependency {d}")
            indegree[t["id"]] += 1
            children[d].append(t["id"])
    q = deque(sorted(i for i, v in indegree.items() if v == 0))
    order = []
    depth = {i: 0 for i in ids}
    parent = {}
    while q:
        i = q.popleft()
        order.append(i)
        for j in sorted(children[i]):
            if depth[i] + 1 > depth[j]:
                depth[j] = depth[i] + 1
                parent[j] = i
            indegree[j] -= 1
            if indegree[j] == 0:
                q.append(j)
    if len(order) != len(ids):
        raise ValueError(
            "cycle / downstream of cycle: " + ", ".join(sorted(i for i, v in indegree.items() if v))
        )
    end = max(order, key=lambda x: depth[x], default=None)
    chain = []
    while end is not None:
        chain.append(end)
        end = parent.get(end)
    return {
        "node_count": len(ids),
        "edge_count": sum(len(set(d for f in fields for d in t.get(f, []))) for t in tasks),
        "max_depth_edges": max(depth.values(), default=0),
        "longest_dependency_chain": chain[::-1],
        "topological_order": order,
        "depths": depth,
    }


def path_prefix(glob: str) -> str:
    return re.split(r"[?*\[]", glob.replace("\\", "/"), maxsplit=1)[0].rstrip("/")


def path_overlap(a: str, b: str) -> bool:
    # Conservative prefix comparison; ambiguous wildcard cases are blocked, never assumed safe.
    x, y = path_prefix(a), path_prefix(b)
    if re.search(r"[?*\[]", a + b):
        return not x or not y or x.startswith(y) or y.startswith(x)
    return x == y or x.startswith(y + "/") or y.startswith(x + "/")


def conflicts(tasks: list[dict]) -> list[str]:
    out = []
    for n, a in enumerate(tasks):
        for b in tasks[n + 1 :]:
            common = set(a.get("required_locks", [])) & set(b.get("required_locks", []))
            if common:
                out.append(f"{a['id']} / {b['id']}: locks {sorted(common)}")
            overlaps = [
                (p, q)
                for p in a.get("owned_paths", [])
                for q in b.get("owned_paths", [])
                if path_overlap(p, q)
            ]
            if overlaps:
                out.append(f"{a['id']} / {b['id']}: write paths {overlaps}")
    return out


def audit(plan: dict) -> dict:
    ts = plan["tasks"]
    by = {t["id"]: t for t in ts}
    hard = topology(ts, ("must",))
    combined = topology(ts, ("must", "integration"))
    for t in ts:
        for k in [
            "id",
            "name",
            "lane",
            "evidence",
            "dev_state",
            "acceptance_state",
            "baseline_sha",
        ]:
            if not t.get(k):
                raise ValueError(f"required field {t['id']}.{k}")
        for p in [*t.get("owned_paths", []), t["evidence"]]:
            if p.startswith("/") or ".." in PurePosixPath(p).parts or "\\" in p:
                raise ValueError(f"unsafe repo path {p}")
        if t["effort_low"] < 0 or t["effort_high"] < t["effort_low"]:
            raise ValueError("invalid effort range")
        if not t.get("implementation") or not t.get("acceptance_cases"):
            raise ValueError("empty task card")
    inherited = {i for t in ts for i in t.get("old_ids", [])}
    missing = set(plan.get("required_old_ids", [])) - inherited
    if missing:
        raise ValueError("unmapped legacy tasks " + str(sorted(missing)))
    packages = {p for t in ts for p in t.get("packages", [])}
    missingp = set(plan.get("required_packages", [])) - packages
    if missingp:
        raise ValueError("unmapped packages " + str(sorted(missingp)))
    if plan.get("max_writers", 0) < 1 or plan["max_writers"] > 3:
        raise ValueError("max_writers must be 1..3")
    ready = [
        t["id"]
        for t in ts
        if t["kind"] not in {"OPTIONAL", "DEVICE_GATE"}
        and t["dev_state"] == "NOT_STARTED"
        and all(by[d]["dev_state"] in COMPLETE for d in t.get("must", []))
    ]
    # Deployment/hardware/contract grants must still be checked by a real controller.
    return dict(
        valid=True,
        development_dag=hard,
        acceptance_union_dag=combined,
        legacy_ids_covered=len(inherited),
        packages_covered=len(packages),
        dependency_ready_candidates=ready,
        initial_running_conflicts=conflicts([t for t in ts if t["dev_state"] == "IN_PROGRESS"]),
        limits=(
            "Static graph and declared-path checks only. NOT proof of deployed behavior, "
            "hardware acceptance or semantic task independence."
        ),
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("plan", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--check-batch", nargs="+")
    a = p.parse_args()
    try:
        plan = json.loads(a.plan.read_text(encoding="utf-8"))
        result = audit(plan)
        if a.check_batch:
            by = {t["id"]: t for t in plan["tasks"]}
            if len(a.check_batch) != len(set(a.check_batch)):
                raise ValueError("duplicate batch id")
            chosen = [by[i] for i in a.check_batch]
            if len(chosen) > plan["max_writers"]:
                raise ValueError("batch exceeds writer capacity")
            c = conflicts(chosen)
            if c:
                raise ValueError("unsafe simultaneous writers: " + "; ".join(c))
            result["batch"] = {
                "ids": a.check_batch,
                "declared_resources_disjoint": True,
                "note": "This checks resources only, NOT current readiness or permissions.",
            }
        if result["initial_running_conflicts"]:
            raise ValueError(str(result["initial_running_conflicts"]))
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if a.output:
            a.output.parent.mkdir(parents=True, exist_ok=True)
            a.output.write_text(text, encoding="utf-8")
        print(text)
        return 0
    except (ValueError, KeyError, OSError, TypeError) as e:
        print(json.dumps({"valid": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
