package com.company.cloudctl.companion.ime

import com.company.cloudctl.companion.automation.ExecutorFailure
import kotlinx.coroutines.delay

/**
 * Proof that [expected] was the complete field text on two consecutive stable
 * reads of the same field.
 *
 * [selectionKnown] is false when the transport cannot read a real selection
 * (the pre-API-33 InputConnection path). Verification then keys off the full
 * text, generation and field identity only — a fabricated caret-at-end is
 * never treated as a safety fact.
 *
 * A chat proof is consumable once. [verify] fails if the field moved, the
 * generation changed, or the text no longer matches.
 */
/**
 * Safe projection of an [InputProof] for a diagnostic log.
 *
 * The fixture text is reduced to its UTF-16 length and SHA-256. The field
 * fingerprint and node key are SHA-256 as well. Expected text, readback text,
 * and any chat content are not fields of this type, so a caller cannot log
 * them by printing the projection.
 */
internal data class InputProofProjection(
    val resultCode: String,
    val utf16Length: Int,
    val textSha256: String,
    val generation: Long,
    val fieldSha256: String,
    val nodeKeySha256: String?,
    val selectionKnown: Boolean,
    val channel: String,
    val commitCount: Int,
)

internal object InputProofProjector {
    fun project(
        proof: InputProof,
        channel: String,
        commitCount: Int,
        resultCode: String = "INPUT_VERIFIED",
    ): InputProofProjection = InputProofProjection(
        resultCode = resultCode,
        utf16Length = proof.expected.length,
        textSha256 = sha256(proof.expected),
        generation = proof.generation,
        fieldSha256 = sha256(proof.field),
        nodeKeySha256 = proof.nodeKey?.let(::sha256),
        selectionKnown = proof.selectionKnown,
        channel = channel,
        commitCount = commitCount,
    )

    fun failure(code: String, channel: String): InputProofProjection = InputProofProjection(
        resultCode = code,
        utf16Length = -1,
        textSha256 = "",
        generation = -1L,
        fieldSha256 = "",
        nodeKeySha256 = null,
        selectionKnown = false,
        channel = channel,
        commitCount = -1,
    )

    fun sha256(value: String): String {
        val digest = java.security.MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { "%02x".format(it) }
    }
}

data class InputProof(
    val target: String,
    val field: String,
    val generation: Long,
    val expected: String,
    val snapshot: EditorSnapshot,
    val targetPackage: String = target,
    val locatorRef: String = "",
    val nodeKey: String? = null,
    val selectionKnown: Boolean = true,
    /** Task that produced this proof. A send from another task cannot consume it. */
    val taskId: String? = null,
    /** Authorized peer/conversation. A drifted header cannot reuse the proof. */
    val peerName: String? = null,
    /**
     * Monotonic deadline in the executor clock ([android.os.SystemClock.elapsedRealtime]
     * on device). Null only for proofs that are not yet bound to a task.
     */
    val expiresAtElapsedMs: Long? = null,
    /**
     * Commits this transaction issued. Zero when the field already equaled the
     * fixture. Never more than one. Absent on proofs minted before the count
     * was recorded; a projection must not invent it.
     */
    val commitCount: Int? = null,
)

/**
 * One text transaction: at most one commit, then read-only proof.
 *
 * An empty field may be committed once. A field that already equals the expected
 * text is verified without a second commit. Any other existing content is
 * [FIELD_DIRTY_BY_USER] and is never cleared. After the commit, a generation
 * change on the same field and package may be re-read, never re-committed.
 */
internal class VerifiedEditorInput(
    private val transport: EditorTransport,
    private val target: () -> String?,
    private val pause: suspend () -> Unit = { delay(150) },
) {
    suspend fun write(value: String): InputProof {
        if (value.isBlank() || value.length > CompleteEditorText.MAX_LENGTH) fail("INPUT_REJECTED")
        val pinned = target() ?: fail("INPUT_TARGET_CHANGED")
        val before = stableRead(pinned)
        if (before.composing) fail("USER_INTERFERENCE")
        if (before.text.isNotEmpty() && before.text != value) fail("FIELD_DIRTY_BY_USER")
        val alreadyPresent = before.text == value
        val commitsBefore = transport.commitCount()
        if (!alreadyPresent && !transport.commit(before, value)) fail("INPUT_REJECTED")
        // A successful proof may record zero commits (the field already equaled
        // the text) or exactly one. coerceAtLeast would turn a second commit into
        // a successful proof; that is a failed transaction, not a success.
        val issued = transport.commitCount() - commitsBefore
        if (alreadyPresent) {
            if (issued != 0) fail("INPUT_REJECTED")
        } else if (issued != 1) {
            fail("INPUT_REJECTED")
        }
        return prove(pinned, before.field, before.generation, value, allowGenerationChange = !alreadyPresent)
            .copy(commitCount = if (alreadyPresent) 0 else issued)
    }

    /**
     * Re-read the same field. Does not commit. Fails when the proof is no longer live.
     * When the original proof could not read a real selection, selection is not
     * re-checked: only the full text, generation and field identity count.
     */
    suspend fun verify(proof: InputProof) {
        val live = read(proof.target)
        val selectionMoved = proof.selectionKnown && (
            live.selectionStart != proof.expected.length || live.selectionEnd != proof.expected.length
            )
        if (live.field != proof.field || live.generation != proof.generation ||
            live.text != proof.expected || live.composing || selectionMoved
        ) {
            fail("INPUT_PROOF_EXPIRED")
        }
    }

    private suspend fun stableRead(pinned: String): EditorSnapshot {
        val first = read(pinned)
        if (first.composing) fail("USER_INTERFERENCE")
        pause()
        val second = read(pinned)
        if (first.field != second.field) fail("INPUT_TARGET_CHANGED")
        if (first.generation != second.generation) fail("USER_INTERFERENCE")
        if (first.text != second.text || first.selectionStart != second.selectionStart ||
            first.selectionEnd != second.selectionEnd || second.composing
        ) {
            fail("USER_INTERFERENCE")
        }
        return second
    }

    private suspend fun prove(
        pinned: String,
        field: String,
        committedGeneration: Long,
        value: String,
        allowGenerationChange: Boolean,
    ): InputProof {
        var previous: EditorSnapshot? = null
        repeat(20) {
            pause()
            val current = read(pinned)
            if (current.field != field) fail("INPUT_TARGET_CHANGED")
            if (current.composing) fail("USER_INTERFERENCE")
            // No commit was issued, so a rebuilt connection is someone else's editor.
            if (!allowGenerationChange && current.generation != committedGeneration) fail("USER_INTERFERENCE")
            val selectionReady = !current.selectionKnown ||
                (current.selectionStart == value.length && current.selectionEnd == value.length)
            if (current.text == value && selectionReady) {
                val prior = previous
                if (prior != null && prior == current) {
                    return InputProof(
                        target = pinned,
                        field = field,
                        generation = current.generation,
                        expected = value,
                        snapshot = current,
                        selectionKnown = current.selectionKnown,
                    )
                }
                previous = current
            } else if (current.text.isNotEmpty() && current.text != value) {
                // Content that is neither empty-in-flight nor the expected text is the
                // user (or another writer). Never commit again to "fix" it.
                fail("USER_INTERFERENCE")
            } else {
                previous = null
            }
        }
        fail("INPUT_REJECTED")
    }

    private suspend fun read(pinned: String): EditorSnapshot {
        if (target() != pinned) fail("INPUT_TARGET_CHANGED")
        val snapshot = transport.snapshot() ?: fail("INPUT_READBACK_UNAVAILABLE")
        if (target() != pinned) fail("INPUT_TARGET_CHANGED")
        if (!CompleteEditorText.accepted(
                snapshot.text, snapshot.offsetKnown, snapshot.offset,
                snapshot.selectionStart, snapshot.selectionEnd, snapshot.truncated,
                snapshot.selectionKnown,
            )
        ) {
            fail("INPUT_READBACK_UNAVAILABLE")
        }
        return snapshot
    }

    private fun fail(code: String): Nothing = throw ExecutorFailure(
        code,
        when (code) {
            "FIELD_DIRTY_BY_USER" -> "The field contains an existing draft; input was not overwritten"
            "USER_INTERFERENCE" -> "The editor changed during automation; input stopped"
            "INPUT_TARGET_CHANGED" -> "The target field changed; input stopped"
            "INPUT_PROOF_EXPIRED" -> "The verified field text is no longer present"
            else -> "A complete stable editor readback was not confirmed"
        },
    )
}
