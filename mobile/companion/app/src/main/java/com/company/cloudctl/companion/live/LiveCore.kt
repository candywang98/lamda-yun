package com.company.cloudctl.companion.live


/** Monotonic input sequence guard for remote control (p10-live/20260913.1). */
class InputSeqGuard(initial: Int = 0) {
    var last: Int = initial
        private set

    /** Returns true when the sequence advances; stale or replayed ids are rejected. */
    fun accept(seq: Int): Boolean {
        if (seq <= last) return false
        last = seq
        return true
    }

    fun reset(baseline: Int = 0) {
        last = baseline
    }
}

/** Bounded frame capture parameters; pure calculation for unit tests. */
data class FrameParams(
    val maxWidth: Int = 720,
    val jpegQuality: Int = 60,
    val remoteFps: Int = 5,
    val viewingFps: Int = 1,
) {
    init {
        require(maxWidth in 320..1080)
        require(jpegQuality in 30..80)
        require(remoteFps in 1..10 && viewingFps in 1..remoteFps)
    }

    fun scale(width: Int, height: Int): Pair<Int, Int> {
        if (width <= 0 || height <= 0) return 0 to 0
        if (width <= maxWidth) return width to height
        val ratio = maxWidth.toFloat() / width
        return maxWidth to (height * ratio).toInt().coerceAtLeast(1)
    }

    fun fps(remote: Boolean): Int = if (remote) remoteFps else viewingFps

    fun intervalMs(remote: Boolean): Long = 1000L / fps(remote)

    companion object {
        val DEFAULT = FrameParams()
    }
}

/**
 * Client-side session state machine mirroring the server (p10-live/20260913.1).
 * Pure states; transport is handled by LiveSessionController.
 */
enum class LiveClientState { IDLE, VIEWING, REMOTE, CLOSED }

class LiveClientStateMachine {
    var state: LiveClientState = LiveClientState.IDLE
        private set
    val guard = InputSeqGuard()

    fun onOpened() {
        check(state == LiveClientState.IDLE) { "session already open" }
        state = LiveClientState.VIEWING
    }

    fun onTakeControl() {
        check(state == LiveClientState.VIEWING) { "take-control requires VIEWING" }
        state = LiveClientState.REMOTE
        guard.reset(0) // server restarts its sequence on take-control
    }

    fun onRelease() {
        check(state == LiveClientState.REMOTE) { "release requires REMOTE" }
        state = LiveClientState.VIEWING
    }

    fun onClosed() {
        state = LiveClientState.CLOSED
    }
}
