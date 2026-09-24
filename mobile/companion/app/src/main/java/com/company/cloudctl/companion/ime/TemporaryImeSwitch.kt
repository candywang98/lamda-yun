package com.company.cloudctl.companion.ime

import kotlinx.coroutines.delay

/**
 * Outcome of putting the user's keyboard back. [leftUserChoice] means a third
 * IME was selected during the transaction and was deliberately not overwritten.
 */
internal data class ImeRestoreReport(
    val restored: Boolean,
    val leftUserChoice: Boolean,
    val observedId: String?,
)

/**
 * Reads and switches the default input method by id. Implementations must not
 * disable an IME: enabling is a persistent side effect this transaction refuses
 * to take on its own.
 */
internal interface ImeSwitcher {
    fun currentDefaultId(): String?
    fun cloudCtlIds(): Set<String>
    /** True only after the platform reports [id] as the selected input method. */
    fun switchTo(id: String): Boolean
    fun observeSelectedId(): String?
}

internal class TemporaryImeSwitch(
    private val switcher: ImeSwitcher,
    private val pause: suspend () -> Unit = { delay(50) },
    private val observeAttempts: Int = 8,
    private val onEngaged: (() -> Unit)? = null,
) {
    /**
     * Switches to CloudCtl for [block] and always attempts to restore.
     *
     * A user who picks a third IME mid-transaction keeps that choice: the block
     * fails with [USER_INTERFERENCE] and restore does not overwrite it. A failed
     * restore is recorded and surfaced; the block's success is never reported
     * when the original keyboard did not come back.
     */
    suspend fun <T> around(block: suspend () -> T): T {
        val original = switcher.currentDefaultId()?.takeIf { it.isNotBlank() }
            ?: fail("INPUT_IME_REQUIRED", "The current keyboard id could not be read")
        val ours = switcher.cloudCtlIds()
        if (ours.isEmpty()) fail("INPUT_IME_REQUIRED", "CloudCtl Input is not enabled")
        val startedAsOurs = original in ours
        if (!startedAsOurs) {
            val targetId = ours.first()
            if (!switcher.switchTo(targetId) || !awaitSelected(ours)) {
                // The switch itself failed. Still try to put the original id back
                // in case the platform moved part-way, then refuse the write.
                val rollback = restore(original, ours)
                if (!rollback.restored && !rollback.leftUserChoice) {
                    fail("IME_RESTORE_FAILED", "Temporary keyboard switch failed and the original keyboard was not restored")
                }
                fail("INPUT_IME_REQUIRED", "CloudCtl Input could not be selected for this field")
            }
        }
        var blockError: Throwable? = null
        var result: T? = null
        try {
            val selected = switcher.observeSelectedId()
            if (selected !in ours) {
                fail("USER_INTERFERENCE", "The keyboard changed before input started")
            }
            onEngaged?.invoke()
            result = block()
        } catch (error: Throwable) {
            blockError = error
        } finally {
            // Cancellation and failure both reach here: the original id is restored
            // unless the user already picked a different keyboard.
        }
        if (startedAsOurs) {
            blockError?.let { throw it }
            @Suppress("UNCHECKED_CAST")
            return result as T
        }
        val report = restore(original, ours)
        when {
            report.leftUserChoice -> fail(
                "USER_INTERFERENCE",
                "The user selected another keyboard; that choice was kept",
            )
            !report.restored -> fail(
                "IME_RESTORE_FAILED",
                "The original keyboard ${original} was not restored (now ${report.observedId ?: "unknown"})",
            )
        }
        blockError?.let { throw it }
        @Suppress("UNCHECKED_CAST")
        return result as T
    }

    private suspend fun restore(original: String, ours: Set<String>): ImeRestoreReport {
        val now = switcher.observeSelectedId()
        if (now != null && now != original && now !in ours) {
            return ImeRestoreReport(restored = false, leftUserChoice = true, observedId = now)
        }
        val switched = switcher.switchTo(original)
        val observed = if (switched) awaitId(original) else switcher.observeSelectedId()
        return ImeRestoreReport(
            restored = observed == original,
            leftUserChoice = false,
            observedId = observed,
        )
    }

    private suspend fun awaitSelected(ids: Set<String>): Boolean {
        repeat(observeAttempts) {
            if (switcher.observeSelectedId() in ids) return true
            pause()
        }
        return switcher.observeSelectedId() in ids
    }

    private suspend fun awaitId(id: String): String? {
        var seen = switcher.observeSelectedId()
        repeat(observeAttempts) {
            if (seen == id) return seen
            pause()
            seen = switcher.observeSelectedId()
        }
        return seen
    }

    private fun fail(code: String, message: String): Nothing =
        throw com.company.cloudctl.companion.automation.ExecutorFailure(code, message)
}
