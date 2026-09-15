package com.company.cloudctl.companion.automation

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.accessibilityservice.GestureDescription
import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Path
import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.company.cloudctl.companion.ClipboardRelayActivity
import com.company.cloudctl.companion.ime.CloudCtlInputMethod
import com.company.cloudctl.companion.network.PreviewFrame
import com.company.cloudctl.companion.service.CompanionServiceStarter
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import java.io.ByteArrayOutputStream
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.Executor
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.math.max

class CloudCtlAccessibilityService : AccessibilityService(), LocalAutomationUi {
    private val executor by lazy { LocalAutomationExecutor(this) }
    private val serviceScope = kotlinx.coroutines.CoroutineScope(
        kotlinx.coroutines.Dispatchers.Default + kotlinx.coroutines.SupervisorJob(),
    )

    override fun onServiceConnected() {
        serviceInfo = serviceInfo.apply {
            flags = flags or
                AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS or
                AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS or
                AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            eventTypes = eventTypes or AccessibilityEvent.TYPE_NOTIFICATION_STATE_CHANGED
            eventTypes = eventTypes or AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
        }
        active = this
        CompanionServiceStarter.startIfBound(this)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        val pkg = event.packageName?.toString() ?: return
        // pa-im slice 2: duty mode consumes list-page changes; notifications stay generic.
        if (event.eventType == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED) {
            com.company.cloudctl.companion.im.DutyController.onPageContentChanged(pkg)
            return
        }
        if (event.eventType != AccessibilityEvent.TYPE_NOTIFICATION_STATE_CHANGED) return
        if (!com.company.cloudctl.companion.im.ImMonitor.isPackageEnabled(pkg)) return
        val notification = event.parcelableData as? android.app.Notification ?: return
        val extras = notification.extras
        val title = (extras.getCharSequence(android.app.Notification.EXTRA_TITLE)?.toString()
            ?: extras.getCharSequence(android.app.Notification.EXTRA_CONVERSATION_TITLE)?.toString()
            ?: "").trim()
        val text = (extras.getCharSequence(android.app.Notification.EXTRA_TEXT)?.toString()
            ?: extras.getCharSequence(android.app.Notification.EXTRA_BIG_TEXT)?.toString()
            ?: "").trim()
        if (title.isEmpty() || text.isEmpty()) return
        val platform = com.company.cloudctl.companion.im.ImMonitorConfig.platformOfPackage(pkg) ?: return
        // im-feed-noise (2026-09-14): every monitored notification is logged with
        // package + channel id + a truncated title so one on-device capture can
        // calibrate the xianyu DM vs feed channel ids (ImFeedNoiseFilter).
        Log.i(TAG, "IM_NOTIF pkg=$pkg channel=${notification.channelId} title=${title.take(24)}")
        val dropped = com.company.cloudctl.companion.im.ImFeedNoiseFilter.dropReason(
            platform, notification.channelId, title,
        )
        if (dropped != null) {
            Log.i(
                TAG,
                "${com.company.cloudctl.companion.im.ImFeedNoiseFilter.DROP_EVENT} " +
                    "platform=$platform reason=${dropped.reason} channel=${notification.channelId} title=${title.take(48)}",
            )
            return
        }
        if (!com.company.cloudctl.companion.im.ImMonitorConfig.isChannelAllowed(
                platform, notification.channelId)
        ) return
        val deviceId = runCatching {
            val raw = getSharedPreferences("cloudctl_binding", android.content.Context.MODE_PRIVATE)
                .getString("binding", null) ?: return
            org.json.JSONObject(raw).getString("deviceId")
        }.getOrNull() ?: return
        val accepted = com.company.cloudctl.companion.im.ImMonitor.accept(
            deviceId,
            com.company.cloudctl.companion.im.ImEvent(
                platform = platform,
                peerName = title.take(128),
                text = text.take(4000),
                occurredAt = java.time.Instant.ofEpochMilli(
                    notification.`when`.takeIf { it > 0 } ?: System.currentTimeMillis()
                ),
            ),
        )
        if (accepted) Log.i(TAG, "IM event queued from $title")
    }
    override fun onInterrupt() = Unit

    override fun onDestroy() {
        if (active === this) active = null
        super.onDestroy()
    }

    suspend fun execute(
        task: AutomationTask,
        control: ExecutionControl? = null,
        startAfterIndex: Int = -1,
        commitGate: CommitGate? = null,
        destructiveGate: DestructiveClickGate? = null,
        journal: (AutomationStep, String) -> Unit,
    ) {
        if (active !== this) throw ExecutorFailure("ACCESSIBILITY_NOT_ACTIVE", "Accessibility service is not active")
        launchTargetApp(task.targetPackage)
        LocalAutomationExecutor(this, commitGate = commitGate, destructiveGate = destructiveGate)
            .execute(task, control, startAfterIndex, journal)
    }

    override suspend fun tapText(targetPackage: String, value: String) {
        ensureReady(targetPackage)
        val matches = allRoots()
            .filter { it.packageName?.toString() == targetPackage }
            .flatMap { findContentDescription(it) { text -> text == value } }
            .distinct()
            .filter { it.isVisibleToUser }
        if (matches.size != 1) {
            throw ExecutorFailure(
                // Only a miss scrolls; an ambiguous match must fail the step as-is.
                if (matches.isEmpty()) "TAP_TEXT_NOT_FOUND" else "TAP_TEXT_NOT_UNIQUE",
                "Expected exactly one visible '$value' node, found ${matches.size}",
            )
        }
        // Flutter views report ACTION_CLICK success without handling it; a real
        // synthesized touch on the node center is the reliable tap (pa-im/20260913.1).
        val node = matches.first()
        if (!gestureClick(node) && !activate(node)) {
            throw ExecutorFailure("TAP_TEXT_NOT_UNIQUE", "Unique '$value' node could not be tapped")
        }
    }

    // Duty-mode helpers (pa-im slice 2) + live sink (p10-live/20260913.1).
    fun allRootsForDuty(): List<AccessibilityNodeInfo> = allRoots()

    fun tapRemoteGestureLike(x: Double, y: Double) {
        serviceScope.launch { tapScreen(x.toFloat(), y.toFloat()) }
    }

    fun dutyBack() {
        performGlobalAction(GLOBAL_ACTION_BACK)
    }
    /**
     * Duty-mode tab navigation (duty-anchor gap 3): park the target on its
     * message list by resolving the verified tab anchor and gesture-tapping the
     * node center. A missing anchor (chat page open, keyboard up, app update)
     * returns false after bounded retries; this method never blind-taps fixed
     * screen coordinates.
     */
    suspend fun ensureMessageListTab(targetPackage: String): Boolean {
        if (targetPackage != TargetLocatorRegistry.XIANYU_PACKAGE) return false
        for (attempt in 1..DUTY_NAV_ANCHOR_ATTEMPTS) {
            val node = runCatching {
                resolveUniqueNode(targetPackage, DUTY_NAV_MESSAGES_TAB_LOCATOR)
            }.getOrNull()
            if (node != null && node.isVisibleToUser && gestureClick(node)) {
                Log.i(TAG, "DUTY_NAV_ANCHOR_TAP attempt=$attempt locator=$DUTY_NAV_MESSAGES_TAB_LOCATOR")
                return true
            }
            delay(DUTY_NAV_ANCHOR_RETRY_MS)
        }
        Log.w(TAG, "DUTY_NAV_ANCHOR_MISSING target=$targetPackage locator=$DUTY_NAV_MESSAGES_TAB_LOCATOR")
        return false
    }

    // ROOT-INTEGRATION live sink (p10-live/20260913.1): remote gestures via accessibility.
    fun remoteTap(x: Double, y: Double) {
        serviceScope.launch { tapScreen(x.toFloat(), y.toFloat()) }
    }

    fun remoteSwipe(x1: Double, y1: Double, x2: Double, y2: Double) {
        serviceScope.launch { dispatchStroke(x1.toFloat(), y1.toFloat(), x2.toFloat(), y2.toFloat(), 220L) }
    }

    suspend fun launchTargetApp(targetPackage: String) {
        val activePackage = rootInActiveWindow?.packageName?.toString()
        Log.i(
            TAG,
            "launchTargetApp targetPackage=$targetPackage " +
                "xianyu=${TargetLocatorRegistry.XIANYU_PACKAGE} " +
                "activeWindow=$activePackage",
        )
        if (targetPackage !in setOf(
                TargetLocatorRegistry.COMPANION_PACKAGE,
                TargetLocatorRegistry.XIANYU_PACKAGE,
                TargetLocatorRegistry.XHS_PACKAGE,
                TargetLocatorRegistry.DOUYIN_PACKAGE,
            )
        ) {
            throw ExecutorFailure("TARGET_PACKAGE_REJECTED", "Target package is not allowlisted")
        }
        if (activePackage != targetPackage) {
            val launch = resolveLaunchIntent(targetPackage)
            if (launch == null) {
                val installed = runCatching { packageManager.getPackageInfo(targetPackage, 0) }.isSuccess
                Log.e(
                    TAG,
                    "getLaunchIntentForPackage($targetPackage) is null " +
                        "installed=$installed " +
                        "expectedXianyu=${targetPackage == TargetLocatorRegistry.XIANYU_PACKAGE} " +
                        "activeWindow=$activePackage",
                )
                throw ExecutorFailure("APP_NOT_INSTALLED", "Target package is not installed")
            }
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            try {
                startActivity(launch)
            } catch (_: ActivityNotFoundException) {
                throw ExecutorFailure("LAUNCH_REQUIRES_USER", "System blocked background launch")
            } catch (_: SecurityException) {
                throw ExecutorFailure("LAUNCH_REQUIRES_USER", "System blocked background launch")
            }
            waitUntilPackage(targetPackage)
        }
        val focused = rootInActiveWindow?.packageName?.toString()
        Log.i(TAG, "launchTargetApp after wait expected=$targetPackage actual=$focused")
        Log.i("CompanionSync", "launchTargetApp after wait expected=$targetPackage actual=$focused")
    }

    private fun resolveLaunchIntent(targetPackage: String): Intent? {
        packageManager.getLaunchIntentForPackage(targetPackage)?.let { return it }
        val launcher = Intent(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_LAUNCHER)
            setPackage(targetPackage)
        }
        val resolved = packageManager.resolveActivity(launcher, PackageManager.MATCH_DEFAULT_ONLY)
        val info = resolved?.activityInfo
        if (info != null) {
            return launcher
                .setComponent(ComponentName(info.packageName, info.name))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        if (targetPackage == TargetLocatorRegistry.XIANYU_PACKAGE) {
            Log.w(TAG, "Falling back to known Idlefish launcher component")
            return Intent(Intent.ACTION_MAIN)
                .addCategory(Intent.CATEGORY_LAUNCHER)
                .setComponent(ComponentName(targetPackage, XIANYU_LAUNCHER_ACTIVITY))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        return null
    }

    // Navigation reset primitive + conversation-list scrolling (im-live slice 2).

    override fun isTargetForeground(targetPackage: String): Boolean =
        runCatching { ensureReady(targetPackage) }.isSuccess

    override fun atRootPage(targetPackage: String): Boolean = runCatching {
        ensureReady(targetPackage)
        TargetLocatorRegistry.rootAnchorRefs(targetPackage).any { anchor ->
            runCatching { resolveUniqueNode(targetPackage, anchor) }.getOrNull()?.isVisibleToUser == true
        }
    }.getOrDefault(false)

    override suspend fun dismissBlockedDialog(targetPackage: String): String? =
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main.immediate) {
            if (BlockedDialogRegistry.rules(targetPackage).isEmpty() || !isTargetForeground(targetPackage)) {
                return@withContext null
            }
            // Only the active target window: never combine title/buttons across windows.
            val root = rootInActiveWindow ?: return@withContext null
            if (root.packageName?.toString() != targetPackage) return@withContext null
            val nodes = findNodes(root) { it.packageName?.toString() == targetPackage }
            val match = BlockedDialogRegistry.match(targetPackage, nodes.map { node ->
                BlockedDialogRegistry.Node(
                    text = node.text?.toString(),
                    description = node.contentDescription?.toString(),
                    visible = node.isVisibleToUser,
                    enabled = node.isEnabled,
                    clickable = node.isClickable,
                )
            }) ?: return@withContext null
            ensureReady(targetPackage)
            if (rootInActiveWindow?.windowId != root.windowId) return@withContext null
            // One dispatchGesture only; an unconfirmed tap fails closed, with no action fallback.
            if (!gestureClick(nodes[match.nodeIndex])) {
                throw ExecutorFailure("NAV_RESET_FAILED", "Recovery dialog gesture was not confirmed")
            }
            match.label
        }

    override suspend fun goBack() {
        performGlobalAction(GLOBAL_ACTION_BACK)
        delay(NAV_SETTLE_MS)
    }

    override suspend fun restartTargetApp(targetPackage: String) {
        // A plain launchTargetApp no-ops when the target is already foreground on
        // an inner page; the forced relaunch below always re-enters the root task.
        if (targetPackage !in setOf(
                TargetLocatorRegistry.COMPANION_PACKAGE,
                TargetLocatorRegistry.XIANYU_PACKAGE,
                TargetLocatorRegistry.XHS_PACKAGE,
                TargetLocatorRegistry.DOUYIN_PACKAGE,
            )
        ) {
            throw ExecutorFailure("TARGET_PACKAGE_REJECTED", "Target package is not allowlisted")
        }
        val launch = resolveLaunchIntent(targetPackage)
            ?: throw ExecutorFailure("APP_NOT_INSTALLED", "Target package is not installed")
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        try {
            startActivity(launch)
        } catch (_: ActivityNotFoundException) {
            throw ExecutorFailure("LAUNCH_REQUIRES_USER", "System blocked background launch")
        } catch (_: SecurityException) {
            throw ExecutorFailure("LAUNCH_REQUIRES_USER", "System blocked background launch")
        }
        waitUntilPackage(targetPackage)
    }

    override fun canScrollTextList(targetPackage: String): Boolean =
        runCatching { ensureReady(targetPackage) }.isSuccess && findScrollableContainer(targetPackage) != null

    override suspend fun scrollTextListForward(targetPackage: String) {
        val container = findScrollableContainer(targetPackage)
            ?: throw ExecutorFailure("SCROLL_CONTAINER_MISSING", "No visible scrollable list to scroll")
        // Flutter lists ignore accessibility scroll actions; fall back to a gesture.
        if (!container.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD)) {
            swipeUp()
        }
        delay(NAV_SETTLE_MS)
    }

    private fun findScrollableContainer(targetPackage: String): AccessibilityNodeInfo? =
        allRoots()
            .filter { it.packageName?.toString() == targetPackage }
            .flatMap { root -> findNodes(root) { node -> node.isVisibleToUser && node.isScrollable } }
            .firstOrNull()

    /** Generic predicate traversal used by scroll-container discovery. */
    private fun findNodes(
        root: AccessibilityNodeInfo,
        predicate: (AccessibilityNodeInfo) -> Boolean,
    ): List<AccessibilityNodeInfo> {
        val matches = mutableListOf<AccessibilityNodeInfo>()
        fun visit(node: AccessibilityNodeInfo) {
            if (predicate(node)) matches += node
            for (index in 0 until node.childCount) node.getChild(index)?.let(::visit)
        }
        visit(root)
        return matches
    }

    /** Chat-page bubble snapshot for IM body enrichment (im-live slice 2, gap 2). */
    fun chatBubbles(targetPackage: String): List<com.company.cloudctl.companion.im.ChatBubble> {
        fun collect(root: AccessibilityNodeInfo, requireScrollableAncestor: Boolean): List<com.company.cloudctl.companion.im.ChatBubble> {
            val found = mutableListOf<com.company.cloudctl.companion.im.ChatBubble>()
            fun visit(node: AccessibilityNodeInfo, inScrollable: Boolean) {
                val scrollable = inScrollable || node.isScrollable
                // Flutter idlefish exposes ALL page text through contentDescription
                // (node.text is empty tree-wide, verified on device). Bubbles live in
                // the scrollable conversation list; input-bar controls and the header
                // card sit outside it and must not become fake inbound bubbles.
                if ((!requireScrollableAncestor || scrollable) && node.isClickable) {
                    val text = (node.text?.toString() ?: node.contentDescription?.toString() ?: "").trim()
                    if (text.isNotEmpty()) {
                        val bounds = Rect()
                        node.getBoundsInScreen(bounds)
                        found += com.company.cloudctl.companion.im.ChatBubble(
                            text = text,
                            centerX = bounds.exactCenterX(),
                            width = bounds.width(),
                            height = bounds.height(),
                        )
                    }
                }
                for (index in 0 until node.childCount) node.getChild(index)?.let { visit(it, scrollable) }
            }
            visit(root, false)
            return found
        }
        return allRoots()
            .filter { it.packageName?.toString() == targetPackage }
            .flatMap { root -> collect(root, requireScrollableAncestor = true).ifEmpty { collect(root, false) } }
    }

    /**
     * Reveal older conversation content (backward=true) or return to the newest
     * (backward=false) by swiping inside the conversation list's own bounds.
     *
     * Rationale (bubble-reader gap, device acceptance 2026-09-14): the legacy
     * fixed start point (540,1600) landed inside the IME window while the chat
     * keyboard was open, so the keyboard consumed the stroke and the list never
     * scrolled. The scrollable list node compresses with the keyboard, so a
     * stroke in its 30%-70% height band on the center-x line always stays
     * within the visible list (fix plan option a; the fixed pair survives only
     * as the no-node fallback). Dragging down pulls older peer bubbles into
     * view; dragging up returns to our newest replies at the bottom.
     */
    suspend fun swipeConversationList(targetPackage: String, backward: Boolean) {
        val bounds = findScrollableContainer(targetPackage)?.let { node ->
            val rect = Rect()
            node.getBoundsInScreen(rect)
            com.company.cloudctl.companion.im.ConversationListSwipe.Bounds(
                left = rect.left,
                top = rect.top,
                right = rect.right,
                bottom = rect.bottom,
            )
        }
        val stroke = com.company.cloudctl.companion.im.ConversationListSwipe.stroke(bounds, backward = backward)
        dispatchStroke(stroke.startX, stroke.startY, stroke.endX, stroke.endY, CONVERSATION_SWIPE_MS)
    }

    override fun ensureReady(targetPackage: String) {
        if (active !== this) throw ExecutorFailure("ACCESSIBILITY_NOT_ACTIVE", "Accessibility service is not active")
        if (targetPackage !in setOf(
                TargetLocatorRegistry.COMPANION_PACKAGE,
                TargetLocatorRegistry.XIANYU_PACKAGE,
                TargetLocatorRegistry.XHS_PACKAGE,
                TargetLocatorRegistry.DOUYIN_PACKAGE,
            )
        ) {
            throw ExecutorFailure("TARGET_PACKAGE_REJECTED", "Target package is not allowlisted")
        }
        if (!serviceInfo.canRetrieveWindowContent) {
            throw ExecutorFailure("WINDOW_CONTENT_DENIED", "Window-content permission is unavailable")
        }
        val root = rootInActiveWindow
            ?: throw ExecutorFailure("ACTIVE_WINDOW_MISSING", "No active accessibility window is available")
        val actual = root.packageName?.toString()
        Log.i(TAG, "ensureReady expected=$targetPackage actual=$actual")
        Log.i("CompanionSync", "ensureReady expected=$targetPackage actual=$actual")
        if (actual != targetPackage) {
            Log.e(TAG, "WRONG_ACTIVE_PACKAGE expected=$targetPackage actual=$actual")
            Log.e("CompanionSync", "WRONG_ACTIVE_PACKAGE expected=$targetPackage actual=$actual")
            throw ExecutorFailure("WRONG_ACTIVE_PACKAGE", "The allowlisted target package is not active")
        }
    }

    override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? =
        resolveUniqueNode(targetPackage, locatorRef)?.let { node ->
            LocalNodeState(
                enabled = true,
                visible = node.isVisibleToUser,
                clickable = true,
                editable = canAcceptText(node),
                text = collectDisplayedText(node),
                // The node's own content description carries the published-goods
                // tab badge signal (「1\n在卖」) asserted by ui.assertBadge.
                description = node.contentDescription?.toString(),
            )
        }

    override fun screenSize(targetPackage: String): Pair<Int, Int>? = runCatching {
        // The service-context displayMetrics exclude system bars (device-verified:
        // the frozen 1080x2400 guard failed on a 2340-high metric). Real bounds
        // are what the frozen coordinates were captured against.
        val manager = getSystemService(android.view.WindowManager::class.java) ?: return null
        val bounds = manager.maximumWindowMetrics.bounds
        bounds.width() to bounds.height()
    }.getOrNull()

    override suspend fun tapScreenAt(targetPackage: String, x: Int, y: Int) {
        // Structured maintenance coordinates (xianyu only): one dispatchGesture
        // path, bounds-checked against the live screen, no fallback click.
        if (targetPackage != TargetLocatorRegistry.XIANYU_PACKAGE) {
            throw ExecutorFailure("COORDINATE_TAP_REJECTED", "Coordinate taps are not approved for this target")
        }
        ensureReady(targetPackage)
        val metrics = resources.displayMetrics
        if (x !in 0 until metrics.widthPixels || y !in 0 until metrics.heightPixels) {
            throw ExecutorFailure("COORDINATE_OUT_OF_BOUNDS", "Coordinate tap left the guarded screen")
        }
        if (!tapScreen(x.toFloat(), y.toFloat())) {
            throw ExecutorFailure("CLICK_UNCONFIRMED", "Coordinate gesture was not confirmed")
        }
    }

    override suspend fun tapOnce(targetPackage: String, locatorRef: String) {
        val node = resolveUniqueNode(targetPackage, locatorRef)
            ?: throw ExecutorFailure("LOCATOR_NOT_FOUND", "Approved locator was not found")
        if (!node.isVisibleToUser || !node.isEnabled) {
            throw ExecutorFailure("NODE_NOT_CLICKABLE", "Approved locator is not safely clickable")
        }
        // A rejected/cancelled gesture is ambiguous. Never attempt a fallback click.
        if (!gestureClick(node)) throw ExecutorFailure("CLICK_UNCONFIRMED", "Single-shot gesture was not confirmed")
    }

    override suspend fun tap(targetPackage: String, locatorRef: String) {
        val node = resolveUniqueNode(targetPackage, locatorRef)
            ?: throw ExecutorFailure("LOCATOR_NOT_FOUND", "Approved locator was not found")
        if (!node.isVisibleToUser) {
            throw ExecutorFailure("NODE_NOT_CLICKABLE", "Approved locator is not safely clickable")
        }
        // Flutter idlefish reports ACTION_CLICK success without opening the picker or composer.
        // The publish control is often clickable=false; only a gesture tap actually submits.
        if (locatorRef == "xianyu_location") {
            if (gestureClickAt(node, 0.88f, 0.50f) || gestureClick(node) || activate(node)) return
            throw ExecutorFailure("CLICK_REJECTED", "Accessibility click was rejected")
        }
        if (locatorRef == "xianyu_publish_button") {
            if (gestureClick(node) || gestureClickAt(node, 0.50f, 0.50f) || activate(node)) return
            throw ExecutorFailure("CLICK_REJECTED", "Accessibility click was rejected")
        }
        if (!gestureClick(node) && !activate(node)) {
            throw ExecutorFailure("CLICK_REJECTED", "Accessibility click was rejected")
        }
    }

    override fun visibleTextContains(expected: String): Boolean {
        if (allRoots().any { treeContains(it, expected) }) return true
        return FlutterTextCommit.accepted(visibleHaystack(), expected)
    }

    override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) {
        if (locatorRef == "xianyu_chat_input") {
            commitChatInput(targetPackage, locatorRef, value)
            return
        }
        val node = resolveUniqueNode(targetPackage, locatorRef)
            ?: throw ExecutorFailure("LOCATOR_NOT_FOUND", "Approved locator was not found")
        if (!node.isVisibleToUser || !node.isEnabled) {
            throw ExecutorFailure("NODE_NOT_EDITABLE", "Approved locator is not safely editable")
        }
        if (targetPackage == TargetLocatorRegistry.XHS_PACKAGE ||
            targetPackage == TargetLocatorRegistry.DOUYIN_PACKAGE
        ) {
            // Native EditText composers (xiaohongshu, douyin) accept SET_TEXT directly.
            commitNativeText(node, value)
            return
        }
        if (FlutterTextCommit.isNumericPrice(value)) {
            openPriceKeypad(targetPackage, node)
            awaitNumericKeypad()
            enterKeypad(value)
            repeat(20) {
                if (priceAccepted(value)) return
                delay(150)
            }
            throw ExecutorFailure("INPUT_REJECTED", "Numeric keypad did not confirm the price")
        }
        commitFlutterDescription(targetPackage, locatorRef, node, value)
    }

    /** Chat never enters the description SET_TEXT/clipboard/paste fallback chain. */
    private suspend fun commitChatInput(targetPackage: String, locatorRef: String, value: String) {
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main.immediate) {
            fun composer(): AccessibilityNodeInfo? {
                ensureReady(targetPackage)
                val locator = TargetLocatorRegistry.resolve(targetPackage, locatorRef)
                return allRoots().filter { it.packageName?.toString() == targetPackage }
                    .flatMap { findMatches(it, locator) }.distinct()
                    .filter { it.isVisibleToUser && it.isEnabled }.singleOrNull()
            }
            ChatInputCommit(object : ChatInputCommit.Port {
                override fun imeSelected() = CloudCtlInputMethod.isEnabled(this@CloudCtlAccessibilityService) &&
                    CloudCtlInputMethod.isSelected(this@CloudCtlAccessibilityService)

                override suspend fun activate(): Boolean {
                    val target = composer() ?: return false
                    target.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
                    return gestureClick(target)
                }

                override fun focused(): Boolean = composer()?.let { findFocused(it) != null } == true
                override fun session() = CloudCtlInputMethod.chatSession(targetPackage)
                override fun replace(session: Long, value: String) =
                    CloudCtlInputMethod.replaceChatText(targetPackage, session, value)

                override fun readText(session: Long): String? {
                    val target = composer() ?: return null
                    // The editor may legitimately restart right after the commit while
                    // the text persists; verify through the live session, never a dead one.
                    val live = CloudCtlInputMethod.chatSession(targetPackage) ?: session
                    val inputText = CloudCtlInputMethod.readChatText(targetPackage, live) ?: return null
                    // Flutter may expose only a placeholder semantics View. If it does
                    // expose a value, disagreement with the IME is not acceptance.
                    val semanticsText = target.text?.toString().orEmpty()
                    return inputText.takeIf { semanticsText.isEmpty() || semanticsText == inputText }
                }

                override fun event(code: String) { Log.i(TAG, code) }
            }).execute(value)
        }
    }


    /** Native EditText targets (xiaohongshu composer) accept SET_TEXT directly. */
    private fun commitNativeText(node: AccessibilityNodeInfo, value: String) {
        node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
        val arguments = android.os.Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value)
        }
        if (!node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)) {
            throw ExecutorFailure("INPUT_REJECTED", "Native SET_TEXT was rejected")
        }
    }

    private suspend fun commitFlutterDescription(
        targetPackage: String,
        locatorRef: String,
        initial: AccessibilityNodeInfo,
        value: String,
    ) {
        if (descriptionAccepted(value)) return
        focusDescriptionField(targetPackage, locatorRef, initial)
        for (attempt in 0 until 20) {
            if (descriptionAccepted(value)) return
            if (CloudCtlInputMethod.hasInputConnection()) break
            delay(100)
        }
        if (CloudCtlInputMethod.hasInputConnection()) {
            repeat(12) {
                if (CloudCtlInputMethod.requestCommit(value) && descriptionAccepted(value)) return
                delay(150)
            }
        }
        resolveUniqueNode(targetPackage, locatorRef)?.let { setTextAnywhere(it, value) }
        if (descriptionAccepted(value)) return
        seedClipboard(value)
        val target = resolveUniqueNode(targetPackage, locatorRef) ?: initial
        pasteAnywhere(target, value)
        delay(250)
        if (descriptionAccepted(value)) return
        pasteViaContextMenu(target, value)
        delay(400)
        if (descriptionAccepted(value)) return
        if (!CloudCtlInputMethod.isEnabled(this) || !CloudCtlInputMethod.isSelected(this)) {
            throw ExecutorFailure(
                "INPUT_IME_REQUIRED",
                "Idlefish description needs CloudCtl Input as the current keyboard",
            )
        }
        throw ExecutorFailure("INPUT_REJECTED", "Accessibility text replacement was rejected")
    }

    private suspend fun focusDescriptionField(
        targetPackage: String,
        locatorRef: String,
        initial: AccessibilityNodeInfo,
    ) {
        var node = initial
        node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
        gestureClickAt(node, 0.50f, 0.18f)
        delay(200)
        node = resolveUniqueNode(targetPackage, locatorRef) ?: node
        gestureClickAt(node, 0.50f, 0.32f)
        delay(200)
        node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
    }

    private fun descriptionAccepted(expected: String): Boolean =
        FlutterTextCommit.accepted(visibleHaystack(), expected)

    private fun visibleHaystack(): String =
        allRoots().joinToString("\n") { collectDisplayedText(it) }

    private fun seedClipboard(value: String): Boolean {
        val clipboard = getSystemService(ClipboardManager::class.java) ?: return false
        return runCatching {
            clipboard.setPrimaryClip(ClipData.newPlainText("cloudctl-input", value))
            true
        }.getOrDefault(false)
    }

    override suspend fun swipeUp() {
        dispatchStroke(540f, 1_850f, 540f, 420f, 500L)
        delay(250)
        dispatchStroke(540f, 1_850f, 540f, 420f, 500L)
    }

    override suspend fun screenshot(taskId: String, label: String): ScreenshotEvidence {
        ensureScreenshotCapability()
        val output = captureScreenshot(taskId, label)
        val bytes = output.readBytes()
        return ScreenshotEvidence(
            path = output.absolutePath,
            size = bytes.size.toLong(),
            sha256 = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) },
        )
    }

    suspend fun capturePreviewJpeg(): PreviewFrame {
        ensureScreenshotCapability()
        val original = captureDisplayBitmap()
        val scaled = scaleForPreview(original)
        try {
            return PreviewFrame(encodeJpeg(scaled), scaled.width, scaled.height)
        } finally {
            if (scaled !== original) scaled.recycle()
            original.recycle()
        }
    }

    override fun log(level: LogLevel, messageCode: String) {
        when (level) {
            LogLevel.DEBUG -> Log.d(TAG, messageCode)
            LogLevel.INFO -> Log.i(TAG, messageCode)
            LogLevel.WARN -> Log.w(TAG, messageCode)
            LogLevel.ERROR -> Log.e(TAG, messageCode)
        }
    }

    private fun allRoots(): List<AccessibilityNodeInfo> {
        val roots = mutableListOf<AccessibilityNodeInfo>()
        windows?.mapNotNull { it.root }?.let(roots::addAll)
        rootInActiveWindow?.let { active ->
            if (roots.none { it == active }) roots.add(0, active)
        }
        return roots
    }

    private fun resolveUniqueNode(targetPackage: String, locatorRef: String): AccessibilityNodeInfo? {
        ensureReady(targetPackage)
        val locator = try {
            TargetLocatorRegistry.resolve(targetPackage, locatorRef)
        } catch (error: IllegalArgumentException) {
            throw ExecutorFailure("LOCATOR_NOT_APPROVED", "Locator is not approved for this target", error)
        }
        val matches = allRoots()
            .filter { it.packageName?.toString() == targetPackage }
            .flatMap { findMatches(it, locator) }
            .distinct()
        if (matches.size > 1) {
            return matches.firstOrNull { it.isVisibleToUser } ?: matches.first()
        }
        if (matches.isEmpty() && locatorRef.startsWith("dy_")) {
            val haystack = allRoots()
                .filter { it.packageName?.toString() == targetPackage }
                .joinToString("\n") { collectDisplayedText(it) }
            Log.w(TAG, "dy locator '$locatorRef' matched nothing; contains 未选中=${haystack.contains("未选中")} sample=${haystack.takeLast(160)}")
        }
        return matches.singleOrNull()
    }

    private fun findLabelAnywhere(label: String): AccessibilityNodeInfo? {
        for (root in allRoots()) {
            val match = findContentDescription(root) { it == label }.firstOrNull { it.isVisibleToUser }
            if (match != null) return match
        }
        return null
    }

    private fun keypadRoot(): AccessibilityNodeInfo? =
        allRoots().firstOrNull { root ->
            findContentDescription(root) { it == "收起键盘" }.any { isKeypadDigit(it) }
        }

    private fun isKeypadDigit(node: AccessibilityNodeInfo): Boolean {
        if (!node.isVisibleToUser) return false
        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        return bounds.top >= 1_450 &&
            bounds.width() in 120..280 &&
            bounds.height() in 120..250
    }

    private fun findKeypadKey(label: String): AccessibilityNodeInfo? {
        val matches = allRoots()
            .flatMap { findContentDescription(it) { desc -> desc == label } }
            .filter { isKeypadDigit(it) }
        if (matches.isEmpty()) return null
        return matches.maxBy { node ->
            val bounds = Rect()
            node.getBoundsInScreen(bounds)
            bounds.centerY()
        }
    }

    private fun logPriceDebug(tag: String) {
        val labels = listOf("收起键盘", "输入定价", "定价", "¥", "1", "5", "9", "0", "确定", "取消", "删除")
        for (label in labels) {
            val matches = allRoots().flatMap { findContentDescription(it) { desc -> desc == label } }
            if (matches.isEmpty()) {
                Log.i(TAG, "$tag $label missing")
                continue
            }
            for (node in matches) {
                val bounds = Rect()
                node.getBoundsInScreen(bounds)
                Log.i(
                    TAG,
                    "$tag $label bounds=$bounds vis=${node.isVisibleToUser} click=${node.isClickable} keypad=${isKeypadDigit(node)}",
                )
            }
        }
    }

    private fun findMatches(root: AccessibilityNodeInfo, locator: ApprovedLocator): List<AccessibilityNodeInfo> =
        when (locator) {
            is ApprovedLocator.ResourceId -> root.findAccessibilityNodeInfosByViewId(locator.value)
            // findContentDescription matches content-desc and text alike; the
            // string tests come from TargetLocatorRegistry.acceptsDescription so
            // node matching and unit tests share one semantic.
            is ApprovedLocator.ContentDescription -> stringMatches(root, locator)
            is ApprovedLocator.DescRegex -> stringMatches(root, locator)
            is ApprovedLocator.ContentDescriptionPrefix -> stringMatches(root, locator)
            is ApprovedLocator.Text -> stringMatches(root, locator)
            is ApprovedLocator.TextPrefix -> stringMatches(root, locator)
            is ApprovedLocator.AnyOf -> locator.alternatives
                .flatMap { findMatches(root, it) }
                .distinct()
            is ApprovedLocator.IndexedContentDescription -> stringMatches(root, locator)
                .getOrNull(locator.index)?.let(::listOf).orEmpty()
            is ApprovedLocator.IndexedResourceId -> root.findAccessibilityNodeInfosByViewId(locator.value)
                .sortedBy { node -> node.boundsTop() }
                .getOrNull(locator.index)?.let(::listOf).orEmpty()
            // Selection marks may report invisible or carry trailing text;
            // their visible cell container is the tap target.
            is ApprovedLocator.IndexedContentDescriptionPrefixParent -> stringMatches(root, locator)
                .getOrNull(locator.index)?.parent?.let(::listOf).orEmpty()
            // The mark node itself is the checkbox overlay on the cell; tapping it selects.
            is ApprovedLocator.IndexedContentDescriptionPrefix -> stringMatches(root, locator)
                .getOrNull(locator.index)?.let(::listOf).orEmpty()
        }

    private fun stringMatches(root: AccessibilityNodeInfo, locator: ApprovedLocator): List<AccessibilityNodeInfo> =
        findContentDescription(root) { TargetLocatorRegistry.acceptsDescription(locator, it) }

    private fun AccessibilityNodeInfo.boundsTop(): Int {
        val bounds = Rect()
        getBoundsInScreen(bounds)
        return bounds.top
    }

    private fun findContentDescription(
        root: AccessibilityNodeInfo,
        predicate: (String) -> Boolean,
    ): List<AccessibilityNodeInfo> {
        val matches = mutableListOf<AccessibilityNodeInfo>()
        fun visit(node: AccessibilityNodeInfo) {
            val description = node.contentDescription?.toString()
            val text = node.text?.toString()
            if (description != null && predicate(description)) matches += node
            else if (text != null && predicate(text)) matches += node
            for (index in 0 until node.childCount) node.getChild(index)?.let(::visit)
        }
        visit(root)
        return matches
    }

    private suspend fun activate(node: AccessibilityNodeInfo): Boolean {
        if (node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
        val parent = node.parent
        if (parent != null && parent.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
        return gestureClick(node)
    }

    private suspend fun gestureClick(node: AccessibilityNodeInfo): Boolean {
        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        if (bounds.width() <= 0 || bounds.height() <= 0) return false
        return tapScreen(bounds.exactCenterX(), bounds.exactCenterY())
    }

    private suspend fun tapScreen(x: Float, y: Float, dwellMs: Long = 50L): Boolean {
        return dispatchStroke(x, y, x + 1f, y, dwellMs)
    }


    private suspend fun dispatchStroke(x: Float, y: Float, durationMs: Long): Boolean {
        val endX = if (durationMs >= 400L) x + 3f else x
        val endY = if (durationMs >= 400L) y + 3f else y
        return dispatchStroke(x, y, endX, endY, durationMs)
    }

    private suspend fun dispatchStroke(startX: Float, startY: Float, endX: Float, endY: Float, durationMs: Long): Boolean {
        val path = Path().apply {
            moveTo(startX, startY)
            lineTo(endX, endY)
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, durationMs))
            .build()
        return suspendCancellableCoroutine { continuation ->
            val callback = object : GestureResultCallback() {
                override fun onCompleted(gestureDescription: GestureDescription?) {
                    if (continuation.isActive) continuation.resume(true)
                }

                override fun onCancelled(gestureDescription: GestureDescription?) {
                    if (continuation.isActive) continuation.resume(false)
                }
            }
            val main = Handler(Looper.getMainLooper())
            val runner = Runnable {
                val dispatched = dispatchGesture(gesture, callback, main)
                if (!dispatched && continuation.isActive) continuation.resume(false)
            }
            if (Looper.myLooper() == Looper.getMainLooper()) runner.run() else main.post(runner)
        }
    }

    private fun setNodeText(node: AccessibilityNodeInfo, value: String): Boolean {
        val arguments = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value)
        }
        if (node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)) return true
        val focused = findFocused(node) ?: findFocused(rootInActiveWindow ?: return false)
        return focused != null && focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)
    }

    private fun setTextAnywhere(node: AccessibilityNodeInfo, value: String): Boolean {
        if (setNodeText(node, value)) return true
        for (index in 0 until node.childCount) {
            val child = node.getChild(index) ?: continue
            if (setTextAnywhere(child, value)) return true
        }
        return false
    }

    private fun treeContains(node: AccessibilityNodeInfo, expected: String): Boolean {
        val text = node.text?.toString().orEmpty()
        val description = node.contentDescription?.toString().orEmpty()
        if (expected in text || expected in description) return true
        for (index in 0 until node.childCount) {
            val child = node.getChild(index) ?: continue
            if (treeContains(child, expected)) return true
        }
        return false
    }

    private suspend fun copyToClipboardForeground(value: String) {
        val intent = Intent(this, ClipboardRelayActivity::class.java).apply {
            addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK or
                    Intent.FLAG_ACTIVITY_NO_ANIMATION or
                    Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS,
            )
            putExtra(ClipboardRelayActivity.EXTRA_TEXT, value)
        }
        startActivity(intent)
        delay(350)
        waitUntilPackage(TargetLocatorRegistry.XIANYU_PACKAGE)
    }

    private suspend fun waitUntilPackage(pkg: String) {
        repeat(20) {
            if (rootInActiveWindow?.packageName?.toString() == pkg) return
            delay(150)
        }
        Log.w(
            TAG,
            "waitUntilPackage timeout expected=$pkg actual=${rootInActiveWindow?.packageName}",
        )
        Log.w(
            "CompanionSync",
            "waitUntilPackage timeout expected=$pkg actual=${rootInActiveWindow?.packageName}",
        )
    }

    private suspend fun pasteViaContextMenu(node: AccessibilityNodeInfo, value: String) {
        val clipboard = getSystemService(ClipboardManager::class.java) ?: return
        clipboard.setPrimaryClip(ClipData.newPlainText("cloudctl-input", value))
        repeat(3) {
            longPress(node)
            delay(600)
            val paste = findLabelAnywhere("粘贴")
            if (paste != null) {
                gestureClick(paste)
                delay(400)
                return
            }
            val selectAll = findLabelAnywhere("全选")
            if (selectAll != null) {
                gestureClick(selectAll)
                delay(300)
            }
        }
    }

    private suspend fun longPress(node: AccessibilityNodeInfo): Boolean {
        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        if (bounds.width() <= 0 || bounds.height() <= 0) return false
        return dispatchStroke(bounds.exactCenterX(), bounds.exactCenterY(), 1_200L)
    }

    private fun pasteAnywhere(node: AccessibilityNodeInfo, value: String): Boolean {
        val clipboard = getSystemService(ClipboardManager::class.java) ?: return false
        clipboard.setPrimaryClip(ClipData.newPlainText("cloudctl-input", value))
        fun visit(current: AccessibilityNodeInfo): Boolean {
            current.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
            if (current.performAction(AccessibilityNodeInfo.ACTION_PASTE)) return true
            for (index in 0 until current.childCount) {
                val child = current.getChild(index) ?: continue
                if (visit(child)) return true
            }
            return false
        }
        if (visit(node)) return true
        val focused = allRoots().firstNotNullOfOrNull { findFocused(it) }
        return focused != null && focused.performAction(AccessibilityNodeInfo.ACTION_PASTE)
    }

    private fun digitKeypadVisible(): Boolean = keypadRoot() != null

    private fun priceSheetVisible(): Boolean =
        findLabelAnywhere("定价") != null || findLabelAnywhere("价格设置") != null

    private fun priceAccepted(value: String): Boolean {
        if (digitKeypadVisible() || priceSheetVisible()) return false
        val typed = PriceKeypad.keys(value)
        if (typed.isEmpty()) return false
        return visibleTextContains(typed) ||
            allRoots().any { PriceKeypad.acceptedOnForm(collectDisplayedText(it), value) }
    }

    private suspend fun gestureClickAt(
        node: AccessibilityNodeInfo,
        xFraction: Float,
        yFraction: Float,
    ): Boolean {
        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        if (bounds.width() <= 0 || bounds.height() <= 0) return false
        val x = bounds.left + bounds.width() * xFraction
        val y = bounds.top + bounds.height() * yFraction
        return tapScreen(x, y)
    }

    private suspend fun openPriceKeypad(targetPackage: String, priceRow: AccessibilityNodeInfo) {
        logPriceDebug("price-start")
        if (digitKeypadVisible()) return
        var row = priceRow
        if (!priceSheetVisible()) {
            for (xFraction in floatArrayOf(0.88f, 0.82f, 0.92f)) {
                row = resolveUniqueNode(targetPackage, "xianyu_price") ?: row
                val bounds = Rect()
                row.getBoundsInScreen(bounds)
                Log.i(TAG, "open price row $xFraction bounds=$bounds")
                gestureClickAt(row, xFraction, 0.50f)
                delay(700)
                if (digitKeypadVisible() || priceSheetVisible()) break
            }
        }
        logPriceDebug("after-row")
        if (digitKeypadVisible()) return
        if (!priceSheetVisible()) {
            activate(row)
            delay(700)
        }
        if (digitKeypadVisible()) return
        if (!priceSheetVisible()) {
            Log.w(TAG, "price sheet did not open")
            return
        }
        delay(400)
        revealNumericKeypad()
        logPriceDebug("after-reveal")
    }

    private fun findPriceAmountField(): AccessibilityNodeInfo? {
        findLabelAnywhere("输入定价")?.let { return it }
        val yen = findLabelAnywhere("¥") ?: return null
        val yenBounds = Rect()
        yen.getBoundsInScreen(yenBounds)
        val candidates = mutableListOf<AccessibilityNodeInfo>()
        fun visit(node: AccessibilityNodeInfo) {
            val bounds = Rect()
            node.getBoundsInScreen(bounds)
            val description = node.contentDescription?.toString().orEmpty()
            val compact = bounds.width() in 200..800 && bounds.height() in 80..250
            if (
                node.isVisibleToUser &&
                compact &&
                yenBounds.contains(bounds.centerX(), bounds.centerY()) &&
                "原价" !in description &&
                "竞拍" !in description &&
                description != "卖闲置以新品价2折更容易售出"
            ) {
                candidates += node
            }
            for (index in 0 until node.childCount) node.getChild(index)?.let(::visit)
        }
        allRoots().forEach(::visit)
        return candidates.minByOrNull { node ->
            val bounds = Rect()
            node.getBoundsInScreen(bounds)
            bounds.width() * bounds.height()
        }
    }

    private fun nodeAt(x: Int, y: Int): AccessibilityNodeInfo? {
        var best: AccessibilityNodeInfo? = null
        var bestArea = Int.MAX_VALUE
        fun visit(node: AccessibilityNodeInfo) {
            val bounds = Rect()
            node.getBoundsInScreen(bounds)
            if (node.isVisibleToUser && bounds.contains(x, y)) {
                val area = bounds.width() * bounds.height()
                if (area in 1 until bestArea) {
                    best = node
                    bestArea = area
                }
            }
            for (index in 0 until node.childCount) node.getChild(index)?.let(::visit)
        }
        allRoots().forEach(::visit)
        return best
    }

    private suspend fun revealNumericKeypad() {
        if (digitKeypadVisible()) return
        val amount = findPriceAmountField()
        if (amount != null) {
            amount.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            delay(450)
            if (digitKeypadVisible()) return
            gestureClickAt(amount, 0.50f, 0.35f)
            delay(450)
            if (digitKeypadVisible()) return
        }
        val yen = findLabelAnywhere("¥") ?: return
        val yenBounds = Rect()
        yen.getBoundsInScreen(yenBounds)
        val amountX = yenBounds.left + yenBounds.width() * 0.50f
        val amountY = yenBounds.top + yenBounds.height() * 0.40f
        Log.i(TAG, "reveal keypad at $amountX,$amountY yen=$yenBounds")
        nodeAt(amountX.toInt(), amountY.toInt())?.let { hit ->
            hit.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            delay(450)
            if (digitKeypadVisible()) return
        }
        tapScreen(amountX, amountY)
        delay(450)
        if (digitKeypadVisible()) return
        yen.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        delay(450)
        if (digitKeypadVisible()) return
        Log.i(TAG, "finger tap amount field 540,820")
        tapScreen(540f, 820f)
        delay(600)
    }

    private suspend fun awaitNumericKeypad() {
        repeat(25) {
            if (digitKeypadVisible()) return
            delay(200)
        }
        if (digitKeypadVisible()) return
        if (priceSheetVisible()) revealNumericKeypad()
        repeat(15) {
            if (digitKeypadVisible()) return
            delay(200)
        }
        if (!digitKeypadVisible()) {
            throw ExecutorFailure("INPUT_REJECTED", "Numeric keypad was not available")
        }
    }

    private suspend fun keypadTap(node: AccessibilityNodeInfo): Boolean {
        if (node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        if (bounds.width() <= 0 || bounds.height() <= 0) return false
        return tapScreen(bounds.exactCenterX(), bounds.exactCenterY())
    }

    private fun keypadShowsAmount(digits: String): Boolean {
        if (digits.isEmpty()) return false
        val yen = findLabelAnywhere("¥") ?: return false
        val hay = collectDisplayedText(yen)
        Log.i(TAG, "amount hay=$hay")
        return PriceKeypad.acceptedOnForm(hay, digits) || digits in hay || "¥$digits" in hay
    }

    private val keypadCoordinates = mapOf(
        '1' to Pair(135f, 1_591f),
        '2' to Pair(405f, 1_591f),
        '3' to Pair(675f, 1_591f),
        '4' to Pair(135f, 1_808f),
        '5' to Pair(405f, 1_808f),
        '6' to Pair(675f, 1_808f),
        '7' to Pair(135f, 2_026f),
        '8' to Pair(405f, 2_026f),
        '9' to Pair(675f, 2_026f),
        '0' to Pair(405f, 2_243f),
        '.' to Pair(135f, 2_243f),
    )

    private suspend fun enterKeypad(value: String) {
        logPriceDebug("enter-keypad")
        if (!digitKeypadVisible()) {
            Log.e(TAG, "enterKeypad: keypad missing after open")
            throw ExecutorFailure("INPUT_REJECTED", "Numeric keypad was not available")
        }
        val digits = PriceKeypad.keys(value)
        if (digits.isEmpty() || !digits.all { it.isDigit() || it == '.' }) {
            throw ExecutorFailure("INPUT_REJECTED", "Price has no keypad digits")
        }
        suspend fun tapDigit(character: Char) {
            val label = character.toString()
            val target = findKeypadKey(label)
            if (target != null) {
                val clicked = target.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                Log.i(TAG, "digit $label ACTION_CLICK=$clicked")
                delay(180)
                if (keypadShowsAmount(label)) return
                keypadTap(target)
                delay(180)
                if (keypadShowsAmount(label)) return
            }
            val point = keypadCoordinates[character]
                ?: throw ExecutorFailure("INPUT_REJECTED", "Keypad digit is missing or ambiguous")
            Log.i(TAG, "fallback tap digit $label at $point")
            nodeAt(point.first.toInt(), point.second.toInt())?.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            delay(120)
            tapScreen(point.first, point.second)
            delay(180)
        }
        for (index in digits.indices) {
            val typed = digits.substring(0, index + 1)
            tapDigit(digits[index])
            delay(80)
            Log.i(TAG, "after $typed shown=${keypadShowsAmount(typed)}")
        }
        delay(200)
        if (!keypadShowsAmount(digits)) {
            Log.w(TAG, "amount not shown after first type, retry")
            logPriceDebug("before-retry")
            repeat(digits.length + 2) {
                val del = findKeypadKey("删除")
                if (del != null) {
                    del.performAction(AccessibilityNodeInfo.ACTION_CLICK) || keypadTap(del)
                } else {
                    tapScreen(945f, 1_700f)
                }
                delay(80)
            }
            for (index in digits.indices) {
                val typed = digits.substring(0, index + 1)
                tapDigit(digits[index])
                delay(80)
                Log.i(TAG, "retry after $typed shown=${keypadShowsAmount(typed)}")
            }
            delay(200)
        }
        if (!keypadShowsAmount(digits)) {
            logPriceDebug("digits-missing")
            throw ExecutorFailure("INPUT_REJECTED", "Keypad digits did not enter the amount")
        }
        for (attempt in 0 until 4) {
            val confirm = findKeypadKey("确定")
            if (confirm != null) {
                confirm.performAction(AccessibilityNodeInfo.ACTION_CLICK) || keypadTap(confirm)
            } else {
                tapScreen(945f, 2_135f)
            }
            delay(350)
            if (!digitKeypadVisible()) break
        }
        if (digitKeypadVisible()) {
            throw ExecutorFailure("INPUT_REJECTED", "Keypad confirm was rejected")
        }
        delay(250)
        confirmPriceSheet()
    }

    private fun sheetConfirmButton(): AccessibilityNodeInfo? =
        allRoots()
            .flatMap { findContentDescription(it) { desc -> desc == "确定" } }
            .filter { node ->
                if (!node.isVisibleToUser || isKeypadDigit(node)) return@filter false
                val bounds = Rect()
                node.getBoundsInScreen(bounds)
                bounds.top >= 2_100 && bounds.width() >= 400
            }
            .maxByOrNull { node ->
                val bounds = Rect()
                node.getBoundsInScreen(bounds)
                bounds.centerY()
            }

    private suspend fun confirmPriceSheet() {
        if (!priceSheetVisible()) return
        logPriceDebug("sheet-confirm")
        repeat(4) {
            if (!priceSheetVisible()) return
            val confirm = sheetConfirmButton()
            if (confirm != null) {
                gestureClick(confirm) || confirm.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            } else {
                tapScreen(701f, 2_262f)
            }
            delay(400)
        }
    }

    private fun findFocused(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        if (node == null) return null
        if (node.isFocused) return node
        for (index in 0 until node.childCount) {
            val match = findFocused(node.getChild(index))
            if (match != null) return match
        }
        return null
    }

    private fun collectDisplayedText(node: AccessibilityNodeInfo): String {
        val parts = mutableListOf<String>()
        fun visit(current: AccessibilityNodeInfo) {
            current.text?.toString()?.takeIf { it.isNotBlank() }?.let(parts::add)
            current.contentDescription?.toString()?.takeIf { it.isNotBlank() }?.let(parts::add)
            for (index in 0 until current.childCount) current.getChild(index)?.let(::visit)
        }
        visit(node)
        return parts.distinct().joinToString("\n")
    }

    private fun canAcceptText(node: AccessibilityNodeInfo): Boolean =
        node.isEditable ||
            hasAction(node, AccessibilityNodeInfo.ACTION_SET_TEXT) ||
            hasAction(node, AccessibilityNodeInfo.ACTION_PASTE)

    private fun hasAction(node: AccessibilityNodeInfo, action: Int): Boolean =
        node.actionList.any { it.id == action }

    private fun ensureScreenshotCapability() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            throw ExecutorFailure("SCREENSHOT_UNSUPPORTED", "Accessibility screenshot requires Android 11")
        }
        if (serviceInfo.capabilities and AccessibilityServiceInfo.CAPABILITY_CAN_TAKE_SCREENSHOT == 0) {
            throw ExecutorFailure("SCREENSHOT_DENIED", "Accessibility screenshot capability is unavailable")
        }
    }

    @SuppressLint("NewApi")
    private suspend fun captureDisplayBitmap(): Bitmap {
        return suspendCancellableCoroutine { continuation ->
            takeScreenshot(
                Display.DEFAULT_DISPLAY,
                Executor { command -> command.run() },
                object : TakeScreenshotCallback {
                    override fun onSuccess(result: ScreenshotResult) {
                        runCatching {
                            result.hardwareBuffer.use { buffer ->
                                val hardware = Bitmap.wrapHardwareBuffer(buffer, result.colorSpace)
                                    ?: throw ExecutorFailure("SCREENSHOT_BUFFER_FAILED", "Screenshot buffer is unavailable")
                                try {
                                    hardware.copy(Bitmap.Config.ARGB_8888, false)
                                        ?: throw ExecutorFailure("SCREENSHOT_BUFFER_FAILED", "Screenshot copy failed")
                                } finally {
                                    hardware.recycle()
                                }
                            }
                        }.fold(continuation::resume, continuation::resumeWithException)
                    }

                    override fun onFailure(errorCode: Int) {
                        continuation.resumeWithException(
                            ExecutorFailure("SCREENSHOT_CAPTURE_FAILED", "Screenshot failed with code $errorCode"),
                        )
                    }
                },
            )
        }
    }

    private fun scaleForPreview(bitmap: Bitmap): Bitmap {
        val longest = max(bitmap.width, bitmap.height)
        if (longest <= PREVIEW_MAX_SIDE) return bitmap
        val scale = PREVIEW_MAX_SIDE.toFloat() / longest
        val width = (bitmap.width * scale).toInt().coerceAtLeast(1)
        val height = (bitmap.height * scale).toInt().coerceAtLeast(1)
        return Bitmap.createScaledBitmap(bitmap, width, height, true)
    }

    private fun encodeJpeg(bitmap: Bitmap): ByteArray {
        var quality = 60
        var encoded: ByteArray
        do {
            val stream = ByteArrayOutputStream()
            if (!bitmap.compress(Bitmap.CompressFormat.JPEG, quality, stream)) {
                throw ExecutorFailure("SCREENSHOT_ENCODING_FAILED", "Preview JPEG encoding failed")
            }
            encoded = stream.toByteArray()
            quality -= 10
        } while (encoded.size > PREVIEW_MAX_BYTES && quality >= 30)
        if (encoded.size > PREVIEW_MAX_BYTES) {
            throw ExecutorFailure("SCREENSHOT_TOO_LARGE", "Preview JPEG exceeds size limit")
        }
        return encoded
    }

    @SuppressLint("NewApi")
    private suspend fun captureScreenshot(taskId: String, label: String): File {
        val safeLabel = label.replace(Regex("[^A-Za-z0-9._-]"), "_")
        val output = File(filesDir, "automation-evidence/$taskId/$safeLabel.png")
        if (output.parentFile?.mkdirs() == false && output.parentFile?.isDirectory != true) {
            throw ExecutorFailure("SCREENSHOT_STORAGE_FAILED", "Screenshot directory is unavailable")
        }
        return suspendCancellableCoroutine { continuation ->
            takeScreenshot(
                Display.DEFAULT_DISPLAY,
                Executor { command -> command.run() },
                object : TakeScreenshotCallback {
                    override fun onSuccess(result: ScreenshotResult) {
                        runCatching {
                            result.hardwareBuffer.use { buffer ->
                                val bitmap = Bitmap.wrapHardwareBuffer(buffer, result.colorSpace)
                                    ?: throw ExecutorFailure("SCREENSHOT_BUFFER_FAILED", "Screenshot buffer is unavailable")
                                try {
                                    output.outputStream().use { stream ->
                                        if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)) {
                                            throw ExecutorFailure("SCREENSHOT_ENCODING_FAILED", "Screenshot encoding failed")
                                        }
                                    }
                                } finally {
                                    bitmap.recycle()
                                }
                            }
                            output
                        }.fold(continuation::resume, continuation::resumeWithException)
                    }

                    override fun onFailure(errorCode: Int) {
                        continuation.resumeWithException(
                            ExecutorFailure("SCREENSHOT_CAPTURE_FAILED", "Screenshot failed with code $errorCode"),
                        )
                    }
                },
            )
        }
    }

    companion object {
        private const val TAG = "CloudCtlExecutor"
        private const val PREVIEW_MAX_SIDE = 720
        private const val PREVIEW_MAX_BYTES = 380_000
        private const val XIANYU_LAUNCHER_ACTIVITY = "com.taobao.fleamarket.home.activity.InitActivity"
        private const val NAV_SETTLE_MS = 800L
        private const val CONVERSATION_SWIPE_MS = 350L
        private const val DUTY_NAV_ANCHOR_ATTEMPTS = 3
        private const val DUTY_NAV_ANCHOR_RETRY_MS = 500L
        private const val DUTY_NAV_MESSAGES_TAB_LOCATOR = "xianyu_messages_tab"

        @Volatile
        var active: CloudCtlAccessibilityService? = null
            private set
    }
}
