package com.company.cloudctl.companion.data

import com.company.cloudctl.companion.model.AccountAuthorizationStatus
import com.company.cloudctl.companion.model.CompanionState
import com.company.cloudctl.companion.model.DeviceBinding
import com.company.cloudctl.companion.model.PresenceIssue
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

class AccountStatusRefreshTest {
    private val binding = DeviceBinding("binding-a", "device-a", "test", "test", "https://example.invalid", "pin")
    private val account = AccountAuthorizationStatus("account-a", "xianyu", "test", "ACTIVE", true, boundToDevice = true)

    @Test
    fun `local status is published before slow network call and stays fresh afterwards`() = runBlocking {
        val state = MutableStateFlow(CompanionState(binding = binding))
        val response = CompletableDeferred<List<AccountAuthorizationStatus>>()
        var online = true
        var refreshes = 0
        val refreshLocal = {
            refreshes++
            state.value = state.value.copy(
                presenceOnline = online,
                presenceIssue = if (online) null else PresenceIssue.HEARTBEAT_EXPIRED,
            )
        }
        val job = launch(start = CoroutineStart.UNDISPATCHED) {
            refreshAccountStatus(state, refreshLocal) {
                assertTrue(state.value.presenceOnline)
                response.await()
            }
        }
        assertTrue(job.isActive)
        assertEquals(1, refreshes)
        online = false
        refreshLocal()
        assertFalse(state.value.presenceOnline)
        response.complete(listOf(account))
        job.join()
        assertEquals(3, refreshes)
        assertFalse(state.value.presenceOnline)
        assertEquals(PresenceIssue.HEARTBEAT_EXPIRED, state.value.presenceIssue)
        assertEquals(listOf(account), state.value.accountStatuses)
    }

    @Test
    fun `slow account response cannot undo unbinding`() = runBlocking {
        val state = MutableStateFlow(CompanionState(binding = binding))
        val response = CompletableDeferred<List<AccountAuthorizationStatus>>()
        val job = launch(start = CoroutineStart.UNDISPATCHED) {
            refreshAccountStatus(state, {}) { response.await() }
        }
        state.value = CompanionState()
        response.complete(listOf(account))
        job.join()
        assertNull(state.value.binding)
        assertTrue(state.value.accountStatuses.isEmpty())
    }

    @Test
    fun `response for old binding cannot replace new binding account status`() = runBlocking {
        val newBinding = binding.copy(bindingId = "binding-b", deviceId = "device-b")
        val newAccount = account.copy(accountId = "account-b")
        val state = MutableStateFlow(CompanionState(binding = binding))
        val response = CompletableDeferred<List<AccountAuthorizationStatus>>()
        val job = launch(start = CoroutineStart.UNDISPATCHED) {
            refreshAccountStatus(state, {}) { response.await() }
        }
        state.value = CompanionState(binding = newBinding, accountStatuses = listOf(newAccount))
        response.complete(listOf(account))
        job.join()
        assertEquals(newBinding, state.value.binding)
        assertEquals(listOf(newAccount), state.value.accountStatuses)
    }

    @Test
    fun `failed network call cannot roll back already published local status`() = runBlocking {
        val state = MutableStateFlow(CompanionState(binding = binding, presenceOnline = true, accountStatuses = listOf(account)))
        refreshAccountStatus(state, {
            state.value = state.value.copy(presenceOnline = false, presenceIssue = PresenceIssue.HEARTBEAT_EXPIRED)
        }) { error("test network failure") }
        assertEquals(listOf(account), state.value.accountStatuses)
        assertFalse(state.value.presenceOnline)
        assertEquals(PresenceIssue.HEARTBEAT_EXPIRED, state.value.presenceIssue)
    }

    @Test
    fun `failed delayed request preserves newer account state`() = runBlocking {
        val state = MutableStateFlow(CompanionState(binding = binding, accountStatuses = listOf(account)))
        val response = CompletableDeferred<List<AccountAuthorizationStatus>>()
        val job = launch(start = CoroutineStart.UNDISPATCHED) {
            refreshAccountStatus(state, {}) { response.await() }
        }
        val newer = account.copy(status = "REVOKED", authorized = false)
        state.value = state.value.copy(accountStatuses = listOf(newer))
        response.completeExceptionally(java.io.IOException("network disconnected"))
        job.join()
        assertEquals(listOf(newer), state.value.accountStatuses)
    }

    @Test
    fun `cancellation propagates without applying a stale account result`() = runBlocking {
        val state = MutableStateFlow(CompanionState(binding = binding))
        assertFailsWith<CancellationException> {
            refreshAccountStatus(state, {}) { throw CancellationException("cancelled test") }
        }
        assertTrue(state.value.accountStatuses.isEmpty())
    }
}
