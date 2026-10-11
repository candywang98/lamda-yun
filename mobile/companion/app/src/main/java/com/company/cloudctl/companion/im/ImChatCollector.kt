package com.company.cloudctl.companion.im

import com.company.cloudctl.companion.automation.ExecutorFailure
import com.company.cloudctl.companion.automation.LocalAutomationUi
import com.company.cloudctl.companion.automation.TargetLocatorRegistry
import java.time.Instant

/** One screen only. No input, send, history scroll, relaunch, or coordinate fallback. */
class ImChatCollector(
    private val ui: LocalAutomationUi,
    private val checkControl: () -> Unit,
    private val sleep: suspend (Long) -> Unit,
    private val now: () -> Instant = Instant::now,
) {
    private val pkg = TargetLocatorRegistry.XIANYU_PACKAGE
    private fun checkForeground() {
        checkControl()
        if (!ui.isTargetForeground(pkg)) reject("IM_COLLECTION_TARGET_LOST")
    }
    private fun observed() = ui.imChatEvidence(pkg, null)
    private fun verified(peer: String): Boolean {
        checkForeground()
        val evidence = observed()
        checkForeground()
        return evidence?.chatInputVisible == true && evidence.openPeerName?.trim() == peer
    }
    private fun reject(code: String): Nothing = throw ExecutorFailure(code, "IM collection stopped safely")

    suspend fun collect(target: ImChatCollectionTarget, persist: (ImChatCollectionSnapshot) -> Unit) {
        checkForeground()
        val initial = observed() ?: reject("IM_COLLECTION_IDENTITY_UNVERIFIED")
        if (initial.chatInputVisible) {
            if (!verified(target.peerName)) reject("IM_COLLECTION_IDENTITY_UNVERIFIED")
        } else {
            // Bounded verified root navigation. A newly encountered chat is not a license to navigate it.
            var backs = 0
            while (!ui.atRootPage(pkg)) {
                checkForeground()
                if (observed()?.chatInputVisible != false) reject("IM_COLLECTION_IDENTITY_UNVERIFIED")
                if (backs++ >= 3) reject("IM_COLLECTION_NAVIGATION_LIMIT")
                ui.goBack()
                checkForeground()
            }
            checkForeground()
            if (ui.inspect(pkg, "xianyu_messages_tab")?.visible != true) reject("IM_COLLECTION_MESSAGES_UNVERIFIED")
            ui.tap(pkg, "xianyu_messages_tab")
            sleep(400)
            checkForeground()
            if (observed()?.chatInputVisible != false) reject("IM_COLLECTION_IDENTITY_UNVERIFIED")
            // Android adapter resolves exactly one visible node; ambiguity fails before any tap.
            ui.tapText(pkg, target.peerName)
            checkForeground()
            var attempts = 0
            while (true) {
                checkForeground()
                val evidence = observed() ?: reject("IM_COLLECTION_IDENTITY_UNVERIFIED")
                if (evidence.chatInputVisible) {
                    if (!verified(target.peerName)) reject("IM_COLLECTION_IDENTITY_UNVERIFIED")
                    break
                }
                if (attempts++ >= 20) reject("IM_COLLECTION_CHAT_NOT_READY")
                sleep(200)
            }
        }
        if (!verified(target.peerName)) reject("IM_COLLECTION_IDENTITY_UNVERIFIED")
        val bubbles = ui.visibleImChatBubbles(pkg)
        if (!verified(target.peerName)) reject("IM_COLLECTION_IDENTITY_UNVERIFIED")
        val snapshot = ImChatCollectionSnapshot.capture(target.peerName, bubbles, now())
        if (!verified(target.peerName)) reject("IM_COLLECTION_IDENTITY_UNVERIFIED")
        persist(snapshot)
    }
}
