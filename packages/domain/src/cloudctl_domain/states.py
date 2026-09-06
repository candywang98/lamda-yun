"""Publish state machine and safe cancellation rules."""

from enum import StrEnum

from .errors import ConflictError


class PublishState(StrEnum):
    DRAFT = "DRAFT"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SCHEDULED = "SCHEDULED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    COMMITTING = "COMMITTING"
    RECONCILING = "RECONCILING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CANCELED = "CANCELED"


TERMINAL_STATES = frozenset(
    {PublishState.SUCCEEDED, PublishState.FAILED, PublishState.UNKNOWN, PublishState.CANCELED}
)
SAFE_CANCEL_STATES = frozenset(
    {
        PublishState.DRAFT,
        PublishState.AWAITING_APPROVAL,
        PublishState.SCHEDULED,
        PublishState.QUEUED,
        PublishState.RUNNING,
        PublishState.WAITING_CONFIRMATION,
    }
)
ALLOWED_TRANSITIONS: dict[PublishState, frozenset[PublishState]] = {
    PublishState.DRAFT: frozenset({PublishState.AWAITING_APPROVAL, PublishState.SCHEDULED}),
    PublishState.AWAITING_APPROVAL: frozenset(
        {PublishState.SCHEDULED, PublishState.FAILED, PublishState.CANCELED}
    ),
    PublishState.SCHEDULED: frozenset({PublishState.QUEUED, PublishState.CANCELED}),
    PublishState.QUEUED: frozenset(
        {PublishState.RUNNING, PublishState.FAILED, PublishState.CANCELED}
    ),
    PublishState.RUNNING: frozenset(
        {
            PublishState.WAITING_CONFIRMATION,
            PublishState.COMMITTING,
            PublishState.FAILED,
            PublishState.CANCELED,
        }
    ),
    PublishState.WAITING_CONFIRMATION: frozenset(
        {PublishState.COMMITTING, PublishState.FAILED, PublishState.CANCELED}
    ),
    PublishState.COMMITTING: frozenset({PublishState.RECONCILING}),
    PublishState.RECONCILING: frozenset(
        {PublishState.SUCCEEDED, PublishState.FAILED, PublishState.UNKNOWN}
    ),
    PublishState.SUCCEEDED: frozenset(),
    PublishState.FAILED: frozenset(),
    PublishState.UNKNOWN: frozenset({PublishState.SUCCEEDED, PublishState.FAILED}),
    PublishState.CANCELED: frozenset(),
}


def assert_publish_transition(current: PublishState, requested: PublishState) -> None:
    if requested not in ALLOWED_TRANSITIONS[current]:
        raise ConflictError(f"invalid publish transition: {current} -> {requested}")


def assert_safe_cancel(current: PublishState) -> None:
    if current not in SAFE_CANCEL_STATES:
        raise ConflictError(f"publish cannot be canceled safely while {current}")
