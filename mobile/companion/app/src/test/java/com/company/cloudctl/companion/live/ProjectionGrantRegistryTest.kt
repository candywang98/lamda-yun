package com.company.cloudctl.companion.live

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * L11 requirement 1 + acceptance 1: per-session MediaProjection
 * authorization. One user confirmation per session, single-use tokens, and
 * no cross-session token reuse after lock screen / revocation / rotation
 * (K13 §6: tokenInvalidated const true — a new session must obtain a fresh
 * on-device user confirmation).
 */
class ProjectionGrantRegistryTest {
    private class Token(val id: String)

    @Test
    fun oneConfirmationPerSession() {
        val registry = ProjectionGrantRegistry<Token>()
        registry.authorize("live-a", Token("a1"), nowMs = 100)
        // The same session may not confirm twice — the second confirmation
        // belongs to a NEW session id.
        assertFailsWith<IllegalStateException> {
            registry.authorize("live-a", Token("a2"), nowMs = 200)
        }
    }

    @Test
    fun grantIsSingleUse() {
        val registry = ProjectionGrantRegistry<Token>()
        registry.authorize("live-a", Token("a1"), nowMs = 100)
        val first = assertNotNull(registry.consume("live-a", nowMs = 150))
        assertEquals("a1", first.payload.id)
        assertEquals(ProjectionGrantRegistry.GrantState.CONSUMED, first.state)
        // A replayed start intent (same session, spent token) gets nothing.
        assertNull(registry.consume("live-a", nowMs = 151))
    }

    @Test
    fun lockScreenOrRevokeKillsTheTokenForFutureSessions() {
        val registry = ProjectionGrantRegistry<Token>()
        val token = Token("a1")
        registry.authorize("live-a", token, nowMs = 100)
        assertNotNull(registry.consume("live-a", nowMs = 120))

        // Lock screen / user revoke / system teardown -> onStop.
        val revocation = assertNotNull(
            registry.revoke("live-a", ProjectionGrantRegistry.CAUSE_USER_REVOKED, nowMs = 500),
        )
        assertEquals(ProjectionGrantRegistry.CAUSE_USER_REVOKED, revocation.cause)
        assertEquals(ProjectionGrantRegistry.GrantState.REVOKED, registry.stateOf("live-a"))

        // NEW session: the old token is nowhere to be found — consume
        // returns null until a fresh user confirmation is recorded, and the
        // old payload can never be re-authorized for the new session id
        // through any API.
        assertNull(registry.consume("live-b", nowMs = 600))
        assertNull(registry.grantOf("live-b"))
        assertFalse(registry.stateOf("live-b") == ProjectionGrantRegistry.GrantState.AUTHORIZED)

        // The revoked session itself is terminal: no re-authorization, no
        // re-consumption (K13 §6: resumable false, reauthorizationRequired
        // true — for a NEW session).
        assertNull(registry.consume("live-a", nowMs = 700))
        assertFailsWith<IllegalStateException> {
            registry.authorize("live-a", Token("fresh"), nowMs = 800)
        }
    }

    @Test
    fun rotationResizeDoesNotConsumeOrRevokeAGrant() {
        // Rotation mid-session is a resize, not a teardown: the in-flight
        // CONSUMED grant stays alive and the capture keeps streaming.
        val registry = ProjectionGrantRegistry<Token>()
        registry.authorize("live-a", Token("a1"), nowMs = 100)
        assertNotNull(registry.consume("live-a", nowMs = 120))

        // ... resize happens in MediaProjectionService without touching the
        // registry (no revoke, no second consume) ...
        assertEquals(ProjectionGrantRegistry.GrantState.CONSUMED, registry.stateOf("live-a"))
        assertTrue(registry.revocations().isEmpty())

        // But once the rotated session DOES end, its token is dead and the
        // next session starts from a fresh confirmation.
        assertNotNull(registry.revoke("live-a", ProjectionGrantRegistry.CAUSE_SESSION_CLOSED, nowMs = 900))
        assertNull(registry.consume("live-b", nowMs = 950))
        registry.authorize("live-b", Token("b1"), nowMs = 1000)
        assertEquals("b1", assertNotNull(registry.consume("live-b", nowMs = 1010)).payload.id)
    }

    @Test
    fun processRestartInvalidatesEverything() {
        val registry = ProjectionGrantRegistry<Token>()
        registry.authorize("live-a", Token("a1"), nowMs = 100)
        registry.authorize("live-b", Token("b1"), nowMs = 110)
        val revoked = registry.revokeAll(ProjectionGrantRegistry.CAUSE_DEVICE_REBOOT, nowMs = 200)
        assertEquals(2, revoked.size)
        assertEquals(ProjectionGrantRegistry.GrantState.REVOKED, registry.stateOf("live-a"))
        assertEquals(ProjectionGrantRegistry.GrantState.REVOKED, registry.stateOf("live-b"))
        assertNull(registry.consume("live-a", nowMs = 300))
        assertNull(registry.consume("live-b", nowMs = 300))
        // Revocation is idempotent.
        assertNull(registry.revoke("live-a", ProjectionGrantRegistry.CAUSE_DEVICE_REBOOT, nowMs = 400))
    }

    @Test
    fun grantIdsAreUniqueAndBoundToTheirSession() {
        val registry = ProjectionGrantRegistry<Token>()
        val ga = registry.authorize("live-a", Token("a1"), nowMs = 100)
        val gb = registry.authorize("live-b", Token("b1"), nowMs = 110)
        assertTrue(ga.grantId != gb.grantId)
        // Consuming b's grant never hands out a's payload and vice versa —
        // the MediaProjectionService start check (grantId extra must equal
        // the consumed grant's id) closes the replay window.
        assertEquals("b1", assertNotNull(registry.consume("live-b", nowMs = 120)).payload.id)
        assertEquals(ProjectionGrantRegistry.GrantState.AUTHORIZED, registry.stateOf("live-a"))
    }
}
