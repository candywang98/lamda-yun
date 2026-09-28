from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.settings import Settings
from cloudctl_domain import ConflictError

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "mobile"
    / "companion"
    / "app"
    / "src"
    / "test"
    / "resources"
    / "claim-maintenance-problem.json"
)


@pytest.mark.asyncio
async def test_conflict_handler_matches_android_maintenance_problem_fixture() -> None:
    expected = json.loads(FIXTURE.read_text())
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))

    @app.get("/__tests__/maintenance-conflict")
    async def maintenance_conflict() -> None:
        raise ConflictError("device is in maintenance and cannot claim tasks")

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/__tests__/maintenance-conflict",
                headers={"X-Request-Id": expected["correlation_id"]},
            )

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == expected
