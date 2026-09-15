package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class GuardedDialogLocatorTest {
    private fun candidate(
        left: Int,
        top: Int,
        right: Int,
        bottom: Int,
        visible: Boolean = true,
        enabled: Boolean = true,
        clickable: Boolean = false,
    ) = GuardedDialogLocator.Candidate(
        GuardedDialogLocator.Bounds(left, top, right, bottom),
        visible,
        enabled,
        clickable,
    )

    private val title = candidate(297, 1111, 783, 1198)
    private val cancel = candidate(81, 1292, 540, 1436, clickable = true)
    private val action = candidate(540, 1292, 999, 1436, clickable = true)

    @Test
    fun acceptsTheDeviceVerifiedDeleteDialogTriplet() {
        assertEquals(action, GuardedDialogLocator.uniqueAction(listOf(title), listOf(cancel), listOf(action)))
    }

    @Test
    fun rejectsMissingOrDuplicateDialogContext() {
        assertNull(GuardedDialogLocator.uniqueAction(emptyList(), listOf(cancel), listOf(action)))
        assertNull(GuardedDialogLocator.uniqueAction(listOf(title), listOf(cancel), listOf(action, action)))
    }

    @Test
    fun rejectsDisabledOrNonClickableConfirmation() {
        assertNull(
            GuardedDialogLocator.uniqueAction(
                listOf(title),
                listOf(cancel),
                listOf(action.copy(enabled = false)),
            ),
        )
        assertNull(
            GuardedDialogLocator.uniqueAction(
                listOf(title),
                listOf(cancel),
                listOf(action.copy(clickable = false)),
            ),
        )
    }

    @Test
    fun rejectsWrongButtonOrderOrRows() {
        val actionOnLeft = action.copy(bounds = GuardedDialogLocator.Bounds(0, 1292, 400, 1436))
        val cancelOnRight = cancel.copy(bounds = GuardedDialogLocator.Bounds(500, 1292, 999, 1436))
        assertNull(GuardedDialogLocator.uniqueAction(listOf(title), listOf(cancelOnRight), listOf(actionOnLeft)))
        assertNull(
            GuardedDialogLocator.uniqueAction(
                listOf(title),
                listOf(cancel),
                listOf(action.copy(bounds = GuardedDialogLocator.Bounds(540, 1300, 999, 1444))),
            ),
        )
    }
}
