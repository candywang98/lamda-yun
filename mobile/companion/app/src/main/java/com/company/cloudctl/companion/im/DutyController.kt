package com.company.cloudctl.companion.im

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.company.cloudctl.companion.automation.CloudCtlAccessibilityService
import com.company.cloudctl.companion.automation.TargetLocatorRegistry
import com.company.cloudctl.companion.data.AutomationStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.Instant
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

/**
 * Duty mode (pa-im slice 2, xianyu only): park the phone on the idlefish message
 * list, diff conversation entries on content changes, open fresh unread
 * conversations, read real bubble text, queue it, and return to the list.
 * Yields whenever a task is pending/running or the config turns it off.
 */
object DutyController {
    private const val TAG = "CloudCtlDuty"
    private const val NAVIGATE_INTERVAL_MS = 45_000
    private const val SETTLE_MS = 2_000L
    private const val CHAT_TIMEOUT_MS = 8_000L

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val busy = AtomicBoolean(false)
    private val lastNav = AtomicLong(0)
    private val lastChange = AtomicLong(0)
    private val knownPeers = HashSet<String>()

    fun onPageContentChanged(pkg: String) {
        if (pkg == "com.taobao.idlefish") lastChange.set(System.currentTimeMillis())
    }

    fun tick(context: android.content.Context, store: AutomationStore) {
        val config = ImMonitor.config
        if (!config.enabled || !config.dutyActive()) return
        if (ImMonitorConfig.PLATFORM_XIANYU !in config.platforms) return
        if (store.hasActiveTask()) return // single writer: running and blocked tasks win over duty
        val service = CloudCtlAccessibilityService.active ?: return
        if (!busy.compareAndSet(false, true)) return
        scope.launch {
            try {
                runCycle(context, service)
            } catch (error: Exception) {
                android.util.Log.w(TAG, "duty cycle failed", error)
            } finally {
                busy.set(false)
            }
        }
    }

    private suspend fun runCycle(context: android.content.Context, service: CloudCtlAccessibilityService) {
        ensureOnMessageList(service)
        val changedRecently = System.currentTimeMillis() - lastChange.get() < 5_000
        if (!changedRecently && knownPeers.isNotEmpty()) return
        // A fresh unread conversation exposes a "未读数N" badge node in its entry.
        val target = findUnreadEntry(service) ?: return
        val peerName = target.second
        if (!openConversation(service, target.first)) return
        readAndQueue(context, service, peerName)
        backToList(service)
        knownPeers.add(peerName)
    }

    private suspend fun ensureOnMessageList(service: CloudCtlAccessibilityService) {
        val now = System.currentTimeMillis()
        // Throttle navigation purely by interval: navigating on every tick when the
        // phone is not parked on the message list relaunches the app in a tight loop.
        if (now - lastNav.get() < NAVIGATE_INTERVAL_MS) return
        lastNav.set(now)
        if (onMessageList(service)) return
        runCatching { service.launchTargetApp(TargetLocatorRegistry.XIANYU_PACKAGE) }
        delay(1_500)
        // Anchor first (duty-anchor gap 3): the verified 消息 tab content description
        // positions the tap even when a keyboard or layout shift moved the old fixed
        // coordinate onto IME keys. The coordinate stays an audited last resort.
        val parked = DutyMessageListNav(object : DutyMessageListNav.Port {
            override fun onMessageList(): Boolean = this@DutyController.onMessageList(service)

            override suspend fun tapMessagesTabAnchor(): Boolean =
                service.ensureMessageListTab(TargetLocatorRegistry.XIANYU_PACKAGE)

            override suspend fun tapCoordinate(x: Double, y: Double) {
                // Never blind-tap a screen that is not verifiably the target app.
                if (!service.isTargetForeground(TargetLocatorRegistry.XIANYU_PACKAGE)) {
                    android.util.Log.w(TAG, "DUTY_NAV_COORD_FALLBACK_SKIPPED_NOT_FOREGROUND")
                    return
                }
                service.tapRemoteGestureLike(x, y)
            }

            override fun event(code: String) { android.util.Log.i(TAG, code) }
        }).execute()
        if (!parked) android.util.Log.w(TAG, "duty navigation did not land on the message list")
    }

    private fun onMessageList(service: CloudCtlAccessibilityService): Boolean {
        val roots = service.allRootsForDuty() ?: return false
        return roots.any { root -> containsDesc(root, "消息，未读消息数") }
    }

    /** Entry container with a fresh unread badge: (tapNode=badge's entry, peerName). */
    private fun findUnreadEntry(service: CloudCtlAccessibilityService): Pair<AccessibilityNodeInfo, String>? {
        val roots = service.allRootsForDuty() ?: return null
        for (root in roots) {
            val found = findUnreadIn(root)
            if (found != null) return found
        }
        return null
    }

    private fun findUnreadIn(root: AccessibilityNodeInfo): Pair<AccessibilityNodeInfo, String>? {
        for (index in 0 until root.childCount) {
            val child = root.getChild(index) ?: continue
            val desc = child.contentDescription?.toString()
            if (desc != null && desc.startsWith("未读数") && desc.length <= 8) {
                val container = child.parent?.parent ?: child.parent
                if (container != null) {
                    val peer = containerChildren(container).firstOrNull { candidate ->
                        val name = candidate.contentDescription?.toString() ?: ""
                        name.isNotBlank() && !name.startsWith("未读数") &&
                            !name.startsWith("消息") && name.length <= 32
                    }?.contentDescription?.toString()
                    if (peer != null && peer !in knownPeers) return container to peer
                }
            }
            findUnreadIn(child)?.let { return it }
        }
        return null
    }

    private suspend fun openConversation(service: CloudCtlAccessibilityService, entry: AccessibilityNodeInfo): Boolean {
        val bounds = Rect().also { entry.getBoundsInScreen(it) }
        service.tapRemoteGestureLike(bounds.exactCenterX().toDouble(), bounds.exactCenterY().toDouble())
        val deadline = System.currentTimeMillis() + CHAT_TIMEOUT_MS
        while (System.currentTimeMillis() < deadline) {
            delay(400)
            if (onChatPage(service)) return true
        }
        return false
    }

    private fun onChatPage(service: CloudCtlAccessibilityService): Boolean {
        val roots = service.allRootsForDuty() ?: return false
        return roots.any { root -> containsDesc(root, "想跟TA说点什么") }
    }

    private fun readAndQueue(context: android.content.Context, service: CloudCtlAccessibilityService, peer: String) {
        val roots = service.allRootsForDuty() ?: return
        val deviceId = runCatching {
            val raw = context.getSharedPreferences("cloudctl_binding", android.content.Context.MODE_PRIVATE)
                .getString("binding", null) ?: return
            org.json.JSONObject(raw).getString("deviceId")
        }.getOrNull() ?: return
        for (root in roots) {
            val bubbles = ArrayList<ChatBubble>()
            collectBubbles(root, bubbles)
            if (bubbles.isEmpty()) continue
            ChatPageReading.freshInbound(bubbles).forEach { text ->
                ImMonitor.accept(
                    deviceId,
                    ImEvent(
                        platform = ImMonitorConfig.PLATFORM_XIANYU,
                        peerName = peer,
                        text = text,
                        occurredAt = Instant.now(),
                    ),
                )
            }
            android.util.Log.i(TAG, "duty queued ${ChatPageReading.freshInbound(bubbles).size} messages from $peer")
            return
        }
    }

    private suspend fun backToList(service: CloudCtlAccessibilityService) {
        service.dutyBack()
        delay(SETTLE_MS)
        if (!onMessageList(service)) {
            service.dutyBack()
            delay(SETTLE_MS)
        }
    }

    private fun containerChildren(container: AccessibilityNodeInfo): List<AccessibilityNodeInfo> =
        (0 until container.childCount).mapNotNull { container.getChild(it) }

    private fun containsDesc(node: AccessibilityNodeInfo, prefix: String): Boolean {
        if (node.contentDescription?.toString()?.startsWith(prefix) == true) return true
        for (index in 0 until node.childCount) {
            val child = node.getChild(index) ?: continue
            if (containsDesc(child, prefix)) return true
        }
        return false
    }

    /** Node traversal stays Android-bound; bubble geometry rules live in ChatBubble. */
    private fun collectBubbles(node: AccessibilityNodeInfo, out: MutableList<ChatBubble>) {
        val text = node.text?.toString()?.trim()
        if (!text.isNullOrEmpty()) {
            val bounds = Rect().also { node.getBoundsInScreen(it) }
            out += ChatBubble(
                text = text,
                centerX = bounds.exactCenterX(),
                width = bounds.width(),
                height = bounds.height(),
            )
        }
        for (index in 0 until node.childCount) {
            node.getChild(index)?.let { collectBubbles(it, out) }
        }
    }
}
