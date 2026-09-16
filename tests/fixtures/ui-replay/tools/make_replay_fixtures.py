#!/usr/bin/env python3
"""B12 ui-replay fixture generator (ui-observation/v1@20260916.1).

Derives the three B12 replay fixtures from the K11 frozen contract
fixtures, reusing the contract's own canonical_tree/digest implementation
(imported from contracts/ui-observation/v1/tools/check_fixtures.py) so the
pinned digests are correct by construction. Also maintains:

  tests/fixtures/ui-replay/contracts/   byte-identical copies of the 5 K11 fixtures
  tests/fixtures/ui-replay/replay/      derived B12 replay fixtures + evidence manifest
  mobile/companion/app/src/test/resources/ui-replay/   classpath mirror (byte-identical)

All node trees are SYNTHETIC (contract-derived); no real device XML exists
or is fabricated — see evidence-manifest.json. Run from anywhere:

  python3 tests/fixtures/ui-replay/tools/make_replay_fixtures.py   # exit 0
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
CONTRACT_DIR = REPO / "contracts/ui-observation/v1"
CONTRACT_FIXTURES = CONTRACT_DIR / "fixtures"
OUT_ROOT = REPO / "tests/fixtures/ui-replay"
OUT_CONTRACTS = OUT_ROOT / "contracts"
OUT_REPLAY = OUT_ROOT / "replay"
TEST_RES = REPO / "mobile/companion/app/src/test/resources/ui-replay"

CONTRACT_ID = "ui-observation/v1@20260916.1"


def load_contract_module():
    spec = importlib.util.spec_from_file_location(
        "k11_check_fixtures", CONTRACT_DIR / "tools/check_fixtures.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def node(depth, index, cls, rid, text, desc, bounds, clickable):
    return {
        "depth": depth,
        "index": index,
        "class": cls,
        "resourceId": rid,
        "text": text,
        "contentDesc": desc,
        "bounds": bounds,
        "clickable": clickable,
    }


def observation(cf, nodes, **overrides):
    obs = {
        "source": "a11y_tree",
        "package": "com.taobao.idlefish",
        "appVersion": "7.10.20",
        "windowId": 123,
        "display": 0,
        "insets": {"left": 0, "top": 132, "right": 0, "bottom": 96},
        "rotation": 0,
        "capturedAt": "2026-09-16T22:00:00+08:00",
        "sessionEpoch": 5,
        "nodes": nodes,
    }
    obs.update(overrides)
    obs["treeDigest"] = cf.digest(cf.canonical_tree(obs["nodes"]))
    return obs


def fullheight_wrapper_fixture(cf):
    # Derived from k11-negative-fullheight-wrapper.json: candidate index 1 is
    # the whole-list RecyclerView whose aggregated contentDescription matches
    # the query; candidate index 4 is the real card title. Same bounds as the
    # contract candidates. The wrapper MUST be excluded (P09-13 precheck).
    nodes = [
        node(0, 0, "android.widget.FrameLayout", "", "", "", "0,0,1080,2400", False),
        node(
            1, 1, "androidx.recyclerview.widget.RecyclerView", "recycler_list", "",
            "如果历史是一群喵4 等 27 件商品", "0,345,1080,2337", True,
        ),
        node(2, 2, "android.widget.LinearLayout", "card_root", "", "", "0,345,1080,820", True),
        node(3, 3, "android.widget.TextView", "item_price", "¥128", "", "0,764,1080,820", False),
        node(3, 4, "android.widget.TextView", "item_title", "如果历史是一群喵4", "", "0,345,1080,764", True),
    ]
    return {
        "contract": CONTRACT_ID,
        "derivedFrom": "k11-negative-fullheight-wrapper.json",
        "case": "replay-fullheight-wrapper",
        "observation": observation(cf, nodes),
        "query": {"locatorKind": "text", "text": "如果历史是一群喵4"},
        "expect": {
            "result": "Resolved",
            "selectedIndex": 4,
            "rawCandidateIndices": [1, 4],
            "excluded": [{"why": "full-height wrapper", "nodeIndex": 1}],
            "misselectionTrap": "无防误选预检时首个候选 index=1（wrapper）会被误选",
        },
    }


def samename_ambiguous_fixture(cf):
    # Derived from k11-negative-samename-ambiguous.json: two cards with the
    # same title, bounds identical to the contract candidates (indices 4/9).
    # Neither contains the other -> both survive -> Ambiguous (LOCATOR_AMBIGUOUS).
    nodes = [
        node(0, 0, "android.widget.FrameLayout", "", "", "", "0,0,1080,2400", False),
        node(1, 1, "androidx.recyclerview.widget.RecyclerView", "recycler_list", "", "", "0,132,1080,2337", False),
        node(3, 4, "android.widget.TextView", "item_title", "云控平台验收测试服务", "", "0,345,1080,500", True),
        node(3, 9, "android.widget.TextView", "item_title", "云控平台验收测试服务", "", "0,900,1080,1055", True),
    ]
    return {
        "contract": CONTRACT_ID,
        "derivedFrom": "k11-negative-samename-ambiguous.json",
        "case": "replay-samename-ambiguous",
        "observation": observation(cf, nodes),
        "query": {"locatorKind": "text", "text": "云控平台验收测试服务"},
        "expect": {
            "result": "Ambiguous",
            "candidateIndices": [4, 9],
            "terminal": "LOCATOR_AMBIGUOUS",
            "forbidden": ["select-first", "select-center", "select-largest", "auto-retry"],
        },
    }


def banner_displacement_fixture(cf):
    # Derived from k11-negative-banner-displacement.json: frame 2 inserts a
    # 96px banner and shifts every business node down by 96px. treeDigest
    # changes, business digest (banner layer excluded, displacement
    # normalized) does not -> polling feeds [1,2,2] must exit NO_PROGRESS
    # with zero side effects.
    def business_nodes(dy):
        # Every business node (root included) shifts uniformly by dy when the
        # banner appears; the replayer normalizes the whole subset by -dy.
        return [
            node(0, 0, "android.widget.FrameLayout", "", "", "", f"0,{dy},1080,{2400+dy}", False),
            node(3, 2, "android.widget.TextView", "item_title", "如果历史是一群喵4", "", f"0,{132+dy},1080,{300+dy}", True),
            node(3, 3, "android.widget.TextView", "item_title", "如果历史是一群喵5", "", f"0,{320+dy},1080,{500+dy}", True),
            node(4, 4, "android.widget.Button", "btn_publish", "发布", "", f"120,{2130+dy},480,{2200+dy}", True),
        ]

    frame1_nodes = business_nodes(0)
    frame2_nodes = [
        business_nodes(96)[0],
        node(1, 1, "android.widget.LinearLayout", "banner_container", "限时活动", "", "0,0,1080,96", True),
        *business_nodes(96)[1:],
    ]
    return {
        "contract": CONTRACT_ID,
        "derivedFrom": "k11-negative-banner-displacement.json",
        "case": "replay-banner-displacement",
        "frames": [
            {
                "n": 1,
                "banner": "absent",
                "displacementY": 0,
                "excludedLayerResourceIds": ["banner_container"],
                "observation": observation(cf, frame1_nodes),
            },
            {
                "n": 2,
                "banner": "present-96px",
                "displacementY": 96,
                "excludedLayerResourceIds": ["banner_container"],
                "observation": observation(cf, frame2_nodes),
            },
        ],
        "expect": {
            "result": "NO_PROGRESS",
            "feed": [1, 2, 2],
            "pollingBudget": {"maxAttempts": 20, "minIntervalMs": 500, "noProgressLimit": 3},
            "treeDigestChanges": True,
            "businessDigestStable": True,
            "afterLimit": "NO_PROGRESS 退出，零副作用",
        },
    }


def evidence_manifest():
    missing = {
        "k11-positive-observation.json": "真机 a11y_tree 原始 dump（windowId/insets 实测值）",
        "k11-negative-samename-ambiguous.json": "真机同名商品列表实测候选 bounds",
        "k11-negative-fullheight-wrapper.json": "真机整列表 wrapper contentDescription 汇总实测",
        "k11-negative-banner-displacement.json": "真机横幅出现前后两帧 dump",
        "k11-negative-input-redraw-lost.json": "真机 IME 输入重绘 trace（B14 消费义务）",
    }
    entries = [
        {
            "file": f"contracts/{name}",
            "origin": "contract-frozen",
            "capturedXml": None,
            "missingEvidence": [reason],
        }
        for name, reason in missing.items()
    ]
    entries += [
        {
            "file": "replay/b12-fullheight-wrapper.json",
            "origin": "derived-synthetic",
            "capturedXml": None,
            "missingEvidence": [
                "真机闲鱼商品列表页 a11y dump（wrapper 汇总 contentDescription 实测）",
                "uiautomator_dump 跨源复核样本（§4 crossCheckedAgainst 第二源）",
            ],
        },
        {
            "file": "replay/b12-samename-ambiguous.json",
            "origin": "derived-synthetic",
            "capturedXml": None,
            "missingEvidence": ["真机同名商品两候选实测 bounds/层级"],
        },
        {
            "file": "replay/b12-banner-displacement.json",
            "origin": "derived-synthetic",
            "capturedXml": None,
            "missingEvidence": ["真机横幅出现前后两帧连续 dump（含位移量实测）"],
        },
    ]
    return {
        "manifest": "ui-replay-evidence/v1",
        "contract": CONTRACT_ID,
        "task": "B12",
        "note": (
            "证据现状清单：本目录所有节点树均为合同冻结 fixture 或其派生合成数据，"
            "不存在任何真实设备抓取的 XML，也不虚构 capturedXml；缺失证据逐条列明。"
        ),
        "fixtures": entries,
    }


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    cf = load_contract_module()

    fixtures = {
        "b12-fullheight-wrapper.json": fullheight_wrapper_fixture(cf),
        "b12-samename-ambiguous.json": samename_ambiguous_fixture(cf),
        "b12-banner-displacement.json": banner_displacement_fixture(cf),
    }
    for name, payload in fixtures.items():
        write_json(OUT_REPLAY / name, payload)
    write_json(OUT_REPLAY / "evidence-manifest.json", evidence_manifest())

    # Byte-identical copies of the frozen contract fixtures (same-source rule,
    # §1: copies stay in the a11y_tree source, never merged with other sources).
    for name in sorted(CONTRACT_FIXTURES.glob("*.json")):
        OUT_CONTRACTS.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(name, OUT_CONTRACTS / name.name)

    # Classpath mirror for Android unit tests (byte-identical, verified by
    # tests). Only the ui-replay subtree is owned by this generator — never
    # touch unrelated test resources.
    ui_replay_res = TEST_RES
    if ui_replay_res.exists():
        shutil.rmtree(ui_replay_res)
    (TEST_RES / "contracts").parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(OUT_ROOT / "contracts", TEST_RES / "contracts")
    shutil.copytree(OUT_REPLAY, TEST_RES / "replay")

    # Self-verify: pinned digests recompute, mirror bytes match.
    for name, payload in fixtures.items():
        obs = payload.get("observation")
        frames = payload.get("frames")
        for o in ([obs] if obs else []) + [f["observation"] for f in (frames or [])]:
            assert o["treeDigest"] == cf.digest(cf.canonical_tree(o["nodes"]))
    for copied in (TEST_RES / "contracts").glob("*.json"):
        assert copied.read_bytes() == (CONTRACT_FIXTURES / copied.name).read_bytes()
    for copied in (TEST_RES / "replay").glob("*.json"):
        assert copied.read_bytes() == (OUT_REPLAY / copied.name).read_bytes()
    print("ui-replay fixtures regenerated + verified (3 replay, 5 contract copies, mirror)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
