package com.company.cloudctl.companion.data

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.model.PresenceIssue
import java.time.Instant
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
@org.robolectric.annotation.Config(sdk = [35])
class RuntimeStatusStorePresenceTest {
    private lateinit var context: Context
    private lateinit var store: RuntimeStatusStore
    private var now = Instant.parse("2026-09-25T00:00:00Z")

    @BeforeTest
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        preferences().edit().clear().commit()
        now = Instant.parse("2026-09-25T00:00:00Z")
        store = RuntimeStatusStore(context) { now }
    }

    @AfterTest
    fun tearDown() {
        preferences().edit().clear().commit()
    }

    @Test
    fun `new install waits for an actual heartbeat`() {
        val snapshot = store.snapshot()
        assertFalse(snapshot.presenceOnline)
        assertNull(snapshot.lastHeartbeatAt)
        assertEquals(PresenceIssue.WAITING_HEARTBEAT, snapshot.presenceIssue)
    }

    @Test
    fun `success records time and expires exactly at ninety seconds`() {
        val acknowledgedAt = now
        store.markPresence(true)
        assertEquals(acknowledgedAt, store.snapshot().lastHeartbeatAt)
        assertTrue(store.snapshot().presenceOnline)
        assertNull(store.snapshot().presenceIssue)
        now = now.plusSeconds(89)
        assertTrue(store.snapshot().presenceOnline)
        now = now.plusSeconds(1)
        assertFalse(store.snapshot().presenceOnline)
        assertEquals(PresenceIssue.HEARTBEAT_EXPIRED, store.snapshot().presenceIssue)
    }

    @Test
    fun `legacy online flag without timestamp is not accepted as fresh`() {
        preferences().edit().putBoolean("presence_online", true).commit()
        assertFalse(store.snapshot().presenceOnline)
        assertEquals(PresenceIssue.WAITING_HEARTBEAT, store.snapshot().presenceIssue)
    }

    @Test
    fun `failure is immediately offline and preserves last success`() {
        val acknowledgedAt = now
        store.markPresence(true)
        now = now.plusSeconds(10)
        store.markPresence(false, PresenceIssue.AUTH_REJECTED)
        assertFalse(store.snapshot().presenceOnline)
        assertEquals(acknowledgedAt, store.snapshot().lastHeartbeatAt)
        assertEquals(PresenceIssue.AUTH_REJECTED, store.snapshot().presenceIssue)
    }

    @Test
    fun `reconnect clears old error and refreshes timestamp`() {
        store.markPresence(false, PresenceIssue.CONNECTION_FAILED)
        now = now.plusSeconds(100)
        store.markPresence(true)
        assertTrue(store.snapshot().presenceOnline)
        assertNull(store.snapshot().presenceIssue)
        assertEquals(now, store.snapshot().lastHeartbeatAt)
    }

    @Test
    fun `status survives store recreation but cannot stay online forever`() {
        store.markPresence(true)
        now = now.plusSeconds(91)
        val restored = RuntimeStatusStore(context) { now }
        assertFalse(restored.snapshot().presenceOnline)
        assertEquals(PresenceIssue.HEARTBEAT_EXPIRED, restored.snapshot().presenceIssue)
    }

    @Test
    fun `clock rollback cannot turn future evidence into online state`() {
        store.markPresence(true)
        now = now.minusSeconds(1)
        assertFalse(store.snapshot().presenceOnline)
    }

    @Test
    fun `corrupt timestamp and unknown reason fail closed without throwing`() {
        preferences().edit()
            .putBoolean("presence_online", true)
            .putString("last_heartbeat_at", "not-a-date")
            .putString("presence_issue", "UNKNOWN_NEW_REASON")
            .commit()
        assertFalse(store.snapshot().presenceOnline)
        assertEquals(PresenceIssue.WAITING_HEARTBEAT, store.snapshot().presenceIssue)
    }

    @Test
    fun `service stop keeps historical evidence but is not online`() {
        store.markPresence(true)
        val acknowledgedAt = now
        store.markPresence(false, PresenceIssue.SERVICE_STOPPED)
        assertFalse(store.snapshot().presenceOnline)
        assertEquals(PresenceIssue.SERVICE_STOPPED, store.snapshot().presenceIssue)
        assertEquals(acknowledgedAt, store.snapshot().lastHeartbeatAt)
    }

    private fun preferences() = context.getSharedPreferences("cloudctl_runtime_status", Context.MODE_PRIVATE)
}
