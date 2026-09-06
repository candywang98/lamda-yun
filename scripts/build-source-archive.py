#!/usr/bin/env python3
"""Build and audit the deterministic, sanitized CloudCtl source archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ARCHIVE_FILE_MODE = 0o100644 << 16
EXCLUDED_DIRECTORIES = {
    ".cache",
    ".git",
    ".gradle",
    ".hypothesis",
    ".idea",
    ".mypy_cache",
    ".next",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "certificates",
    "certs",
    "coverage",
    "credentials",
    "dist",
    "htmlcov",
    "logs",
    "node_modules",
    "out",
    "playwright-report",
    "secrets",
    "target",
    "test-results",
    "tmp",
    "tokens",
}
EXCLUDED_NAMES = {
    ".coverage",
    ".ds_store",
    ".env",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "access-token",
    "access_token",
    "auth-token",
    "auth_token",
    "credentials.json",
    "credentials.yaml",
    "credentials.yml",
    "id_ed25519",
    "id_rsa",
    "refresh-token",
    "refresh_token",
    "secret.json",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
    "service-account.json",
    "token",
    "token.json",
    "token.txt",
    "tokens.json",
}
ALLOWED_ENV_TEMPLATES = {".env.example", ".env.sample", ".env.template"}
EXCLUDED_SUFFIXES = {
    ".cer",
    ".crt",
    ".credentials",
    ".db",
    ".db-shm",
    ".db-wal",
    ".der",
    ".jks",
    ".key",
    ".keystore",
    ".log",
    ".p12",
    ".p7b",
    ".p7c",
    ".p8",
    ".pem",
    ".pfx",
    ".pyc",
    ".pyo",
    ".secret",
    ".sqlite",
    ".sqlite-shm",
    ".sqlite-wal",
    ".sqlite3",
    ".token",
    ".tsbuildinfo",
}
SENSITIVE_MARKERS = {
    "certificate": b"-----BEGIN " + b"CERTIFICATE-----",
    "dsa-private-key": b"-----BEGIN DSA " + b"PRIVATE KEY-----",
    "ec-private-key": b"-----BEGIN EC " + b"PRIVATE KEY-----",
    "openssh-private-key": b"-----BEGIN OPENSSH " + b"PRIVATE KEY-----",
    "pkcs8-private-key": b"-----BEGIN " + b"PRIVATE KEY-----",
    "rsa-private-key": b"-----BEGIN RSA " + b"PRIVATE KEY-----",
}
SENSITIVE_TOKEN_PATTERNS = {
    "aws-access-key": re.compile(rb"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"),
    "github-token": re.compile(rb"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}(?![A-Za-z0-9])"),
    "gitlab-token": re.compile(rb"(?<![A-Za-z0-9])glpat-[A-Za-z0-9_-]{20,}(?![A-Za-z0-9])"),
    "jwt": re.compile(
        rb"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\."
        rb"[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_-])"
    ),
    "slack-token": re.compile(rb"(?<![A-Za-z0-9])xox[baprs]-[A-Za-z0-9-]{20,}(?![A-Za-z0-9])"),
}


class ArchivePolicyError(RuntimeError):
    """Raised when source or archive content violates the delivery policy."""


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _is_task_evidence_log(path: PurePosixPath | None) -> bool:
    return bool(
        path is not None
        and len(path.parts) >= 4
        and path.parts[:2] == ("artifacts", "tasks")
        and path.suffix.casefold() == ".log"
    )


def _is_excluded_directory(path: PurePosixPath) -> bool:
    normalized = path.name.casefold()
    if normalized not in EXCLUDED_DIRECTORIES:
        return False
    return not (
        normalized == "test-results"
        and len(path.parts) >= 4
        and path.parts[:2] == ("artifacts", "tasks")
    )


def _is_excluded_file(name: str, path: PurePosixPath | None = None) -> bool:
    normalized = name.casefold()
    if normalized in EXCLUDED_NAMES:
        return True
    if normalized.startswith(".env.") and normalized not in ALLOWED_ENV_TEMPLATES:
        return True
    return any(normalized.endswith(suffix) for suffix in EXCLUDED_SUFFIXES) and not (
        normalized.endswith(".log") and _is_task_evidence_log(path)
    )


def _sensitive_content_label(content: bytes) -> str | None:
    for label, marker in SENSITIVE_MARKERS.items():
        if marker in content:
            return label
    for label, pattern in SENSITIVE_TOKEN_PATTERNS.items():
        if pattern.search(content):
            return label
    return None


def validate_delivery_paths(root: Path, *delivery_paths: Path) -> None:
    if not root.is_dir():
        raise ValueError(f"source root is not a directory: {root}")
    if len(set(delivery_paths)) != len(delivery_paths):
        raise ValueError("archive, manifest, and checksum paths must be distinct")
    for path in delivery_paths:
        if _is_inside(path, root):
            raise ValueError(f"delivery output must be outside source root: {path}")


def source_files(root: Path) -> list[tuple[str, bytes]]:
    files: list[tuple[str, bytes]] = []
    for directory, child_directories, names in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        for name in child_directories:
            path = directory_path / name
            if path.is_symlink():
                raise ArchivePolicyError(f"symbolic link found in source tree: {path}")
        child_directories[:] = sorted(
            name
            for name in child_directories
            if not _is_excluded_directory(
                PurePosixPath((directory_path / name).relative_to(root).as_posix())
            )
        )
        for name in sorted(names):
            path = directory_path / name
            if path.is_symlink():
                raise ArchivePolicyError(f"symbolic link found in source tree: {path}")
            relative = path.relative_to(root).as_posix()
            if _is_excluded_file(name, PurePosixPath(relative)):
                continue
            content = path.read_bytes()
            sensitive_label = _sensitive_content_label(content)
            if sensitive_label is not None:
                raise ArchivePolicyError(
                    f"sensitive content ({sensitive_label}) found in source file: {relative}"
                )
            files.append((relative, content))
    return sorted(files)


def _zip_info(relative: str) -> ZipInfo:
    info = ZipInfo(relative, ARCHIVE_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = ARCHIVE_FILE_MODE
    return info


def audit_ledger_evidence(
    root: Path,
    ledger_path: Path,
    archived_paths: set[str],
) -> dict[str, Any]:
    ledger_path = ledger_path.resolve()
    if not _is_inside(ledger_path, root):
        raise ValueError(f"delivery ledger must stay inside source root: {ledger_path}")
    if not ledger_path.is_file():
        raise ValueError(f"delivery ledger does not exist: {ledger_path}")

    ledger_relative = ledger_path.relative_to(root).as_posix()
    if ledger_relative not in archived_paths:
        raise ArchivePolicyError(f"delivery ledger is excluded from archive: {ledger_relative}")
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ArchivePolicyError(f"delivery ledger is not valid JSON: {ledger_relative}") from exc
    if not isinstance(ledger, dict) or not isinstance(ledger.get("tasks"), list):
        raise ArchivePolicyError("delivery ledger must contain a tasks array")

    task_ids: set[str] = set()
    evidence_paths: set[str] = set()
    evidence_reference_count = 0
    for index, raw_task in enumerate(ledger["tasks"]):
        if not isinstance(raw_task, dict):
            raise ArchivePolicyError(f"delivery ledger task {index} must be an object")
        task_id = raw_task.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise ArchivePolicyError(f"delivery ledger task {index} must have an id")
        if task_id in task_ids:
            raise ArchivePolicyError(f"duplicate delivery ledger task id: {task_id}")
        task_ids.add(task_id)

        evidence = raw_task.get("evidence")
        if not isinstance(evidence, list):
            raise ArchivePolicyError(f"{task_id}: evidence must be an array")
        task_evidence: set[str] = set()
        for raw_path in evidence:
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise ArchivePolicyError(f"{task_id}: evidence paths must be non-empty strings")
            if "\\" in raw_path:
                raise ArchivePolicyError(
                    f"{task_id}: evidence paths must use repository-relative "
                    f"POSIX paths: {raw_path}"
                )
            path = PurePosixPath(raw_path)
            if path.is_absolute() or ".." in path.parts:
                raise ArchivePolicyError(
                    f"{task_id}: evidence path must stay inside source root: {raw_path}"
                )
            relative = path.as_posix()
            if relative in task_evidence:
                raise ArchivePolicyError(f"{task_id}: duplicate evidence reference: {relative}")
            task_evidence.add(relative)
            if not (root / Path(*path.parts)).is_file():
                raise ArchivePolicyError(f"{task_id}: evidence file does not exist: {relative}")
            if relative not in archived_paths:
                raise ArchivePolicyError(
                    f"{task_id}: evidence file is excluded from archive: {relative}"
                )
            evidence_paths.add(relative)
            evidence_reference_count += 1

    return {
        "evidenceReferenceCount": evidence_reference_count,
        "ledger": ledger_relative,
        "ledgerSha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
        "status": "passed",
        "taskCount": len(task_ids),
        "uniqueEvidenceFileCount": len(evidence_paths),
    }


def build_archive(
    root: Path,
    output: Path,
    files: list[tuple[str, bytes]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    files = source_files(root) if files is None else files
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.next")
    entries: list[dict[str, Any]] = []
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
            for relative, content in files:
                archive.writestr(_zip_info(relative), content, compresslevel=9)
                entries.append(
                    {
                        "path": relative,
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "size": len(content),
                    }
                )
        audit = audit_archive(temporary, entries)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return entries, audit


def audit_archive(
    output: Path, expected_entries: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    observed_entries: list[dict[str, Any]] = []
    with ZipFile(output) as archive:
        corrupt_entry = archive.testzip()
        if corrupt_entry is not None:
            raise ArchivePolicyError(f"archive CRC failed for {corrupt_entry}")

        names = archive.namelist()
        if names != sorted(names):
            raise ArchivePolicyError("archive entries are not sorted")
        if len(names) != len(set(names)):
            raise ArchivePolicyError("archive contains duplicate paths")

        for info in archive.infolist():
            name = info.filename
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise ArchivePolicyError(f"unsafe archive path: {name}")
            for index in range(1, len(path.parts)):
                if _is_excluded_directory(PurePosixPath(*path.parts[:index])):
                    raise ArchivePolicyError(f"excluded directory entered archive: {name}")
            if _is_excluded_file(path.name, path):
                raise ArchivePolicyError(f"excluded file entered archive: {name}")
            if info.date_time != ARCHIVE_TIMESTAMP:
                raise ArchivePolicyError(f"non-deterministic timestamp found: {name}")
            if info.create_system != 3 or info.external_attr != ARCHIVE_FILE_MODE:
                raise ArchivePolicyError(f"non-deterministic permissions found: {name}")
            content = archive.read(info)
            sensitive_label = _sensitive_content_label(content)
            if sensitive_label is not None:
                raise ArchivePolicyError(
                    f"sensitive content ({sensitive_label}) entered archive: {name}"
                )
            observed_entries.append(
                {
                    "path": name,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                }
            )

    if expected_entries is not None and observed_entries != expected_entries:
        raise ArchivePolicyError("archive entries differ from the source manifest")

    return {
        "checks": {
            "crc": "passed",
            "deterministicMetadata": "passed",
            "entryDigests": "passed",
            "pathPolicy": "passed",
            "sensitiveContent": "passed",
            "uniqueSortedEntries": "passed",
        },
        "status": "passed",
    }


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.next")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_manifest(
    output: Path,
    manifest_path: Path,
    entries: list[dict[str, Any]],
    audit: dict[str, Any],
) -> dict[str, Any]:
    archive_content = output.read_bytes()
    archive_sha256 = hashlib.sha256(archive_content).hexdigest()
    manifest = {
        "archive": {
            "bytes": len(archive_content),
            "compression": "deflate-9",
            "entryCount": len(entries),
            "fileName": output.name,
            "normalizedFileMode": "100644",
            "normalizedTimestamp": "1980-01-01T00:00:00Z",
            "sha256": archive_sha256,
        },
        "audit": audit,
        "entries": entries,
        "exclusions": {
            "allowedEnvTemplates": sorted(ALLOWED_ENV_TEMPLATES),
            "directories": sorted(EXCLUDED_DIRECTORIES),
            "fileNames": sorted(EXCLUDED_NAMES),
            "suffixes": sorted(EXCLUDED_SUFFIXES),
        },
        "schemaVersion": 1,
    }
    serialized = json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    _atomic_write_text(manifest_path, serialized)
    return manifest


def write_checksum(output: Path, checksum_path: Path, archive_sha256: str) -> None:
    _atomic_write_text(checksum_path, f"{archive_sha256}  {output.name}\n")


def build_delivery(
    root: Path,
    output: Path,
    manifest_path: Path,
    checksum_path: Path,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    output = output.resolve()
    manifest_path = manifest_path.resolve()
    checksum_path = checksum_path.resolve()
    validate_delivery_paths(root, output, manifest_path, checksum_path)
    files = source_files(root)
    ledger_audit = None
    if ledger_path is not None:
        ledger_path = ledger_path if ledger_path.is_absolute() else root / ledger_path
        ledger_audit = audit_ledger_evidence(
            root,
            ledger_path,
            {relative for relative, _ in files},
        )
    entries, audit = build_archive(root, output, files)
    if ledger_audit is not None:
        audit["ledgerEvidence"] = ledger_audit
    manifest = write_manifest(output, manifest_path, entries, audit)
    write_checksum(output, checksum_path, manifest["archive"]["sha256"])
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--checksum", type=Path)
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("docs/delivery/task-status.json"),
        help="repository-relative delivery ledger whose evidence references must enter the archive",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output.resolve()
    manifest_path = (args.manifest or output.with_name(f"{output.stem}.manifest.json")).resolve()
    checksum_path = (args.checksum or output.with_name(f"{output.name}.sha256")).resolve()
    ledger_path = args.ledger if args.ledger.is_absolute() else root / args.ledger
    manifest = build_delivery(root, output, manifest_path, checksum_path, ledger_path)
    print(f"files={manifest['archive']['entryCount']}")
    print(f"bytes={manifest['archive']['bytes']}")
    print(f"sha256={manifest['archive']['sha256']}")
    print(f"manifest={manifest_path}")
    print(f"checksum={checksum_path}")
    print(f"ledger_evidence={manifest['audit']['ledgerEvidence']['status']}")
    print("archive_audit=passed")


if __name__ == "__main__":
    main()
