"""Deployment-aware capability registry for Operations executors."""

from __future__ import annotations

from typing import Literal

from .operation_catalog import BY_KEY
from .settings import Settings

BUILTIN_OPERATION_KEYS = frozenset(
    {
        "publish_plans.snapshot.validate",
        "works.revision.validate",
        "xianyu.listing.publish",
    }
)


class OperationExecutorRegistry:
    """Reports only executors that this deployment can actually invoke."""

    def __init__(self, settings: Settings) -> None:
        configured = frozenset(settings.operation_executor_urls)
        unknown = configured - BY_KEY.keys()
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"unknown operation executor keys: {names}")
        self._available = BUILTIN_OPERATION_KEYS | configured

    @property
    def available_keys(self) -> frozenset[str]:
        return self._available

    def available(self, operation_key: str) -> bool:
        return operation_key in self._available

    def execution_state(self, operation_key: str) -> Literal["implemented", "contract_only"]:
        return "implemented" if self.available(operation_key) else "contract_only"
