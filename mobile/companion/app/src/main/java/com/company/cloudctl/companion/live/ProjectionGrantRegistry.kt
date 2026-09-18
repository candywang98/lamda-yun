package com.company.cloudctl.companion.live

/**
 * Per-session MediaProjection authorization registry (K13
 * live-capabilities/v1@20260917.1 §6, task L11 requirement 1).
 *
 * Frozen rules:
 *  - ONE user confirmation per session: [authorize] refuses a sessionId that
 *    ever held a grant; a session that lost its grant (revoked/consumed) must
 *    not be re-authorized — it is terminal and a NEW session with a fresh
 *    user confirmation takes over.
 *  - Single-use tokens: [consume] hands the projection payload out exactly
 *    once. `getMediaProjection(resultCode, data)` must only ever be called
 *    with a payload fetched through [consume] for the very session that was
 *    authorized — an Intent result from session A can never start the
 *    capture of session B (acceptance: lock screen / revoked / rotated
 *    sessions never reuse an old projection token).
 *  - Revocation is terminal and cause-recorded: user revoke (onStop), device
 *    reboot, process/service death, lock-screen teardown. A revoked grant is
 *    unusable and un-resumable (K13 §6: tokenInvalidated const true).
 *  - Rotation is NOT revocation: an in-flight session resizes its virtual
 *    display and keeps streaming; the grant stays consumed-but-alive. Only a
 *    stop of the projection ends it.
 *
 * The registry is generic over the payload so the pure logic stays
 * JVM-testable; the Android glue binds it to resultCode+Intent data.
 */
class ProjectionGrantRegistry<P : Any> {

    enum class GrantState { AUTHORIZED, CONSUMED, REVOKED }

    data class Grant<P>(
        val sessionId: String,
        val grantId: Long,
        val payload: P,
        val grantedAtMs: Long,
        val state: GrantState,
        val consumedAtMs: Long? = null,
    )

    data class Revocation(
        val sessionId: String,
        val grantId: Long,
        val cause: String,
        val atMs: Long,
        val priorState: GrantState,
    )

    private val lock = Any()
    private val grants = LinkedHashMap<String, Grant<P>>()
    private val revocations = ArrayList<Revocation>()
    private var nextGrantId = 0L

    /**
     * Records a fresh user-confirmed MediaProjection authorization for
     * [sessionId]. Fails when this session ever held a grant: one
     * confirmation per session, ever.
     */
    fun authorize(sessionId: String, payload: P, nowMs: Long): Grant<P> = synchronized(lock) {
        require(sessionId.isNotBlank()) { "sessionId must not be blank" }
        check(!grants.containsKey(sessionId)) {
            "session $sessionId was already authorized once; one MediaProjection confirmation per session"
        }
        nextGrantId += 1
        Grant(
            sessionId = sessionId,
            grantId = nextGrantId,
            payload = payload,
            grantedAtMs = nowMs,
            state = GrantState.AUTHORIZED,
        ).also { grants[sessionId] = it }
    }

    /**
     * Single-use handout of the projection payload. Returns the grant the
     * first time an AUTHORIZED session asks, flips it to CONSUMED, and
     * returns null afterwards (token spent, unknown session, or revoked).
     */
    fun consume(sessionId: String, nowMs: Long): Grant<P>? = synchronized(lock) {
        val grant = grants[sessionId] ?: return null
        if (grant.state != GrantState.AUTHORIZED) return null
        val consumed = grant.copy(state = GrantState.CONSUMED, consumedAtMs = nowMs)
        grants[sessionId] = consumed
        consumed
    }

    /**
     * Terminal invalidation (user revoke / onStop, reboot, service crash,
     * session close). Idempotent; returns the revocation record for auditing
     * or null when there was nothing to revoke.
     */
    fun revoke(sessionId: String, cause: String, nowMs: Long): Revocation? = synchronized(lock) {
        val grant = grants[sessionId] ?: return null
        if (grant.state == GrantState.REVOKED) return null
        grants[sessionId] = grant.copy(state = GrantState.REVOKED)
        Revocation(
            sessionId = sessionId,
            grantId = grant.grantId,
            cause = cause,
            atMs = nowMs,
            priorState = grant.state,
        ).also { revocations.add(it) }
    }

    /** Process-wide teardown (device reboot / companion process restart). */
    fun revokeAll(cause: String, nowMs: Long): List<Revocation> = synchronized(lock) {
        grants.keys.toList().mapNotNull { revoke(it, cause, nowMs) }
    }

    fun stateOf(sessionId: String): GrantState? = synchronized(lock) { grants[sessionId]?.state }

    fun grantOf(sessionId: String): Grant<P>? = synchronized(lock) { grants[sessionId] }

    fun revocations(): List<Revocation> = synchronized(lock) { revocations.toList() }

    companion object {
        /** Revocation causes, aligned with the L10 TERMINAL_CAUSES vocabulary. */
        const val CAUSE_USER_REVOKED = "PROJECTION_REVOKED"
        const val CAUSE_SESSION_CLOSED = "SERVER_CLOSED"
        const val CAUSE_OPERATOR_STOP = "OPERATOR_STOP"
        const val CAUSE_DEVICE_REBOOT = "DEVICE_REBOOT"
        const val CAUSE_SERVICE_CRASH = "SERVICE_CRASH"
    }
}
