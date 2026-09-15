package com.company.cloudctl.companion.automation

object SingleShotGestureGuard {
    data class Snapshot(
        val windowId: Int?,
        val packageName: String?,
        val titleCandidates: Int,
        val cancelCandidates: Int,
        val actionCandidates: Int,
        val action: GuardedDialogLocator.Candidate?,
    )

    data class Ready(
        val windowId: Int,
        val bounds: GuardedDialogLocator.Bounds,
        val centerX: Float,
        val centerY: Float,
    )

    sealed interface Outcome {
        data class Allowed(val ready: Ready) : Outcome
        data class Rejected(val code: String) : Outcome
    }

    fun validate(
        expectedPackage: String,
        first: Snapshot,
        second: Snapshot,
    ): Outcome {
        if (first.packageName != expectedPackage || second.packageName != expectedPackage) {
            return Outcome.Rejected("WRONG_ACTIVE_PACKAGE")
        }
        val firstWindow = first.windowId ?: return Outcome.Rejected("ACTIVE_WINDOW_MISSING")
        val secondWindow = second.windowId ?: return Outcome.Rejected("ACTIVE_WINDOW_MISSING")
        if (firstWindow != secondWindow) return Outcome.Rejected("ACTIVE_WINDOW_CHANGED")

        val firstAction = first.action ?: return Outcome.Rejected("DIALOG_GUARD_REJECTED")
        val secondAction = second.action ?: return Outcome.Rejected("DIALOG_GUARD_REJECTED")
        if (!isSafe(firstAction) || !isSafe(secondAction)) {
            return Outcome.Rejected("NODE_NOT_CLICKABLE")
        }
        if (firstAction.bounds != secondAction.bounds) {
            return Outcome.Rejected("ACTION_BOUNDS_CHANGED")
        }

        val bounds = secondAction.bounds
        val width = bounds.right - bounds.left
        val height = bounds.bottom - bounds.top
        if (width <= 0 || height <= 0) return Outcome.Rejected("ACTION_BOUNDS_INVALID")
        return Outcome.Allowed(
            Ready(
                windowId = secondWindow,
                bounds = bounds,
                centerX = (bounds.left + bounds.right) / 2f,
                centerY = (bounds.top + bounds.bottom) / 2f,
            ),
        )
    }

    private fun isSafe(candidate: GuardedDialogLocator.Candidate): Boolean =
        candidate.visible && candidate.enabled && candidate.clickable
}
