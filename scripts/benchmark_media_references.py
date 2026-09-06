"""Repeatable local SQLite API benchmark; not a production capacity claim."""

from __future__ import annotations

import asyncio
import json
import math
import platform
import statistics
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx
from cloudctl_api.app import create_app
from cloudctl_api.db import ContentItemRow, ContentRevisionMediaRow, ContentRevisionRow, MediaAssetRow
from cloudctl_api.settings import Settings
from sqlalchemy import insert, text

TENANT = "00000000-0000-7000-8000-000000000111"
USER = "00000000-0000-7000-8000-000000000222"


async def measure(size: int, matches: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="cloudctl-benchmark-") as directory:
        app = create_app(Settings(
            env="test", repository_mode="sqlite", sqlite_path=Path(directory) / "bench.db",
            dev_auth_bypass=True,
        ))
        async with app.router.lifespan_context(app):
            database = app.state.database
            now = datetime.now(UTC)
            async with database.unit_of_work() as session:
                await session.execute(insert(MediaAssetRow), [
                    dict(id=name, tenant_id=TENANT, sha256=digest * 64, object_key=name,
                         content_type="image/jpeg", size_bytes=32, metadata_json={}, created_at=now)
                    for name, digest in (("target", "a"), ("other", "b"))
                ])
                await session.execute(insert(ContentItemRow), [
                    dict(id="content", tenant_id=TENANT, title="Benchmark", created_by=USER,
                         status="ACTIVE", created_at=now)
                ])
                for start in range(0, size, 500):
                    indexes = range(start, min(start + 500, size))
                    await session.execute(insert(ContentRevisionRow), [
                        dict(id=f"revision-{i:08}", tenant_id=TENANT, content_id="content",
                             revision_no=i + 1, payload={"mediaAssetIds": ["target" if i < matches else "other"]},
                             payload_sha256="c" * 64, created_by=USER, created_at=now)
                        for i in indexes
                    ])
                    await session.execute(insert(ContentRevisionMediaRow), [
                        dict(id=f"reference-{i:08}", tenant_id=TENANT, content_id="content",
                             content_revision_id=f"revision-{i:08}",
                             media_asset_id="target" if i < matches else "other", created_at=now)
                        for i in indexes
                    ])
            async with database.engine.connect() as connection:
                await connection.execute(text("ANALYZE"))
                plan = [list(row) for row in await connection.execute(text(
                    "EXPLAIN QUERY PLAN SELECT * FROM content_revision_media "
                    "WHERE tenant_id = :tenant AND media_asset_id = :asset"
                ), {"tenant": TENANT, "asset": "target"})]
                version = await connection.scalar(text("SELECT sqlite_version()"))
            headers = {"X-Tenant-Id": TENANT, "X-User-Id": USER, "X-Roles": "viewer", "X-MFA": "false"}
            timings = []
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://benchmark", trust_env=False,
            ) as client:
                for iteration in range(35):
                    start = perf_counter()
                    response = await client.get("/api/v1/media/assets/target/references", headers=headers)
                    elapsed = (perf_counter() - start) * 1000
                    response.raise_for_status()
                    assert len(response.json()["contentReferences"]) == matches
                    if iteration >= 5:
                        timings.append(elapsed)
            return dict(rows=size, matches=matches, samples=len(timings), warmup=5,
                        p50_ms=round(statistics.median(timings), 3),
                        p95_ms=round(sorted(timings)[math.ceil(len(timings) * .95) - 1], 3),
                        max_ms=round(max(timings), 3), sqlite_version=version,
                        query_plan=plan)


async def main() -> None:
    result = dict(measured_at=datetime.now(UTC).isoformat(), python=platform.python_version(),
                  system=platform.platform(), database="temporary file-backed SQLite",
                  concurrency=1, transport="in-process ASGI", cases=[])
    for size, matches in ((1000, 10), (10000, 10), (1000, 1000)):
        result["cases"].append(await measure(size, matches))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
