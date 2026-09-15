package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class SingleShotGestureGuardTest {
    private val action = GuardedDialogLocator.Candidate(
        bounds = GuardedDialogLocator.Bounds(540, 1292, 999, 1436),
        visible = true,
        enabled = true,
        clickable = true,
    )

    private fun snapshot(
        windowId: Int? = 42,
        packageName: String? = TargetLocatorRegistry.XIANYU_PACKAGE,
        candidate: GuardedDialogLocator.Candidate? = action,
    ) = SingleShotGestureGuard.Snapshot(
        windowId = windowId,
        packageName = packageName,
        titleCandidates = if (candidate == null) 0 else 1,
        cancelCandidates = if (candidate == null) 0 else 1,
        actionCandidates = if (candidate == null) 0 else 1,
        action = candidate,
    )

    @Test
    fun stableActiveWindowAndBoundsAllowOneDispatchPoint() {
        val ready = assertIs<SingleShotGestureGuard.Outcome.Allowed>(
            SingleShotGestureGuard.validate(
                TargetLocatorRegistry.XIANYU_PACKAGE,
                snapshot(),
                snapshot(),
            ),
        ).ready

        assertEquals(42, ready.windowId)
        assertEquals(action.bounds, ready.bounds)
        assertEquals(769.5f, ready.centerX)
        assertEquals(1364f, ready.centerY)
    }

    @Test
    fun activeWindowChangeFailsBeforeDispatch() {
        assertRejected("ACTIVE_WINDOW_CHANGED", snapshot(windowId = 42), snapshot(windowId = 43))
    }

    @Test
    fun packageChangeFailsBeforeDispatch() {
        assertRejected("WRONG_ACTIVE_PACKAGE", snapshot(), snapshot(packageName = "other.package"))
    }

    @Test
    fun missingActiveWindowFailsBeforeDispatch() {
        assertRejected("ACTIVE_WINDOW_MISSING", snapshot(), snapshot(windowId = null))
    }

    @Test
    fun dialogDisappearanceFailsBeforeDispatch() {
        assertRejected("DIALOG_GUARD_REJECTED", snapshot(), snapshot(candidate = null))
    }

    @Test
    fun actionBoundsChangeFailsBeforeDispatch() {
        val moved = action.copy(bounds = GuardedDialogLocator.Bounds(541, 1292, 1000, 1436))
        assertRejected("ACTION_BOUNDS_CHANGED", snapshot(), snapshot(candidate = moved))
    }

    @Test
    fun disabledOrDegenerateActionFailsBeforeDispatch() {
        assertRejected("NODE_NOT_CLICKABLE", snapshot(), snapshot(candidate = action.copy(enabled = false)))
        val empty = action.copy(bounds = GuardedDialogLocator.Bounds(540, 1292, 540, 1436))
        assertRejected("ACTION_BOUNDS_CHANGED", snapshot(), snapshot(candidate = empty))
        assertRejected("ACTION_BOUNDS_INVALID", snapshot(candidate = empty), snapshot(candidate = empty))
    }

    private fun assertRejected(
        code: String,
        first: SingleShotGestureGuard.Snapshot,
        second: SingleShotGestureGuard.Snapshot,
    ) {
        val rejected = assertIs<SingleShotGestureGuard.Outcome.Rejected>(
            SingleShotGestureGuard.validate(TargetLocatorRegistry.XIANYU_PACKAGE, first, second),
        )
        assertEquals(code, rejected.code)
    }
}
