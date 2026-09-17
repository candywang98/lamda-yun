package com.company.cloudctl.companion.ime

/**
 * Generation-pinned admission for InputConnections.
 *
 * An InputConnection captured while editor generation N was live must never carry
 * text once the editor restarted (generation N+1): the old editor may be a
 * disposed Flutter view that silently drops commits, or a different field the
 * user just focused. Callers that get [admits] == false must re-capture the
 * connection AND re-verify the target field identity (see [ImeSessionIdentity])
 * before typing anything — never blind-replay the pending input.
 */
internal class ImeSessionGate {
    private var generation = 0L
    private var live: Long? = null

    /** Called from onStartInput: bumps the generation and returns the new session id. */
    fun onEditorStarted(): Long {
        generation += 1
        live = generation
        return generation
    }

    /** Called from onFinishInput: nothing captured before this is admitted again. */
    fun onEditorFinished() {
        live = null
    }

    fun currentSession(): Long? = live

    /** True only while [captured] is exactly the live editor generation. */
    fun admits(captured: Long): Boolean = live != null && live == captured
}
