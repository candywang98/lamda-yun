package com.company.cloudctl.companion.automation

import java.util.concurrent.atomic.AtomicReference

class ExecutionControl {
    private val requested = AtomicReference<String?>(null)

    @Volatile
    var reason: String? = null
        private set

    fun requestPause(reason: String? = null) {
        if (requested.compareAndSet(null, PAUSE_REQUESTED)) {
            this.reason = reason
        }
    }

    fun requestCancel(reason: String? = null) {
        if (requested.compareAndSet(null, CANCEL_REQUESTED)) {
            this.reason = reason
        }
    }

    val pauseRequested: Boolean
        get() = requested.get() == PAUSE_REQUESTED

    val cancelRequested: Boolean
        get() = requested.get() == CANCEL_REQUESTED

    private companion object {
        const val PAUSE_REQUESTED = "PAUSE_REQUESTED"
        const val CANCEL_REQUESTED = "CANCEL_REQUESTED"
    }
}

class TaskPausedException(
    val lastCompletedStepId: String?,
    val lastCompletedStepIndex: Int,
    reason: String?,
) : Exception(reason ?: "TASK_PAUSED")
