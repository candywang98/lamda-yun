import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def workflow_jobs() -> dict[str, Any]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    return jobs


def test_only_python_checkout_requests_full_history_for_q02() -> None:
    jobs = workflow_jobs()
    checkouts = [
        step for step in jobs["python"]["steps"] if step.get("uses") == "actions/checkout@v4"
    ]

    assert checkouts == [{"uses": "actions/checkout@v4", "with": {"fetch-depth": 0}}]
    assert type(checkouts[0]["with"]["fetch-depth"]) is int
    assert jobs["python"]["steps"][0] == checkouts[0]
    for name in ("frontend", "android"):
        other = [step for step in jobs[name]["steps"] if step.get("uses") == "actions/checkout@v4"]
        assert other == [{"uses": "actions/checkout@v4"}]


def test_python_workflow_keeps_all_gates_without_ancestry_shortcuts() -> None:
    job = workflow_jobs()["python"]
    commands = [step["run"] for step in job["steps"] if "run" in step]

    assert commands == [
        "pip install -e '.[dev,lamda]'",
        "ruff format --check .",
        "ruff check .",
        "pyright",
        "mypy",
        "pytest -q",
        "scripts/check-security-boundaries.sh",
    ]
    for section in (job, *job["steps"]):
        assert "if" not in section
        assert "continue-on-error" not in section
    assert "Q02_EXPECTED_SHA" not in WORKFLOW.read_text(encoding="utf-8")


def test_configured_checkout_depth_preserves_real_ancestor_proof(tmp_path: Path) -> None:
    steps = workflow_jobs()["python"]["steps"]
    checkout = next(step for step in steps if step.get("uses") == "actions/checkout@v4")
    depth = checkout.get("with", {}).get("fetch-depth", 1)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)

    def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 - fixed git commands in disposable local repositories
            ["git", *args],  # noqa: S607 - repository tests use git from PATH
            capture_output=True,
            text=True,
            env=environment,
            check=check,
            timeout=30,
        )

    origin = tmp_path / "origin"
    git("init", "--quiet", str(origin))
    for message in ("frozen ancestor", "descendant"):
        git(
            "-C",
            str(origin),
            "-c",
            "user.name=CI portability test",
            "-c",
            "user.email=ci@example.test",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            message,
        )
    expected = git("-C", str(origin), "rev-parse", "HEAD^").stdout.strip()

    shallow = tmp_path / "shallow"
    git("clone", "--quiet", "--depth", "1", "--no-checkout", origin.as_uri(), str(shallow))
    assert git("-C", str(shallow), "rev-parse", "--is-shallow-repository").stdout.strip() == "true"
    assert (
        git(
            "-C", str(shallow), "merge-base", "--is-ancestor", expected, "HEAD", check=False
        ).returncode
        != 0
    )

    configured = tmp_path / "configured"
    depth_args = () if depth == 0 else ("--depth", str(depth))
    git("clone", "--quiet", "--no-checkout", *depth_args, origin.as_uri(), str(configured))
    proof = git("-C", str(configured), "merge-base", "--is-ancestor", expected, "HEAD", check=False)
    assert proof.returncode == 0, proof.stderr
    assert (
        git("-C", str(configured), "rev-parse", "--is-shallow-repository").stdout.strip() == "false"
    )
