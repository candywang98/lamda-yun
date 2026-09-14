package com.company.cloudctl.companion.im

import kotlinx.coroutines.delay

/**
 * Duty-mode navigation decision. Device evidence 2026-09-14 closed two gaps:
 *
 * - The 消息 tab anchor must match every verified tab form (unread
 *   "消息，未读消息数N…", "消息，未选中状态", "消息，选中状态"); the anchor is
 *   multi-form at the locator layer, so this port just resolves it.
 * - From a chat page the anchor never resolves (inner pages hide the bottom tab
 *   bar), so before any coordinate fallback the nav backs out of inner pages a
 *   bounded number of times and retries the anchor after each back.
 *
 * The legacy fixed screen coordinate stays the audited last resort only: the
 * keyboard or a layout shift once moved that point onto IME keys (a stray "2"
 * was typed and sent into a chat). The fallback fires at most once per
 * execution, only when the phone is verifiably not on the message list, and is
 * always audited through the DUTY_NAV_COORD_FALLBACK event.
 */
internal class DutyMessageListNav(private val port: Port) {
    interface Port {
        /** True when the message list is already on screen. */
        fun onMessageList(): Boolean

        /** Resolves the (multi-form) tab anchor and gesture-taps its node center. */
        suspend fun tapMessagesTabAnchor(): Boolean

        /** performGlobalAction(GLOBAL_ACTION_BACK) to close an inner page. */
        fun goBack()

        /** The audited last-resort tap at the fixed verified coordinate. */
        suspend fun tapCoordinate(x: Double, y: Double)

        fun event(code: String)
        suspend fun settle() { delay(SETTLE_MS) }
    }

    suspend fun execute(): Boolean {
        if (port.onMessageList()) return true
        if (port.tapMessagesTabAnchor()) {
            port.settle()
            return true
        }
        // The anchor resolved to nothing: an inner page (chat, detail, sheet) is
        // probably covering the tab bar. Back out — bounded, settled — and retry
        // the anchor (and the list check) after each back.
        repeat(BACK_ATTEMPTS) {
            port.event(BACK_EVENT)
            port.goBack()
            delay(BACK_SETTLE_MS)
            if (port.onMessageList()) return true
            if (port.tapMessagesTabAnchor()) {
                port.settle()
                return true
            }
        }
        // The coordinate fallback may only fire when the phone is still
        // verifiably off the message list (the port also guards foreground).
        if (port.onMessageList()) return true
        port.event(COORD_FALLBACK_EVENT)
        port.tapCoordinate(FALLBACK_X, FALLBACK_Y)
        port.settle()
        return port.onMessageList()
    }

    companion object {
        const val COORD_FALLBACK_EVENT = "DUTY_NAV_COORD_FALLBACK"
        const val BACK_EVENT = "DUTY_NAV_BACK"

        /** Verified 消息 tab coordinate family (device acceptance 2026-09-13). */
        const val FALLBACK_X = 975.0
        const val FALLBACK_Y = 2331.0
        private const val SETTLE_MS = 2_000L

        /** Bounded BACK presses to resurface the tab bar (device evidence 2026-09-14). */
        private const val BACK_ATTEMPTS = 2
        private const val BACK_SETTLE_MS = 800L
    }
}
