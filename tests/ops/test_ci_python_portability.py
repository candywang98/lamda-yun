import os
import shutil
import stat
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PG_DISCOVERY_STEP = "Discover PostgreSQL test binaries"
PG_TOOLS = ("initdb", "pg_ctl", "createdb")
SECURITY_SCRIPT = Path("scripts/check-security-boundaries.sh")
DIAGNOSTIC_NAME = "Diagnose fleet latency after pytest failure"
UPLOAD_NAME = "Upload fleet diagnostic evidence"
GATE_COMMAND = 'pytest -q -rs --basetemp "$RUNNER_TEMP/cloudctl-pytest"'
DIAGNOSTIC_COMMAND = (
    'python -m tests.load.fleet.ci_diagnostics --basetemp "$RUNNER_TEMP/cloudctl-fleet-diagnostic"'
)
REPORT_PATHS = (
    "${{ runner.temp }}/cloudctl-pytest/**/load-report-*.json\n"
    "${{ runner.temp }}/cloudctl-fleet-diagnostic/load-report-*.json\n"
    "${{ runner.temp }}/cloudctl-fleet-diagnostic/diagnostic.json\n"
)


def workflow_jobs() -> dict[str, Any]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    return jobs


def postgres_discovery_step() -> dict[str, Any]:
    matches = [
        step for step in workflow_jobs()["python"]["steps"] if step.get("name") == PG_DISCOVERY_STEP
    ]
    assert len(matches) == 1
    return matches[0]


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


def assert_python_gates(job: dict[str, Any]) -> None:
    steps = job["steps"]
    supplementary = steps[-2:]
    assert supplementary == [
        {
            "name": DIAGNOSTIC_NAME,
            "if": "failure() && steps.pytest.outcome == 'failure'",
            "timeout-minutes": 5,
            "run": DIAGNOSTIC_COMMAND,
        },
        {
            "name": UPLOAD_NAME,
            "if": "always()",
            "uses": "actions/upload-artifact@v4",
            "with": {
                "name": (
                    "fleet-evidence-${{ github.sha }}-"
                    "${{ github.run_id }}-${{ github.run_attempt }}"
                ),
                "path": REPORT_PATHS,
                "retention-days": 7,
                "if-no-files-found": "warn",
            },
        },
    ]
    core = steps[:-2]
    commands = [step["run"] for step in core if "run" in step]
    assert commands == [
        "pip install -e '.[dev,lamda]'",
        "ruff format --check .",
        "ruff check .",
        "pyright",
        "mypy",
        postgres_discovery_step()["run"],
        GATE_COMMAND,
        "bash scripts/check-security-boundaries.sh",
    ]
    assert [step for step in core if step.get("id") == "pytest"] == [
        {"id": "pytest", "run": GATE_COMMAND}
    ]
    for section in (job, *core):
        assert "if" not in section
    for section in (job, *steps):
        assert "continue-on-error" not in section


def test_python_workflow_keeps_all_gates_without_ancestry_shortcuts() -> None:
    assert_python_gates(workflow_jobs()["python"])
    assert "Q02_EXPECTED_SHA" not in WORKFLOW.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "mutation",
    [
        "conditional-core",
        "conditional-job",
        "continue",
        "skip-core",
        "replace-gate",
        "retry-gate",
        "broad-upload",
        "conditional-upload",
        "implicit-success",
        "diagnostic-always",
        "same-basetemp",
        "extra-diagnostic",
    ],
)
def test_python_evidence_steps_cannot_bypass_or_replace_gate(mutation: str) -> None:
    job = deepcopy(workflow_jobs()["python"])
    gate = next(step for step in job["steps"] if step.get("id") == "pytest")
    diagnostic, upload = job["steps"][-2:]
    if mutation == "conditional-core":
        gate["if"] = "false"
    elif mutation == "conditional-job":
        job["if"] = "false"
    elif mutation == "continue":
        diagnostic["continue-on-error"] = True
    elif mutation == "skip-core":
        job["steps"].remove(gate)
    elif mutation == "replace-gate":
        gate["run"] = DIAGNOSTIC_COMMAND
    elif mutation == "retry-gate":
        gate["run"] += " || pytest -q -rs"
    elif mutation == "broad-upload":
        upload["with"]["path"] = "${{ runner.temp }}/**"
    elif mutation == "conditional-upload":
        upload["if"] = "success()"
    elif mutation == "implicit-success":
        diagnostic["if"] = "steps.pytest.outcome == 'failure'"
    elif mutation == "diagnostic-always":
        diagnostic["if"] = "always()"
    elif mutation == "same-basetemp":
        diagnostic["run"] = DIAGNOSTIC_COMMAND.replace(
            "cloudctl-fleet-diagnostic", "cloudctl-pytest"
        )
    else:
        job["steps"].insert(-2, deepcopy(diagnostic))
    with pytest.raises(AssertionError):
        assert_python_gates(job)


@pytest.mark.parametrize("forbidden_import", [False, True], ids=["benign", "forbidden-import"])
def test_parsed_security_gate_runs_nonexecutable_guard(
    tmp_path: Path, forbidden_import: bool
) -> None:
    guard = tmp_path / SECURITY_SCRIPT
    guard.parent.mkdir()
    shutil.copyfile(ROOT / SECURITY_SCRIPT, guard)
    guard.chmod(0o644)
    assert stat.S_IMODE(guard.stat().st_mode) == 0o644
    assert guard.read_bytes() == (ROOT / SECURITY_SCRIPT).read_bytes()
    for directory in ("infra", "services", "apps"):
        (tmp_path / directory).mkdir()
    statement = " ".join(("import", "lamda")) if forbidden_import else "value = 1"
    (tmp_path / "services" / "probe.py").write_text(f"{statement}\n", encoding="utf-8")

    def execute(command: str, *, errexit: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 - workflow command in an isolated repository fixture
            [
                "/bin/bash",
                "--noprofile",
                "--norc",
                *(["-e"] if errexit else []),
                "-o",
                "pipefail",
                "-c",
                command,
            ],
            cwd=tmp_path,
            env={"PATH": os.defpath, "LC_ALL": "C"},
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )

    # Bash 3.2 with -e maps EACCES to 1; inspect the raw command status here.
    direct = execute(SECURITY_SCRIPT.as_posix(), errexit=False)
    assert direct.returncode == 126, direct.stdout + direct.stderr
    assert "Permission denied" in direct.stderr

    command = next(
        step["run"]
        for step in workflow_jobs()["python"]["steps"]
        if step.get("run") == "bash scripts/check-security-boundaries.sh"
    )
    result = execute(command)
    assert result.returncode == (1 if forbidden_import else 0), result.stdout + result.stderr
    if forbidden_import:
        assert result.stderr == (
            f"LAMDA import outside packages/lamda-driver: ./services/probe.py:1:{statement}\n"
        )
        assert result.stdout == ""
    else:
        assert result.stdout == "Security boundary checks passed.\n"
        assert result.stderr == ""


def test_postgres_discovery_uses_bash_only_in_python_job() -> None:
    step = postgres_discovery_step()

    assert set(step) == {"name", "shell", "run"}
    assert step["shell"] == "bash"
    for name, job in workflow_jobs().items():
        if name != "python":
            assert all(step.get("name") != PG_DISCOVERY_STEP for step in job["steps"])


@pytest.mark.parametrize(
    ("unavailable_tool", "failure_mode"),
    [
        (None, None),
        ("pg_config", "missing"),
        ("initdb", "missing"),
        ("pg_ctl", "missing"),
        ("createdb", "missing"),
        ("initdb", "not-executable"),
        ("pg_ctl", "not-executable"),
        ("createdb", "not-executable"),
    ],
)
def test_parsed_postgres_discovery_checks_tools_before_export(
    tmp_path: Path, unavailable_tool: str | None, failure_mode: str | None
) -> None:
    command_dir = tmp_path / "commands"
    binary_dir = tmp_path / "postgres binaries"
    command_dir.mkdir()
    binary_dir.mkdir()
    pg_config = command_dir / "pg_config"
    pg_config.write_text(
        "#!/bin/sh\n"
        '[ "$#" -eq 1 ] && [ "$1" = "--bindir" ] || exit 64\n'
        'printf "%s\\n" "$TEST_PG_BINDIR"\n',
        encoding="utf-8",
    )
    pg_config.chmod(0o700)
    for tool in PG_TOOLS:
        binary = binary_dir / tool
        binary.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$0" >> "$TEST_PG_EXECUTIONS"\nexit 99\n',
            encoding="utf-8",
        )
        binary.chmod(0o700)
    if unavailable_tool is not None:
        unavailable = (
            pg_config if unavailable_tool == "pg_config" else binary_dir / unavailable_tool
        )
        if failure_mode == "missing":
            unavailable.unlink()
        else:
            unavailable.chmod(0o600)

    github_path = tmp_path / "github-path"
    previous_path = "/existing/tool/bin\n"
    github_path.write_text(previous_path, encoding="utf-8")
    executions = tmp_path / "unexpected-postgres-execution"
    script = postgres_discovery_step()["run"]
    result = subprocess.run(  # noqa: S603 - parsed workflow with isolated fake executables
        ["/bin/bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
        env={
            "PATH": str(command_dir),
            "GITHUB_PATH": str(github_path),
            "TEST_PG_BINDIR": str(binary_dir),
            "TEST_PG_EXECUTIONS": str(executions),
        },
    )

    assert not executions.exists(), "Discovery must not execute PostgreSQL tools"
    if unavailable_tool is None:
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        assert result.stdout.splitlines() == [
            f"PostgreSQL test binary: {binary_dir / tool}" for tool in PG_TOOLS
        ]
        assert github_path.read_text(encoding="utf-8") == previous_path + f"{binary_dir}\n"
    else:
        assert result.returncode == 1
        expected_error = (
            "Cannot locate PostgreSQL test binaries via pg_config --bindir"
            if unavailable_tool == "pg_config"
            else f"Missing or non-executable PostgreSQL test binary: {unavailable}"
        )
        assert f"::error::{expected_error}" in result.stdout + result.stderr
        assert not any(
            line.startswith("PostgreSQL test binary: ") for line in result.stdout.splitlines()
        )
        assert github_path.read_text(encoding="utf-8") == previous_path


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
