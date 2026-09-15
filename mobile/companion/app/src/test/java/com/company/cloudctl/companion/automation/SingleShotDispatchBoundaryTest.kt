package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class SingleShotDispatchBoundaryTest {
    @Test
    fun stableValidationSubmitsExactlyOnce() {
        var validations = 0
        var submissions = 0

        val accepted = SingleShotDispatchBoundary.dispatch(
            validateImmediatelyBeforeDispatch = { validations++ },
            submit = { submissions++; true },
        )

        assertTrue(accepted)
        assertEquals(1, validations)
        assertEquals(1, submissions)
    }

    @Test
    fun systemRejectionStillSubmitsOnlyOnce() {
        var submissions = 0

        val accepted = SingleShotDispatchBoundary.dispatch(
            validateImmediatelyBeforeDispatch = {},
            submit = { submissions++; false },
        )

        assertFalse(accepted)
        assertEquals(1, submissions)
    }

    @Test
    fun finalWindowChangeRejectsBeforeAnySubmission() {
        var submissions = 0

        val failure = assertFailsWith<ExecutorFailure> {
            SingleShotDispatchBoundary.dispatch(
                validateImmediatelyBeforeDispatch = {
                    throw ExecutorFailure("ACTIVE_WINDOW_CHANGED", "test window changed")
                },
                submit = { submissions++; true },
            )
        }

        assertEquals("ACTIVE_WINDOW_CHANGED", failure.code)
        assertEquals(0, submissions)
    }

    @Test
    fun cancellationDuringFinalValidationRejectsBeforeSubmission() {
        var active = true
        var submissions = 0

        val accepted = SingleShotDispatchBoundary.dispatch(
            validateImmediatelyBeforeDispatch = { active = false },
            canSubmit = { active },
            submit = { submissions++; true },
        )

        assertFalse(accepted)
        assertEquals(0, submissions)
    }

    @Test
    fun noFallbackSubmissionRunsAfterFailure() {
        var submissions = 0
        assertFailsWith<IllegalStateException> {
            SingleShotDispatchBoundary.dispatch(
                validateImmediatelyBeforeDispatch = { error("invalid final snapshot") },
                submit = { submissions++; true },
            )
        }
        assertEquals(0, submissions)
    }
}
