package com.company.cloudctl.companion.im

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.company.cloudctl.companion.automation.CloudCtlAccessibilityService
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
        if (store.hasBlockingHead()) return // single writer: tasks win over duty
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
        if (now - lastNav.get() < NAVIGATE_INTERVAL_MS && onMessageList(service)) return
        lastNav.set(now)
        runCatching { service.launchTargetApp("com.taobao.idlefish") }
        delay(1_500)
        service.tapRemoteGestureLike(975.0, 2331.0) // 消息 tab (verified coordinate family)
        delay(SETTLE_MS)
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
