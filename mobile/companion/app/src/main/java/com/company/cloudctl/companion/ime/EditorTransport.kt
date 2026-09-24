package com.company.cloudctl.companion.ime

/**
 * One complete field read. [truncated] is true when the window hit the read cap,
 * so the caller must not treat [text] as the whole field.
 */
data class EditorSnapshot(
    val generation: Long,
    val field: String,
    val text: String,
    val selectionStart: Int,
    val selectionEnd: Int,
    val composing: Boolean,
    val offsetKnown: Boolean,
    val offset: Int,
    val truncated: Boolean,
    /**
     * False when this transport cannot observe a real selection. Callers must
     * not invent a caret position and then treat it as proof the field is settled.
     */
    val selectionKnown: Boolean = true,
)

internal object CompleteEditorText {
    const val MAX_LENGTH = 10_000
    /** One past the cap so a field that fills the window is reported truncated. */
    const val WINDOW = MAX_LENGTH + 1

    /**
     * A full-field claim requires a known zero offset, a window that did not hit
     * the cap, and a selection that sits inside the returned text.
     */
    fun accepted(
        text: String,
        offsetKnown: Boolean,
        offset: Int,
        start: Int,
        end: Int,
        truncated: Boolean,
        selectionKnown: Boolean = true,
    ): Boolean {
        if (!offsetKnown || offset != 0 || truncated || text.length > MAX_LENGTH) return false
        // An unknown selection is not a failure and is not a caret-at-end claim.
        if (!selectionKnown) return true
        return start in 0..text.length && end in 0..text.length
    }
}

/**
 * Read/write surface shared by the accessibility editor connection and the
 * CloudCtl IME. [commit] is invoked at most once per transaction by the caller.
 */
internal interface EditorTransport {
    suspend fun snapshot(): EditorSnapshot?
    suspend fun commit(snapshot: EditorSnapshot, text: String): Boolean

    /**
     * How many commits this transport has performed. Default 0 so existing
     * fakes keep compiling. A diagnostic projection reads it; it is not a
     * license to commit again.
     */
    fun commitCount(): Int = 0
}

/** Which public input channel a device may use. Binding is still decided at runtime. */
internal enum class InputChannel {
    /** API 33+: accessibility InputMethod, user's keyboard stays selected. */
    ACCESSIBILITY,
    /** API 30–32: CloudCtl IME must already be enabled; switch is temporary. */
    TEMPORARY_IME,
    /** API 29: CloudCtl IME must already be the user's current keyboard. */
    MANUAL_IME,
}

internal object InputRoutePolicy {
    fun channel(sdk: Int): InputChannel = when {
        sdk >= 33 -> InputChannel.ACCESSIBILITY
        sdk >= 30 -> InputChannel.TEMPORARY_IME
        else -> InputChannel.MANUAL_IME
    }

    /**
     * Claim-time input capability. Editor binding is not part of this decision:
     * API 33 is ready once accessibility is active; API 30–32 once CloudCtl is
     * enabled; API 29 only when it is also the current keyboard.
     */
    fun ready(sdk: Int, accessibilityActive: Boolean, imeEnabled: Boolean, imeSelected: Boolean): Boolean =
        accessibilityActive && when (channel(sdk)) {
            InputChannel.ACCESSIBILITY -> true
            InputChannel.TEMPORARY_IME -> imeEnabled
            InputChannel.MANUAL_IME -> imeEnabled && imeSelected
        }

    /** True when the status UI must still ask the user to touch the keyboard settings. */
    fun requiresSetup(sdk: Int, imeEnabled: Boolean, imeSelected: Boolean): Boolean = when (channel(sdk)) {
        InputChannel.ACCESSIBILITY -> false
        InputChannel.TEMPORARY_IME -> !imeEnabled
        InputChannel.MANUAL_IME -> !imeEnabled || !imeSelected
    }

    /** Price stays on the nine-key pad. A numeric description is not a price. */
    fun isPrice(locatorRef: String): Boolean = locatorRef == "xianyu_price"

    /**
     * API 33+ may fall back to a temporary CloudCtl switch only while the
     * accessibility editor connection is bound. Unbound means the readback
     * is unavailable: never switch the user's Sogou/iFlytek keyboard.
     */
    fun accessibilityFallbackAllowed(accessibilityBound: Boolean): Boolean = accessibilityBound
}
