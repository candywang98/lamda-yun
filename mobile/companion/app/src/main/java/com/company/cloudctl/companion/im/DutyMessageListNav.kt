package com.company.cloudctl.companion.im

import kotlinx.coroutines.delay

/**
 * Duty-mode navigation decision (duty-anchor gap 3): parking the phone on the
 * xianyu message list must go through the verified "消息，未读消息数" tab anchor.
 * The legacy fixed screen coordinate is a last resort only, because a keyboard
 * or layout shift moved that point onto IME keys (a stray "2" was once typed
 * and sent into a chat). The fallback fires at most once per execution, only
 * when the phone is verifiably not on the message list, and is always audited
 * through the DUTY_NAV_COORD_FALLBACK event.
 */
internal class DutyMessageListNav(private val port: Port) {
    interface Port {
        /** True when the message list is already on screen. */
        fun onMessageList(): Boolean

        /** Resolves the tab anchor and gesture-taps its node center. */
        suspend fun tapMessagesTabAnchor(): Boolean

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
        // The anchor resolved to nothing. The coordinate fallback may only fire
        // when the phone is still verifiably off the message list.
        if (port.onMessageList()) return true
        port.event(COORD_FALLBACK_EVENT)
        port.tapCoordinate(FALLBACK_X, FALLBACK_Y)
        port.settle()
        return port.onMessageList()
    }

    companion object {
        const val COORD_FALLBACK_EVENT = "DUTY_NAV_COORD_FALLBACK"

        /** Verified 消息 tab coordinate family (device acceptance 2026-09-13). */
        const val FALLBACK_X = 975.0
        const val FALLBACK_Y = 2331.0
        private const val SETTLE_MS = 2_000L
    }
}
