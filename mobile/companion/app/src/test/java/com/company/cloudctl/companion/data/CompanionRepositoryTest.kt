package com.company.cloudctl.companion.data

import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class CompanionRepositoryTest {
    @Test
    fun clearsLocalBindingOnlyAfterRemoteRevocationSucceeds() = runBlocking {
        val events = mutableListOf<String>()
        revokeThenClear(
            revoke = { events += "remote-revoked" },
            clear = { events += "local-cleared" },
        )
        assertEquals(listOf("remote-revoked", "local-cleared"), events)
    }

    @Test
    fun retainsLocalBindingWhenRemoteRevocationFails() = runBlocking {
        val events = mutableListOf<String>()
        assertFailsWith<IllegalStateException> {
            revokeThenClear(
                revoke = {
                    events += "remote-failed"
                    error("offline")
                },
                clear = { events += "local-cleared" },
            )
        }
        assertEquals(listOf("remote-failed"), events)
    }
}
