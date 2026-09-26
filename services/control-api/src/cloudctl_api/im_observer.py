"""Bounded, non-durable shadow classification after successful IM commits."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from .im_classifier import ImMessageClassifier, MessageAssessment

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InboundObservation:
    message_id: str
    device_id: str
    platform: str
    title: str = field(repr=False)
    text: str = field(repr=False)


class ImClassificationObserver:
    """Observe new allowlisted messages, never change intake or delivery state."""

    def __init__(self, classifier: ImMessageClassifier, *, capacity: int = 100) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.classifier = classifier
        self._queue: asyncio.Queue[InboundObservation] = asyncio.Queue(maxsize=capacity)
        self._worker: asyncio.Task[None] | None = None

    def start(self) -> None:
        settings = self.classifier.settings
        if settings.im_classifier_enabled and settings.im_classifier_device_ids:
            if self._worker is None:
                self._worker = asyncio.create_task(self._run(), name="im-classifier-shadow")
            logger.info("im_classifier_shadow_started", extra={"fields": {"mode": "SHADOW"}})

    def submit(self, observation: InboundObservation) -> None:
        if (
            self._worker is None
            or self._worker.done()
            or observation.device_id not in self.classifier.settings.im_classifier_device_ids
        ):
            return
        try:
            self._queue.put_nowait(observation)
        except asyncio.QueueFull:
            self._record(observation, MessageAssessment(status="QUEUE_FULL"))

    @staticmethod
    def _record(observation: InboundObservation, assessment: MessageAssessment) -> None:
        logger.info(
            "im_classifier_shadow",
            extra={
                "fields": {
                    "mode": "SHADOW",
                    "messageId": observation.message_id,
                    "deviceId": observation.device_id,
                    "category": assessment.category,
                    "confidence": assessment.confidence,
                    "classificationStatus": assessment.status,
                    "httpStatus": assessment.http_status,
                }
            },
        )

    async def _run(self) -> None:
        while True:
            observation = await self._queue.get()
            try:
                assessment = await self.classifier.classify(
                    platform=observation.platform,
                    title=observation.title,
                    text=observation.text,
                )
                self._record(observation, assessment)
            except asyncio.CancelledError:
                self._record(observation, MessageAssessment(status="SHUTDOWN"))
                raise
            except Exception:
                # Exception text may contain notification data or provider credentials.
                self._record(observation, MessageAssessment(status="INTERNAL_ERROR"))
            finally:
                self._queue.task_done()

    async def close(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        while not self._queue.empty():
            observation = self._queue.get_nowait()
            self._record(observation, MessageAssessment(status="SHUTDOWN"))
            self._queue.task_done()
