from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock

import pytest
from cloudctl_api.im_classifier import ImMessageClassifier, MessageAssessment
from cloudctl_api.im_observer import ImClassificationObserver, InboundObservation
from cloudctl_api.settings import Settings


def observer(*, enabled=True, devices=None, capacity=100):
    settings = Settings(
        env="test",
        im_classifier_enabled=enabled,
        im_classifier_device_ids=["device-one"] if devices is None else devices,
        im_classifier_base_url="https://classifier.example/v1",
        im_classifier_api_key="synthetic-key",
    )
    classifier = ImMessageClassifier(settings)
    classifier.classify = AsyncMock(return_value=MessageAssessment(status="NEEDS_REVIEW"))
    return ImClassificationObserver(classifier, capacity=capacity)


def observation(device="device-one"):
    return InboundObservation("message-one", device, "xianyu", "Private buyer", "Private text")


@pytest.mark.parametrize("enabled,devices", [(False, ["device-one"]), (True, [])])
async def test_disabled_or_empty_allowlist_never_starts(enabled, devices):
    item = observer(enabled=enabled, devices=devices)
    item.start()
    item.submit(observation())
    assert item._worker is None
    item.classifier.classify.assert_not_called()
    await item.close()


async def test_only_allowlisted_device_is_sent_and_logs_exclude_content(caplog):
    caplog.set_level(logging.INFO)
    item = observer()
    item.start()
    item.submit(observation("other-device"))
    item.submit(observation())
    await asyncio.wait_for(item._queue.join(), 1)
    item.classifier.classify.assert_awaited_once_with(
        platform="xianyu", title="Private buyer", text="Private text"
    )
    records = [record for record in caplog.records if record.message == "im_classifier_shadow"]
    assert records[0].fields["classificationStatus"] == "NEEDS_REVIEW"
    assert records[0].fields["messageId"] == "message-one"
    assert "Private" not in str(records[0].fields)
    assert "Private" not in repr(observation())
    await item.close()
    assert item._worker is None


async def test_queue_full_is_nonblocking_and_never_sends_overflow(caplog):
    caplog.set_level(logging.INFO)
    item = observer(capacity=1)
    item.start()
    item.submit(observation())
    item.submit(observation())
    assert any(
        getattr(record, "fields", {}).get("classificationStatus") == "QUEUE_FULL"
        for record in caplog.records
    )
    await asyncio.wait_for(item._queue.join(), 1)
    item.classifier.classify.assert_awaited_once()
    await item.close()


async def test_provider_exception_does_not_kill_worker_or_log_exception(caplog):
    caplog.set_level(logging.INFO)
    item = observer()
    item.classifier.classify.side_effect = [
        RuntimeError("Private text synthetic-key"),
        MessageAssessment(category="PROMOTION", status="CLASSIFIED", confidence=1.0),
    ]
    item.start()
    item.submit(observation())
    item.submit(observation())
    await asyncio.wait_for(item._queue.join(), 1)
    states = [
        getattr(record, "fields", {}).get("classificationStatus") for record in caplog.records
    ]
    assert "INTERNAL_ERROR" in states
    assert "CLASSIFIED" in states
    assert "Private" not in caplog.text
    assert "synthetic-key" not in caplog.text
    await item.close()


async def test_shutdown_cancels_inflight_and_clears_queue(caplog):
    caplog.set_level(logging.INFO)
    item = observer()
    started = asyncio.Event()

    async def blocked(**kwargs):
        started.set()
        await asyncio.Event().wait()

    item.classifier.classify.side_effect = blocked
    item.start()
    item.submit(observation())
    item.submit(observation())
    await asyncio.wait_for(started.wait(), 1)
    await asyncio.wait_for(item.close(), 1)
    await asyncio.wait_for(item._queue.join(), 1)
    assert item._queue.empty()
    assert (
        sum(
            getattr(record, "fields", {}).get("classificationStatus") == "SHUTDOWN"
            for record in caplog.records
        )
        == 2
    )


def test_queue_capacity_cannot_be_unbounded():
    with pytest.raises(ValueError, match="capacity"):
        observer(capacity=0)
