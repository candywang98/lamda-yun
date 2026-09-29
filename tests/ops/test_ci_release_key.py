from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
COMPANION_BUILD_PATH = ROOT / "mobile" / "companion" / "app" / "build.gradle.kts"


def android_job() -> dict[str, Any]:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    job = workflow["jobs"]["android"]
    assert isinstance(job, dict)
    return job


def test_android_job_maps_only_the_repository_public_key_variable() -> None:
    mapping = android_job()["env"]["CLOUDCTL_APP_UPDATE_PUBLIC_KEY"]

    assert mapping == "${{ vars.CLOUDCTL_APP_UPDATE_PUBLIC_KEY }}"
    assert "secrets." not in mapping
    assert "||" not in mapping


def test_missing_key_gate_fails_before_checkout_without_echoing_the_key() -> None:
    steps = android_job()["steps"]
    gate_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Require Android release update public key"
    )
    gate = steps[gate_index]
    script = gate["run"]

    assert gate_index == 0
    assert gate["shell"] == "bash"
    assert '[[ -z "${CLOUDCTL_APP_UPDATE_PUBLIC_KEY:-}" ]]' in script
    assert "::error::CLOUDCTL_APP_UPDATE_PUBLIC_KEY repository variable is required" in script
    assert "exit 1" in script
    assert all(
        "${CLOUDCTL_APP_UPDATE_PUBLIC_KEY" not in line
        for line in script.splitlines()
        if "echo" in line
    )


def test_android_commands_keep_full_suites_and_release_key_verification() -> None:
    steps = android_job()["steps"]
    commands = [step["run"] for step in steps if "run" in step]

    verifier = "cd mobile/companion && ./gradlew verifyReleaseUpdatePublicKey"
    companion = "cd mobile/companion && ./gradlew lint test"
    dpc = "cd mobile/dpc && ./gradlew lint test"
    assert verifier in commands
    assert companion in commands
    assert dpc in commands
    assert commands.index(verifier) < commands.index(companion) < commands.index(dpc)

    for step in steps:
        assert step.get("continue-on-error") not in (True, "true")
        command = step.get("run", "")
        assert "--exclude-task" not in command
        assert " -x" not in command
        assert "|| true" not in command


def test_existing_gradle_verifier_rejects_malformed_and_test_keys() -> None:
    build = COMPANION_BUILD_PATH.read_text(encoding="utf-8")

    assert "Base64.getDecoder().decode(encoded)" in build
    assert "decoded.size != 44" in build
    assert 'KeyFactory.getInstance("Ed25519").generatePublic(X509EncodedKeySpec(decoded))' in build
    assert "encoded == debugUpdatePublicKey" in build
    assert 'tasks.named("preReleaseBuild").configure' in build
    assert "dependsOn(verifyReleaseUpdatePublicKey)" in build
