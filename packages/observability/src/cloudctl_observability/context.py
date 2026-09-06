"""Async-safe context propagation for logs, traces, and event metadata."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ObservabilityContext:
    tenant_id: str | None = None
    request_id: str | None = None
    workflow_id: str | None = None
    run_id: str | None = None
    task_run_id: str | None = None
    target_id: str | None = None
    edge_id: str | None = None
    device_id: str | None = None
    automation_version: str | None = None
    lamda_version: str | None = None
    target_app_version: str | None = None


_context: ContextVar[ObservabilityContext | None] = ContextVar(
    "cloudctl_observability_context", default=None
)


def _current_context() -> ObservabilityContext:
    return _context.get() or ObservabilityContext()


def context_fields() -> dict[str, str]:
    return {key: value for key, value in asdict(_current_context()).items() if value is not None}


@contextmanager
def bind_context(**values: str | None) -> Iterator[ObservabilityContext]:
    current = asdict(_current_context())
    current.update({key: value for key, value in values.items() if key in current})
    token: Token[ObservabilityContext | None] = _context.set(ObservabilityContext(**current))
    try:
        yield _current_context()
    finally:
        _context.reset(token)
