package com.company.cloudctl.companion.automation

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.accessibilityservice.GestureDescription
import android.annotation.SuppressLint
import android.content.ClipData
import android.content.ClipboardManager
import android.graphics.Bitmap
import android.graphics.Path
import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.company.cloudctl.companion.network.PreviewFrame
import com.company.cloudctl.companion.service.CompanionServiceStarter
import kotlinx.coroutines.delay
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

    override fun onServiceConnected() {
        serviceInfo = serviceInfo.apply {
            flags = flags or
                AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS or
                AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS or
                AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
        }
        active = this
        CompanionServiceStarter.startIfBound(this)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) = Unit
    override fun onInterrupt() = Unit

    override fun onDestroy() {
        if (active === this) active = null
        super.onDestroy()
    }

    suspend fun execute(task: AutomationTask, journal: (AutomationStep, String) -> Unit) {
        if (active !== this) throw ExecutorFailure("ACCESSIBILITY_NOT_ACTIVE", "Accessibility service is not active")
        executor.execute(task, journal)
    }

    override fun ensureReady(targetPackage: String) {
        if (active !== this) throw ExecutorFailure("ACCESSIBILITY_NOT_ACTIVE", "Accessibility service is not active")
        if (targetPackage !in setOf(TargetLocatorRegistry.COMPANION_PACKAGE, TargetLocatorRegistry.XIANYU_PACKAGE)) {
            throw ExecutorFailure("TARGET_PACKAGE_REJECTED", "Target package is not allowlisted")
        }
        if (!serviceInfo.canRetrieveWindowContent) {
            throw ExecutorFailure("WINDOW_CONTENT_DENIED", "Window-content permission is unavailable")
        }
        val root = rootInActiveWindow
            ?: throw ExecutorFailure("ACTIVE_WINDOW_MISSING", "No active accessibility window is available")
        if (root.packageName?.toString() != targetPackage) {
            throw ExecutorFailure("WRONG_ACTIVE_PACKAGE", "The allowlisted target package is not active")
        }
    }

    override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? =
        resolveUniqueNode(targetPackage, locatorRef)?.let { node ->
            LocalNodeState(
                enabled = node.isEnabled,
                visible = node.isVisibleToUser,
                clickable = node.isClickable || hasAction(node, AccessibilityNodeInfo.ACTION_CLICK),
                editable = canAcceptText(node),
                text = collectDisplayedText(node),
            )
        }

    override suspend fun tap(targetPackage: String, locatorRef: String) {
        val node = resolveUniqueNode(targetPackage, locatorRef)
            ?: throw ExecutorFailure("LOCATOR_NOT_FOUND", "Approved locator was not found")
        if (!node.isVisibleToUser || !node.isEnabled) {
            throw ExecutorFailure("NODE_NOT_CLICKABLE", "Approved locator is not safely clickable")
        }
        if (!activate(node)) {
            throw ExecutorFailure("CLICK_REJECTED", "Accessibility click was rejected")
        }
    }

    override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) {
        val node = resolveUniqueNode(targetPackage, locatorRef)
            ?: throw ExecutorFailure("LOCATOR_NOT_FOUND", "Approved locator was not found")
        if (!node.isVisibleToUser || !node.isEnabled) {
            throw ExecutorFailure("NODE_NOT_EDITABLE", "Approved locator is not safely editable")
        }
        activate(node)
        if (setNodeText(node, value)) return
        if (paste(node, value)) return
        if (value.all { it.isDigit() || it == '.' }) {
            enterKeypad(value)
            return
        }
        throw ExecutorFailure("INPUT_REJECTED", "Accessibility text replacement was rejected")
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

    private fun resolveUniqueNode(targetPackage: String, locatorRef: String): AccessibilityNodeInfo? {
        ensureReady(targetPackage)
        val root = rootInActiveWindow
            ?: throw ExecutorFailure("ACTIVE_WINDOW_MISSING", "No active accessibility window is available")
        val locator = try {
            TargetLocatorRegistry.resolve(targetPackage, locatorRef)
        } catch (error: IllegalArgumentException) {
            throw ExecutorFailure("LOCATOR_NOT_APPROVED", "Locator is not approved for this target", error)
        }
        val matches = findMatches(root, locator)
        if (matches.size > 1) {
            throw ExecutorFailure("LOCATOR_AMBIGUOUS", "Approved locator matched multiple nodes")
        }
        return matches.singleOrNull()
    }

    private fun findMatches(root: AccessibilityNodeInfo, locator: ApprovedLocator): List<AccessibilityNodeInfo> =
        when (locator) {
            is ApprovedLocator.ResourceId -> root.findAccessibilityNodeInfosByViewId(locator.value)
            is ApprovedLocator.ContentDescription -> findContentDescription(root) { it == locator.value }
            is ApprovedLocator.ContentDescriptionPrefix -> findContentDescription(root) { it.startsWith(locator.prefix) }
            is ApprovedLocator.IndexedContentDescription -> findContentDescription(root) { it == locator.value }
                .getOrNull(locator.index)?.let(::listOf).orEmpty()
        }

    private fun findContentDescription(
        root: AccessibilityNodeInfo,
        predicate: (String) -> Boolean,
    ): List<AccessibilityNodeInfo> {
        val matches = mutableListOf<AccessibilityNodeInfo>()
        fun visit(node: AccessibilityNodeInfo) {
            val description = node.contentDescription?.toString()
            if (description != null && predicate(description)) matches += node
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
        val path = Path().apply { moveTo(bounds.exactCenterX(), bounds.exactCenterY()) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 60))
            .build()
        return suspendCancellableCoroutine { continuation ->
            val dispatched = dispatchGesture(
                gesture,
                object : GestureResultCallback() {
                    override fun onCompleted(gestureDescription: GestureDescription?) {
                        if (continuation.isActive) continuation.resume(true)
                    }

                    override fun onCancelled(gestureDescription: GestureDescription?) {
                        if (continuation.isActive) continuation.resume(false)
                    }
                },
                null,
            )
            if (!dispatched && continuation.isActive) continuation.resume(false)
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

    private fun paste(node: AccessibilityNodeInfo, value: String): Boolean {
        val clipboard = getSystemService(ClipboardManager::class.java) ?: return false
        clipboard.setPrimaryClip(ClipData.newPlainText("cloudctl-input", value))
        node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
        if (node.performAction(AccessibilityNodeInfo.ACTION_PASTE)) return true
        val focused = findFocused(rootInActiveWindow ?: return false)
        return focused != null && focused.performAction(AccessibilityNodeInfo.ACTION_PASTE)
    }

    private suspend fun enterKeypad(value: String) {
        delay(200)
        val root = rootInActiveWindow
            ?: throw ExecutorFailure("ACTIVE_WINDOW_MISSING", "No active accessibility window is available")
        if (findContentDescription(root) { it == "定价" || it == "确定" }.isEmpty()) {
            throw ExecutorFailure("INPUT_REJECTED", "Numeric keypad was not available")
        }
        for (character in value) {
            val label = character.toString()
            val keys = findContentDescription(rootInActiveWindow ?: root) { it == label }
            if (keys.size != 1) {
                throw ExecutorFailure("INPUT_REJECTED", "Keypad digit is missing or ambiguous")
            }
            if (!activate(keys.single())) {
                throw ExecutorFailure("CLICK_REJECTED", "Keypad digit click was rejected")
            }
            delay(80)
        }
        val confirm = findContentDescription(rootInActiveWindow ?: root) { it == "确定" }
        if (confirm.size != 1 || !activate(confirm.single())) {
            throw ExecutorFailure("INPUT_REJECTED", "Keypad confirm was rejected")
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

        @Volatile
        var active: CloudCtlAccessibilityService? = null
            private set
    }
}
