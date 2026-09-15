package com.company.cloudctl.companion.automation

object GuardedDialogLocator {
    data class Bounds(val left: Int, val top: Int, val right: Int, val bottom: Int)

    data class Candidate(
        val bounds: Bounds,
        val visible: Boolean,
        val enabled: Boolean,
        val clickable: Boolean,
    )

    fun uniqueAction(
        titles: List<Candidate>,
        cancels: List<Candidate>,
        actions: List<Candidate>,
    ): Candidate? {
        val visibleTitles = titles.filter { it.visible }
        val enabledCancels = cancels.filter { it.visible && it.enabled }
        val clickableActions = actions.filter { it.visible && it.enabled && it.clickable }
        if (visibleTitles.size != 1 || enabledCancels.size != 1 || clickableActions.size != 1) return null

        val title = visibleTitles.single().bounds
        val cancel = enabledCancels.single().bounds
        val action = clickableActions.single().bounds
        val sameButtonRow = cancel.top == action.top && cancel.bottom == action.bottom
        return clickableActions.single().takeIf {
            title.bottom <= action.top && sameButtonRow && cancel.right <= action.left
        }
    }
}
