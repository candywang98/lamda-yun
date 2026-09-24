package com.company.cloudctl.companion.ime

import com.company.cloudctl.companion.automation.ExecutorFailure

/**
 * Where a chat or description field is allowed to be written.
 *
 * [nodeKey] is a stable public signature (window, bounds, class, view id),
 * never [System.identityHashCode] of the [android.view.accessibility.AccessibilityNodeInfo]
 * wrapper. A fresh wrapper of the same field must still match; a different
 * window, position or field must not.
 */
internal data class FieldAnchor(
    val targetPackage: String,
    val locatorRef: String,
    val nodeKey: String?,
)

/**
 * Turns the readback [ChatInputCommit] already finished into the held chat proof.
 *
 * The readback is produced inside the temporary-IME block, while CloudCtl is still
 * selected. Callers must not read the field again after [TemporaryImeSwitch.around]
 * restores the original keyboard: that later read is a different editor and is not
 * this proof.
 */
internal object ChatInputProofFactory {
    fun fromReadback(
        targetPackage: String,
        locatorRef: String,
        value: String,
        anchor: FieldAnchor,
        readback: com.company.cloudctl.companion.automation.ChatInputReadback,
        livePackage: String?,
    ): InputProof {
        if (anchor.targetPackage != targetPackage || anchor.locatorRef != locatorRef) {
            throw ExecutorFailure("INPUT_TARGET_CHANGED", "The chat locator changed after commit")
        }
        val fingerprint = readback.fingerprint
            ?: throw ExecutorFailure("INPUT_READBACK_UNAVAILABLE", "The editor identity was not available after commit")
        // The fingerprint's first field is the EditorInfo package, captured with the
        // two stable reads. A later observation that names a different package is
        // the user having left the target.
        val fingerprintedPackage = fingerprint.substringBefore('|')
        if (fingerprintedPackage != targetPackage || (livePackage != null && livePackage != targetPackage)) {
            throw ExecutorFailure("INPUT_TARGET_CHANGED", "The editor package changed after commit")
        }
        if (readback.text != value) {
            throw ExecutorFailure("INPUT_REJECTED", "The committed chat text did not read back")
        }
        val snapshot = EditorSnapshot(
            generation = readback.generation,
            field = fingerprint,
            text = readback.text,
            selectionStart = 0,
            selectionEnd = 0,
            composing = false,
            offsetKnown = true,
            offset = 0,
            truncated = false,
            selectionKnown = false,
        )
        return InputProof(
            target = targetPackage,
            field = fingerprint,
            generation = readback.generation,
            expected = value,
            snapshot = snapshot,
            targetPackage = targetPackage,
            locatorRef = locatorRef,
            nodeKey = anchor.nodeKey,
            selectionKnown = false,
        )
    }
}

/**
 * API 30–32 chat commit, extracted so the proof is minted while CloudCtl is still
 * the selected IME.
 *
 * [switchToCloudCtl] is [TemporaryImeSwitch.around]: it selects CloudCtl, runs the
 * block, then restores the original keyboard. The block must return the proof.
 * A read after the switch returns is rejected — the user's keyboard is back and
 * that read is not the commit's readback.
 */
internal class Api30ChatInputCommit(
    private val commit: suspend (String) -> com.company.cloudctl.companion.automation.ChatInputReadback,
    private val switchToCloudCtl: suspend (
        suspend () -> InputProof,
    ) -> InputProof,
    private val anchorOf: () -> FieldAnchor?,
    private val cloudCtlStillSelected: () -> Boolean,
    private val livePackage: () -> String?,
) {
    suspend fun execute(targetPackage: String, locatorRef: String, value: String): InputProof {
        val anchor = anchorOf()
            ?: throw ExecutorFailure("LOCATOR_NOT_FOUND", "Approved locator was not found")
        return switchToCloudCtl {
            val readback = commit(value)
            if (!cloudCtlStillSelected()) {
                throw ExecutorFailure(
                    "INPUT_IME_REQUIRED",
                    "CloudCtl Input was no longer selected when the chat proof was captured",
                )
            }
            ChatInputProofFactory.fromReadback(
                targetPackage, locatorRef, value, anchor, readback, livePackage(),
            )
        }
    }
}

/**
 * Shared chat/description transaction.
 *
 * The anchor is re-checked before the commit and again before the proof is
 * returned. A disappeared node, a different node, or a different package fails
 * closed. Price locators never enter this path.
 */
internal class FieldInputTransaction(
    private val route: () -> InputChannel,
    private val accessibilityBound: (String) -> Boolean,
    private val accessibilityTransport: (String) -> EditorTransport?,
    private val imeTransport: (String) -> EditorTransport?,
    private val anchorOf: (String, String) -> FieldAnchor?,
    private val pause: suspend () -> Unit = {},
) {
    suspend fun replace(targetPackage: String, locatorRef: String, value: String): InputProof {
        if (InputRoutePolicy.isPrice(locatorRef)) {
            throw ExecutorFailure("INPUT_REJECTED", "Price fields are not text-committed")
        }
        if (value.isBlank() || value.length > CompleteEditorText.MAX_LENGTH) {
            throw ExecutorFailure("INPUT_REJECTED", "Text is empty or longer than the verified window")
        }
        val anchor = anchorOf(targetPackage, locatorRef)
            ?: throw ExecutorFailure("LOCATOR_NOT_FOUND", "Approved locator was not found")
        return when (route()) {
            InputChannel.ACCESSIBILITY -> {
                // Unbound is not a license to switch Sogou/iFlytek. The caller
                // must already have refused the write; refuse again here.
                if (!accessibilityBound(targetPackage)) {
                    throw ExecutorFailure(
                        "INPUT_READBACK_UNAVAILABLE",
                        "Accessibility editor is not bound; the user's keyboard was not switched",
                    )
                }
                commit(anchor, value, accessibilityTransport(targetPackage))
            }
            // The caller already holds the temporary switch for this one replace.
            InputChannel.TEMPORARY_IME -> commit(anchor, value, imeTransport(targetPackage))
            InputChannel.MANUAL_IME -> commit(anchor, value, imeTransport(targetPackage))
        }
    }

    private suspend fun commit(anchor: FieldAnchor, value: String, transport: EditorTransport?): InputProof {
        val live = transport ?: throw ExecutorFailure("INPUT_REJECTED", "No editor connection is bound to this field")
        val writer = VerifiedEditorInput(
            live,
            target = {
                val liveAnchor = anchorOf(anchor.targetPackage, anchor.locatorRef)
                if (liveAnchor?.nodeKey != anchor.nodeKey) null else anchor.targetPackage
            },
            pause = pause,
        )
        val proof = writer.write(value)
        val after = anchorOf(anchor.targetPackage, anchor.locatorRef)
            ?: throw ExecutorFailure("INPUT_TARGET_CHANGED", "The target field disappeared after input")
        if (after.targetPackage != anchor.targetPackage || after.locatorRef != anchor.locatorRef ||
            after.nodeKey != anchor.nodeKey
        ) {
            throw ExecutorFailure("INPUT_TARGET_CHANGED", "The target field changed after input")
        }
        return proof.copy(
            targetPackage = anchor.targetPackage,
            locatorRef = anchor.locatorRef,
            nodeKey = anchor.nodeKey,
        )
    }
}
