"""F12 fleet schedule request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class FleetScheduleCancelRequest(StrictModel):
    reason: str = Field(min_length=3, max_length=500)


class FleetSchedulePollRequest(StrictModel):
    now: datetime | None = None


class FleetScheduleMintRequest(StrictModel):
    """Mint-due is normally invoked by the temporal worker tick.

    ``now`` is injectable for deterministic tests/replays; production callers
    leave it empty and the server uses wall clock.
    """

    now: datetime | None = None


class FleetDueItem(StrictModel):
    scheduleId: str
    periodMarker: str
    scheduledFor: datetime
    timezone: str


class FleetFireView(StrictModel):
    scheduleId: str
    deviceId: str
    scheduledFor: datetime
    scheduledForLocal: str
    periodMarker: str
    status: str
    taskId: str | None = None
    detail: str | None = None


class FleetMintDecisionView(StrictModel):
    periodMarker: str
    scheduledFor: datetime
    action: str  # MINT | SKIP
    detail: str | None = None
    items: list[FleetFireView] = Field(default_factory=list)


class FleetMintDueResponse(StrictModel):
    scheduleId: str
    missPolicy: str
    decisions: list[FleetMintDecisionView]
    taskIds: list[str]
    createdAny: bool


class FleetScheduleCancelResponse(StrictModel):
    scheduleId: str
    status: str
    cancelledAt: datetime | None = None
    cancelledBy: str | None = None
    cancelReason: str | None = None
    # Already-minted tasks are NOT auto-cancelled (F12 §4): each stays on its
    # device/account and is cancelled individually through the existing
    # platform-tasks :cancel route.
    mintedTaskIds: list[str] = Field(default_factory=list)
