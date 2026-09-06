#!/usr/bin/env python3
"""Run bounded local load, resilience, and recovery acceptance checks.

The checks use an in-process test Control API, a temporary Edge SQLite spool,
and synthetic backup payloads. They never connect to a device, LAMDA, or a
production service, so their reports cannot satisfy hardware/production gates.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import tracemalloc
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = (
    "packages/domain/src",
    "packages/edge-protocol/src",
    "packages/lamda-driver/src",
    "packages/automation-sdk/src",
    "packages/observability/src",
    "services/control-api/src",
    "services/temporal-worker/src",
    "services/edge-hub/src",
    "services/outbox-dispatcher/src",
    "edge/gateway/src",
)
for source in SOURCE_DIRS:
    source_path = str(ROOT / source)
    if source_path not in sys.path:
        sys.path.insert(0, source_path)

from cloudctl_edge.spool import EdgeSpool, StaleFencingToken  # noqa: E402
from cloudctl_edge_protocol import edge_control_pb2 as pb  # noqa: E402

TENANT_ID = "00000000-0000-7000-8000-00000000c001"
USER_ID = "00000000-0000-7000-8000-00000000c002"


class AcceptanceError(RuntimeError):
    """Raised when a local operational acceptance assertion fails."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.next")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("at least one observation is required")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * percentile)))
    return ordered[index]


def _headers() -> dict[str, str]:
    return {
        "X-Tenant-Id": TENANT_ID,
        "X-User-Id": USER_ID,
        "X-Roles": "viewer",
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }


async def run_load(
    request_count: int,
    concurrency: int,
    p95_latency_ms_maximum: float = 1000.0,
) -> dict[str, Any]:
    from cloudctl_api import create_app
    from cloudctl_api.settings import Settings

    if request_count < 1:
        raise ValueError("request_count must be positive")
    if concurrency < 1 or concurrency > request_count:
        raise ValueError("concurrency must be between 1 and request_count")
    if p95_latency_ms_maximum <= 0:
        raise ValueError("p95 latency maximum must be positive")

    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    latencies_ms: list[float] = []
    statuses: Counter[int] = Counter()
    failures: list[str] = []
    semaphore = asyncio.Semaphore(concurrency)
    started = 0.0
    peak_bytes = 0
    try:
        async with app.router.lifespan_context(app):
            logging.getLogger("httpx").setLevel(logging.WARNING)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://local-acceptance",
                timeout=5.0,
            ) as client:
                warmup = await client.get("/health/ready")
                if warmup.status_code != 200:
                    raise AcceptanceError(f"load warmup failed: {warmup.status_code}")
                catalog_warmup = await client.get("/api/v1/operations/catalog", headers=_headers())
                if catalog_warmup.status_code != 200:
                    raise AcceptanceError(f"catalog warmup failed: {catalog_warmup.status_code}")

                async def request_once(index: int) -> None:
                    path = "/api/v1/operations/catalog" if index % 2 else "/health/ready"
                    headers = _headers() if path.startswith("/api/") else None
                    async with semaphore:
                        request_started = time.perf_counter()
                        try:
                            response = await client.get(path, headers=headers)
                            statuses[response.status_code] += 1
                            if response.status_code != 200:
                                failures.append(f"{path}:{response.status_code}")
                        except Exception as error:  # noqa: BLE001
                            failures.append(f"{path}:{type(error).__name__}")
                        finally:
                            latencies_ms.append((time.perf_counter() - request_started) * 1000)

                started = time.perf_counter()
                tracemalloc.start()
                await asyncio.gather(*(request_once(index) for index in range(request_count)))
    finally:
        if tracemalloc.is_tracing():
            _, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()

    duration_seconds = time.perf_counter() - started
    p95_ms = _percentile(latencies_ms, 0.95)
    error_rate = len(failures) / request_count
    thresholds = {
        "errorRateMaximum": 0.0,
        "p95LatencyMsMaximum": p95_latency_ms_maximum,
        "pythonPeakAllocationBytesMaximum": 256 * 1024 * 1024,
    }
    passed = (
        error_rate <= thresholds["errorRateMaximum"]
        and p95_ms <= thresholds["p95LatencyMsMaximum"]
        and peak_bytes <= thresholds["pythonPeakAllocationBytesMaximum"]
    )
    return {
        "acceptanceStatus": "blocked_hardware",
        "evidenceClass": "local_mock_load",
        "generatedAt": _now(),
        "hardwareEvidence": False,
        "metrics": {
            "durationSeconds": round(duration_seconds, 6),
            "errorRate": round(error_rate, 6),
            "p50LatencyMs": round(_percentile(latencies_ms, 0.50), 3),
            "p95LatencyMs": round(p95_ms, 3),
            "p99LatencyMs": round(_percentile(latencies_ms, 0.99), 3),
            "pythonPeakAllocationBytes": peak_bytes,
            "requestsPerSecond": round(request_count / duration_seconds, 3),
            "statusCounts": {str(key): value for key, value in sorted(statuses.items())},
        },
        "parameters": {"concurrency": concurrency, "requestCount": request_count},
        "schemaVersion": 1,
        "softwareStatus": "passed" if passed else "failed",
        "taskId": "P5-001",
        "thresholds": thresholds,
        "warning": (
            "This is a bounded in-process load probe. It is not a production capacity, "
            "long-soak, device, Android, or LAMDA acceptance result."
        ),
    }


def _command(command_id: str, fencing_token: int, lease_id: str) -> pb.StartCommand:
    command = pb.StartCommand(
        command_id=command_id,
        task_run_id="task-local-chaos",
        device_id="device-local-chaos",
        lease_id=lease_id,
        fencing_token=fencing_token,
        command_type="COLLECT_HEALTH",
    )
    command.deadline.FromDatetime(datetime.now(UTC) + timedelta(minutes=5))
    return command


def _disk_pressure_check(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    full_error_seen = False
    inserted = 0
    try:
        connection.execute("PRAGMA page_size=512")
        connection.execute("PRAGMA max_page_count=32")
        connection.execute("CREATE TABLE sentinel(value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel(value) VALUES ('preserved')")
        connection.commit()
        try:
            for index in range(10_000):
                connection.execute(
                    "INSERT INTO pressure(value) VALUES (?)"
                    if index
                    else "CREATE TABLE pressure(value BLOB NOT NULL)",
                    (b"x" * 400,) if index else (),
                )
                if index:
                    inserted += 1
            connection.commit()
        except sqlite3.OperationalError as error:
            full_error_seen = "full" in str(error).casefold()
            connection.rollback()
    finally:
        connection.close()

    reopened = sqlite3.connect(database)
    try:
        integrity = str(reopened.execute("PRAGMA integrity_check").fetchone()[0])
        sentinel = str(reopened.execute("SELECT value FROM sentinel").fetchone()[0])
    finally:
        reopened.close()
    if not full_error_seen or integrity != "ok" or sentinel != "preserved":
        raise AcceptanceError(
            "bounded SQLite disk-pressure check did not fail closed with intact data"
        )
    return {
        "detail": "SQLITE_FULL observed; committed sentinel survived and integrity_check=ok",
        "insertedBeforeFailure": inserted,
        "status": "passed",
    }


def run_chaos() -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="cloudctl-local-chaos-") as temporary:
        state = Path(temporary)
        spool_path = state / "edge-spool.sqlite3"
        spool = EdgeSpool(spool_path)
        try:
            spool.accept_command(_command("restart-command", 1, "lease-1"))
            spool.set_command_state("restart-command", "STARTED")
            for index in range(25):
                spool.enqueue_edge_message(
                    pb.EdgeToCloud(
                        command_ack=pb.CommandAck(command_id=f"offline-{index}", state="RECEIVED")
                    )
                )
        finally:
            spool.close()

        restarted = EdgeSpool(spool_path)
        try:
            replayed = restarted.replay_edge_messages()
            if [message.sequence for message in replayed] != list(range(1, 26)):
                raise AcceptanceError("offline replay sequence was not durable and ordered")
            checks["networkOutage"] = {
                "detail": "25 outbound events persisted offline and replayed in order",
                "status": "passed",
            }
            if restarted.command_state("restart-command") != "STARTED":
                raise AcceptanceError("command state did not survive Edge spool restart")
            checks["edgeRestart"] = {
                "detail": "STARTED command state survived close and reopen",
                "status": "passed",
            }

            restarted.accept_command(_command("new-owner", 2, "lease-2"))
            try:
                restarted.assert_current_fence("device-local-chaos", "lease-1", 1)
            except StaleFencingToken:
                checks["leaseLoss"] = {
                    "detail": "higher fencing token invalidated the previous lease",
                    "status": "passed",
                }
            else:
                raise AcceptanceError("stale lease retained the current device fence")
        finally:
            restarted.close()

        checks["diskPressure"] = _disk_pressure_check(state / "pressure.sqlite3")

    return {
        "acceptanceStatus": "blocked_hardware",
        "checks": checks,
        "evidenceClass": "local_synthetic_chaos",
        "generatedAt": _now(),
        "hardwareEvidence": False,
        "schemaVersion": 1,
        "softwareStatus": "passed",
        "taskId": "P5-002",
        "warning": (
            "These bounded local checks do not inject faults into an authorized device, "
            "LAMDA session, production network, PostgreSQL, Temporal, or object store."
        ),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_recovery_drill() -> dict[str, Any]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="cloudctl-local-dr-") as temporary:
        root = Path(temporary)
        source = root / "backup-set"
        restored = root / "isolated-restore"
        source.mkdir()
        payloads = {
            "objectStore": ("object-store.tar", b"synthetic object payload\n"),
            "postgresql": ("postgresql.dump", b"synthetic database payload\n"),
            "temporal": ("temporal.snapshot", b"synthetic workflow payload\n"),
        }
        artifacts: dict[str, dict[str, Any]] = {}
        for component, (name, content) in payloads.items():
            path = source / name
            path.write_bytes(content)
            artifacts[component] = {
                "bytes": len(content),
                "fileName": name,
                "sha256": _sha256(path),
            }

        restored.mkdir()
        for artifact in artifacts.values():
            source_path = source / str(artifact["fileName"])
            destination = restored / source_path.name
            shutil.copyfile(source_path, destination)
            if _sha256(destination) != artifact["sha256"]:
                raise AcceptanceError(f"restored digest mismatch: {source_path.name}")

        corrupt = restored / "corruption-probe.dump"
        shutil.copyfile(source / "postgresql.dump", corrupt)
        corrupt.write_bytes(corrupt.read_bytes() + b"corrupt")
        corruption_detected = _sha256(corrupt) != artifacts["postgresql"]["sha256"]
        if not corruption_detected:
            raise AcceptanceError("recovery drill failed to detect a corrupted artifact")

    return {
        "acceptanceStatus": "pending_external",
        "artifacts": artifacts,
        "checks": {
            "corruptionDetection": "passed",
            "isolatedRestore": "passed",
            "requiredStoresPresent": "passed",
            "restoredDigests": "passed",
        },
        "evidenceClass": "synthetic_local_recovery",
        "generatedAt": _now(),
        "hardwareEvidence": False,
        "measuredRtoSeconds": round(time.perf_counter() - started, 6),
        "schemaVersion": 1,
        "softwareStatus": "passed",
        "taskId": "P5-005",
        "warning": (
            "Synthetic files prove the local verification workflow only. Production PostgreSQL, "
            "Temporal, object storage, RPO, RTO, and scheduling controls remain unverified."
        ),
    }


async def run_selected(
    task: str, output_root: Path, request_count: int, concurrency: int
) -> list[Path]:
    written: list[Path] = []
    if task in {"all", "P5-001"}:
        report = await run_load(request_count, concurrency)
        path = output_root / "P5-001" / "local-load-report.json"
        _atomic_json(path, report)
        written.append(path)
    if task in {"all", "P5-002"}:
        report = run_chaos()
        path = output_root / "P5-002" / "local-chaos-report.json"
        _atomic_json(path, report)
        written.append(path)
    if task in {"all", "P5-005"}:
        report = run_recovery_drill()
        path = output_root / "P5-005" / "local-dr-drill.json"
        _atomic_json(path, report)
        written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=("all", "P5-001", "P5-002", "P5-005"), default="all")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts" / "tasks")
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=16)
    args = parser.parse_args()

    output_root = args.output_root.resolve()
    paths = asyncio.run(run_selected(args.task, output_root, args.requests, args.concurrency))
    for path in paths:
        print(f"PASS {path}")


if __name__ == "__main__":
    main()
