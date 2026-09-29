"""Controlled HTTP faults verify reporting, not production failure reproduction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from .harness import run_scenario


@pytest.mark.asyncio
@pytest.mark.parametrize("claim_status", [204, 409, 500])
async def test_guard_exhaustion_reports_remaining_tasks_and_http_statuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, claim_status: int
) -> None:
    original_post = httpx.AsyncClient.post

    async def failed_claim(client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        if url == "/companion/v2/tasks/claim":
            return httpx.Response(
                claim_status,
                request=httpx.Request("POST", f"http://load{url}"),
                content=b"" if claim_status == 204 else b"synthetic claim failure",
            )
        return await original_post(client, url, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", failed_claim)
    result = await run_scenario(
        device_count=1, tasks_per_device=1, scenario_name="exhaustion", report_dir=tmp_path
    )
    outcome = next(iter(result["outcomes"].values()))
    assert outcome.errors, "guard exhaustion must not silently return partial success"
    assert outcome.exit_reason == "guard-exhausted"
    assert outcome.guard_exhausted is True
    assert outcome.claim_attempts == 80
    assert outcome.http_status_counts == {f"claim-{claim_status}": 80}
    assert len(outcome.remaining_task_ids) == 1
    assert outcome.task_states[outcome.remaining_task_ids[0]]["status"] == "QUEUED"
    assert outcome.device_lease is None
    assert outcome.completed == outcome.stranded == 0
    assert any("guard-exhausted:remaining=1;" in error for error in outcome.errors)
    if claim_status != 204:
        assert f"claim-{claim_status}:synthetic claim failure" in outcome.errors
    saved = json.loads((tmp_path / "load-report-exhaustion.json").read_text())
    assert saved == result["report"]
    saved_outcome = saved["outcomes"][outcome.device_id]
    assert saved_outcome["errors"] == outcome.errors
    assert saved_outcome["remainingTaskIds"] == outcome.remaining_task_ids
    assert saved_outcome["taskStates"] == outcome.task_states
    assert saved["db"]["engine"] == "temporary-postgresql"


@pytest.mark.asyncio
async def test_success_response_without_durable_completion_fails_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_post = httpx.AsyncClient.post

    async def unpersisted_completion(
        client: httpx.AsyncClient, url: str, **kwargs: Any
    ) -> httpx.Response:
        if url.endswith("/complete"):
            return httpx.Response(
                200,
                request=httpx.Request("POST", f"http://load{url}"),
                json={"status": "SUCCEEDED"},
            )
        return await original_post(client, url, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", unpersisted_completion)
    result = await run_scenario(device_count=1, tasks_per_device=1, scenario_name="unpersisted")
    outcome = next(iter(result["outcomes"].values()))
    assert outcome.completed == 1  # Client acknowledgement, deliberately not durable truth.
    assert outcome.remaining_task_ids == []
    assert outcome.exit_reason == "failed"
    assert any(error.startswith("completion-not-persisted:") for error in outcome.errors)
    assert outcome.task_states[outcome.completed_task_ids[0]]["status"] == "CLAIMED"
    assert result["report"]["outcomes"][outcome.device_id]["errors"] == outcome.errors


@pytest.mark.asyncio
async def test_failed_completion_keeps_lease_evidence_without_invalid_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_post = httpx.AsyncClient.post
    releases = []

    async def failed_completion(
        client: httpx.AsyncClient, url: str, **kwargs: Any
    ) -> httpx.Response:
        if url.endswith("/release"):
            releases.append(url)
        if url.endswith("/complete"):
            return httpx.Response(
                409,
                request=httpx.Request("POST", f"http://load{url}"),
                content=b"synthetic completion conflict",
            )
        return await original_post(client, url, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", failed_completion)
    result = await run_scenario(device_count=1, tasks_per_device=1, scenario_name="complete-failed")
    outcome = next(iter(result["outcomes"].values()))
    assert outcome.completed == outcome.released == 0
    assert outcome.exit_reason == "incomplete"
    assert outcome.guard_exhausted is False
    assert len(outcome.remaining_task_ids) == 1
    assert outcome.device_lease is not None
    assert outcome.device_lease["canceledAt"] is None
    assert outcome.http_status_counts["complete-409"] == 2
    assert "complete-409:synthetic completion conflict" in outcome.errors
    assert releases == []
