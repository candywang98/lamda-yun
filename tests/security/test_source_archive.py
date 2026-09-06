from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType
from zipfile import ZipFile

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build-source-archive.py"
HARDWARE_TASK_IDS = ("P2-011", "P3-012", "P5-003", "P5-006", "P5-007")


def load_archive_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_source_archive", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def delivery_paths(base: Path, name: str = "source") -> tuple[Path, Path, Path]:
    return (
        base / f"{name}.zip",
        base / f"{name}.manifest.json",
        base / f"{name}.zip.sha256",
    )


def test_archive_is_deterministic_and_writes_auditable_manifest(tmp_path: Path) -> None:
    module = load_archive_module()
    root = tmp_path / "root"
    delivery = tmp_path / "delivery"
    (root / "nested").mkdir(parents=True)
    (root / "alpha.txt").write_text("alpha\n", encoding="utf-8")
    (root / "nested" / "beta.txt").write_text("beta\n", encoding="utf-8")
    output, manifest_path, checksum_path = delivery_paths(delivery)

    first_manifest = module.build_delivery(root, output, manifest_path, checksum_path)
    first_archive = output.read_bytes()
    os.utime(root / "alpha.txt", (2_000_000_000, 2_000_000_000))
    second_manifest = module.build_delivery(root, output, manifest_path, checksum_path)

    assert output.read_bytes() == first_archive
    assert second_manifest == first_manifest
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == second_manifest
    assert checksum_path.read_text(encoding="utf-8") == (
        f"{second_manifest['archive']['sha256']}  source.zip\n"
    )
    assert [entry["path"] for entry in second_manifest["entries"]] == [
        "alpha.txt",
        "nested/beta.txt",
    ]
    assert second_manifest["audit"]["status"] == "passed"
    with ZipFile(output) as archive:
        for info in archive.infolist():
            assert info.date_time == module.ARCHIVE_TIMESTAMP
            assert info.create_system == 3
            assert info.external_attr == module.ARCHIVE_FILE_MODE


def test_archive_excludes_build_outputs_caches_and_sensitive_files(tmp_path: Path) -> None:
    module = load_archive_module()
    root = tmp_path / "root"
    delivery = tmp_path / "delivery"
    root.mkdir()
    (root / "keep.py").write_text("print('kept')\n", encoding="utf-8")
    evidence = root / "artifacts" / "tasks" / "P1-003"
    evidence.mkdir(parents=True)
    (evidence / "commands.log").write_text("pytest -q: passed\n", encoding="utf-8")
    evidence_results = evidence / "test-results"
    evidence_results.mkdir()
    (evidence_results / "software-gates.txt").write_text("passed\n", encoding="utf-8")
    for directory in (
        ".venv",
        "node_modules",
        ".cache",
        "tmp",
        "logs",
        "certs",
        "tokens",
        "test-results",
    ):
        candidate = root / directory
        candidate.mkdir()
        (candidate / "ignored.txt").write_text("ignored\n", encoding="utf-8")
    for name in (
        "app.db",
        "app.log",
        "bundle.tsbuildinfo",
        "client.crt",
        "credentials.json",
        "session.token",
    ):
        (root / name).write_text("excluded\n", encoding="utf-8")
    (root / ".env.example").write_text("TOKEN=replace-me\n", encoding="utf-8")
    output, manifest_path, checksum_path = delivery_paths(delivery)

    manifest = module.build_delivery(root, output, manifest_path, checksum_path)

    assert [entry["path"] for entry in manifest["entries"]] == [
        ".env.example",
        "artifacts/tasks/P1-003/commands.log",
        "artifacts/tasks/P1-003/test-results/software-gates.txt",
        "keep.py",
    ]


def test_hardware_gate_and_remaining_task_evidence_enter_source_archive(
    tmp_path: Path,
) -> None:
    module = load_archive_module()
    source_root = SCRIPT.parents[1]
    root = tmp_path / "source"
    required = {
        "scripts/prepare-hardware-evidence.py",
        "scripts/validate-hardware-evidence.py",
        "scripts/validate-rollout-evidence.py",
        "tests/security/test_source_archive.py",
        "tests/unit/test_delivery_status.py",
        "tests/unit/test_hardware_evidence_gate.py",
        "tests/unit/test_hardware_evidence_preparation.py",
    }
    base_checksum_files = {
        "device-evidence/template.json",
        "software-gates.txt",
        "status.json",
        "summary.md",
    }
    for task_id in HARDWARE_TASK_IDS:
        prefix = f"artifacts/tasks/{task_id}"
        local_checksum_files = set(base_checksum_files)
        if task_id in {"P2-011", "P3-012"}:
            local_checksum_files.update(
                {
                    "device-evidence/authorization-template.json",
                    "device-evidence/run-result-template.json",
                }
            )
        required.add(f"{prefix}/checksums.sha256")
        required.update(f"{prefix}/{name}" for name in local_checksum_files)

        task_root = source_root / prefix
        checksum_entries: dict[str, str] = {}
        for line in (task_root / "checksums.sha256").read_text(encoding="utf-8").splitlines():
            digest, name = line.split("  ", 1)
            checksum_entries[name] = digest
        assert local_checksum_files <= set(checksum_entries)
        required.update(f"{prefix}/{name}" for name in checksum_entries)
        for name, expected in checksum_entries.items():
            actual = hashlib.sha256((task_root / name).read_bytes()).hexdigest()
            assert actual == expected

    for relative in required:
        source = source_root / relative
        assert source.is_file()
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())

    output, manifest_path, checksum_path = delivery_paths(tmp_path / "delivery")
    manifest = module.build_delivery(root, output, manifest_path, checksum_path)
    archived = {entry["path"] for entry in manifest["entries"]}

    assert required <= archived


def test_delivery_ledger_evidence_references_are_audited(tmp_path: Path) -> None:
    module = load_archive_module()
    root = tmp_path / "root"
    evidence = root / "artifacts" / "tasks" / "P0-001" / "summary.md"
    evidence.parent.mkdir(parents=True)
    evidence.write_text("implemented\n", encoding="utf-8")
    ledger = root / "docs" / "delivery" / "task-status.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "P0-001",
                        "evidence": ["artifacts/tasks/P0-001/summary.md"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output, manifest_path, checksum_path = delivery_paths(tmp_path / "delivery")

    manifest = module.build_delivery(
        root,
        output,
        manifest_path,
        checksum_path,
        Path("docs/delivery/task-status.json"),
    )

    assert manifest["audit"]["ledgerEvidence"] == {
        "evidenceReferenceCount": 1,
        "ledger": "docs/delivery/task-status.json",
        "ledgerSha256": hashlib.sha256(ledger.read_bytes()).hexdigest(),
        "status": "passed",
        "taskCount": 1,
        "uniqueEvidenceFileCount": 1,
    }
    archived = {entry["path"] for entry in manifest["entries"]}
    assert "artifacts/tasks/P0-001/summary.md" in archived
    assert "docs/delivery/task-status.json" in archived


@pytest.mark.parametrize(
    ("evidence_path", "create_file", "message"),
    [
        ("artifacts/tasks/P0-001/missing.md", False, "evidence file does not exist"),
        ("runtime.log", True, "evidence file is excluded from archive"),
        ("../outside.txt", False, "evidence path must stay inside source root"),
        ("artifacts\\tasks\\P0-001\\summary.md", False, "POSIX paths"),
    ],
)
def test_delivery_ledger_rejects_unarchivable_evidence(
    tmp_path: Path,
    evidence_path: str,
    create_file: bool,
    message: str,
) -> None:
    module = load_archive_module()
    root = tmp_path / "root"
    root.mkdir()
    if create_file:
        (root / evidence_path).write_text("runtime output\n", encoding="utf-8")
    ledger = root / "docs" / "delivery" / "task-status.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        json.dumps({"tasks": [{"id": "P0-001", "evidence": [evidence_path]}]}),
        encoding="utf-8",
    )
    output, manifest_path, checksum_path = delivery_paths(tmp_path / "delivery")

    with pytest.raises(module.ArchivePolicyError, match=message):
        module.build_delivery(root, output, manifest_path, checksum_path, ledger)

    assert not output.exists()


@pytest.mark.parametrize(
    ("name", "content", "label"),
    [
        (
            "private.txt",
            b"-----BEGIN " + b"PRIVATE KEY-----\nvalue",
            "pkcs8-private-key",
        ),
        (
            "certificate.txt",
            b"-----BEGIN " + b"CERTIFICATE-----\nvalue",
            "certificate",
        ),
        ("token.txt.example", b"AKIA" + b"1234567890ABCDEF", "aws-access-key"),
    ],
)
def test_archive_rejects_sensitive_content(
    tmp_path: Path, name: str, content: bytes, label: str
) -> None:
    module = load_archive_module()
    root = tmp_path / "root"
    root.mkdir()
    (root / name).write_bytes(content)
    output, manifest_path, checksum_path = delivery_paths(tmp_path / "delivery")

    with pytest.raises(module.ArchivePolicyError, match=label):
        module.build_delivery(root, output, manifest_path, checksum_path)

    assert not output.exists()


def test_delivery_outputs_must_be_outside_source_root(tmp_path: Path) -> None:
    module = load_archive_module()
    root = tmp_path / "root"
    root.mkdir()
    output, manifest_path, checksum_path = delivery_paths(root / "outputs")

    with pytest.raises(ValueError, match="outside source root"):
        module.build_delivery(root, output, manifest_path, checksum_path)


def test_archive_rejects_symbolic_links(tmp_path: Path) -> None:
    module = load_archive_module()
    root = tmp_path / "root"
    root.mkdir()
    target = root / "target.txt"
    target.write_text("target\n", encoding="utf-8")
    link = root / "link.txt"
    try:
        link.symlink_to(target)
    except OSError as error:
        pytest.skip(f"symbolic links unavailable: {error}")
    output, manifest_path, checksum_path = delivery_paths(tmp_path / "delivery")

    with pytest.raises(module.ArchivePolicyError, match="symbolic link"):
        module.build_delivery(root, output, manifest_path, checksum_path)
