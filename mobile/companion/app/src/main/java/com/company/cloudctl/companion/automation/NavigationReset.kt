package com.company.cloudctl.companion.automation

/** Bounded navigation policy; the port owns Android I/O, cancellation and time. */
internal class NavigationReset(private val port: Port) {
    interface Port {
        fun atRootPage(): Boolean
        fun isTargetForeground(): Boolean
        /** Atomically recognizes and gesture-taps one allowlisted safe button, or returns null. */
        suspend fun dismissBlockedDialog(): String?
        suspend fun goBack()
        suspend fun relaunch()
        suspend fun settle(ms: Long)
        fun checkpoint()
        fun event(code: String)
    }

    suspend fun execute() {
        var dismissed = 0
        suspend fun recoverRoot(): Boolean {
            port.checkpoint()
            if (port.atRootPage()) return true
            while (dismissed < MAX_DIALOGS && port.isTargetForeground()) {
                port.checkpoint()
                val label = port.dismissBlockedDialog() ?: break
                dismissed++
                port.event("NAV_DIALOG_DISMISSED label=$label")
                port.settle(DIALOG_SETTLE_MS)
                port.checkpoint()
                if (port.atRootPage()) return true
            }
            return false
        }

        if (recoverRoot()) return
        port.event("NAV_RESET_BACK")
        repeat(MAX_BACKS) {
            if (recoverRoot()) return
            if (!port.isTargetForeground()) return@repeat
            port.checkpoint()
            port.goBack()
        }
        if (recoverRoot()) return
        port.checkpoint()
        port.event("NAV_RESET_RELAUNCH")
        port.relaunch()
        repeat(RELAUNCH_POLLS) {
            if (recoverRoot()) return
            port.settle(POLL_MS)
        }
        if (!recoverRoot()) {
            throw ExecutorFailure("NAV_RESET_FAILED", "Target app could not be returned to its root page")
        }
    }

    companion object {
        const val MAX_DIALOGS = 3
        const val DIALOG_SETTLE_MS = 800L
        private const val MAX_BACKS = 5
        private const val RELAUNCH_POLLS = 12
        private const val POLL_MS = 500L
    }
}
