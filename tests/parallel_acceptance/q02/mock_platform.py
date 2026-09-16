"""Mock platform readback stub for Q02 scenario 2 (class A).

The controlled platforms (xianyu first) verify a gated destructive action by
reading state back from the platform UI, never by trusting the click itself:

- badge readback: the numeric badge on ``xianyu_pub_tab_onsale`` must change by
  the frozen delta of the maintenance shape (delist: -1) after the gated
  confirm; a delete has no numeric badge, so the confirm-dialog dismissal plus
  screenshots/operator resolution carry the verification instead;
- postcondition readback: the publish-success node (``xianyu_publish_success``)
  must be observed after the gated publish tap.

This stub plays the "platform server" for the class-A suite: it hands out
before/after observations and decides the outcome verdict the companion is
allowed to report. The real-device variant (class B) replaces the stub with
the actual on-device readback; see artifacts/parallel/W5/Q02/README.md.
"""

from __future__ import annotations

from typing import Literal

OutcomeStatus = Literal["APPLIED", "UNKNOWN"]

DELIST_BADGE_LOCATOR = "xianyu_pub_tab_onsale"
DELIST_EXPECTED_DELTA = -1
PUBLISH_POSTCONDITION = "xianyu_publish_success"


class BadgeReadbackStub:
    """Numeric badge readback (delist shape: expectedDelta -1)."""

    def __init__(self, *, badge_before: int, badge_after: int) -> None:
        self.badge_before = badge_before
        self.badge_after = badge_after

    def before_evidence(self) -> str:
        return f"{DELIST_BADGE_LOCATOR}@before={self.badge_before}"

    def observed_delta(self) -> int:
        return self.badge_after - self.badge_before

    def verdict(self) -> tuple[OutcomeStatus, str]:
        """Verdict the companion may report after its sole readback."""
        if self.observed_delta() == DELIST_EXPECTED_DELTA:
            return "APPLIED", f"{DELIST_BADGE_LOCATOR}@after={self.badge_after}"
        return "UNKNOWN", (
            f"{DELIST_BADGE_LOCATOR}@after={self.badge_after}"
            f":observedDelta={self.observed_delta()}"
            f":expected={DELIST_EXPECTED_DELTA}:readback-inconclusive"
        )


class PostconditionReadbackStub:
    """Node-presence readback (publish shape: xianyu_publish_success)."""

    def __init__(self, *, postcondition_present: bool) -> None:
        self.postcondition_present = postcondition_present

    def before_evidence(self) -> str:
        return f"{PUBLISH_POSTCONDITION}@before=absent"

    def verdict(self) -> tuple[OutcomeStatus, str]:
        if self.postcondition_present:
            return "APPLIED", f"{PUBLISH_POSTCONDITION}@after=present"
        return "UNKNOWN", f"{PUBLISH_POSTCONDITION}@after=absent:readback-inconclusive"
