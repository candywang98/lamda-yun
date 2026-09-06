"""Temporal worker entry point."""

from __future__ import annotations

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

from .activities import PublishActivities
from .backend import InMemoryActivityBackend
from .workflows import PublishPlanWorkflow, PublishTargetWorkflow


async def run_worker() -> None:
    address = os.getenv("CLOUDCTL_TEMPORAL_ADDRESS", "localhost:7233")
    task_queue = os.getenv("CLOUDCTL_TEMPORAL_TASK_QUEUE", "cloudctl-publish-v1")
    client = await Client.connect(address)
    activities = PublishActivities(InMemoryActivityBackend())
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[PublishPlanWorkflow, PublishTargetWorkflow],
        activities=[
            activities.validate_snapshot,
            activities.acquire_device_lease,
            activities.edge_preflight,
            activities.stage_media,
            activities.run_prepare_steps,
            activities.write_commit_intent,
            activities.commit_once,
            activities.reconcile_result,
            activities.mark_target_state,
            activities.cleanup,
            activities.release_device_lease,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
