package com.company.cloudctl.companion.data

import com.company.cloudctl.companion.model.AccountAuthorizationStatus
import com.company.cloudctl.companion.model.CompanionState
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update

/** Publish local liveness before I/O; a delayed account reply cannot restore old device state. */
internal suspend fun refreshAccountStatus(
    state: MutableStateFlow<CompanionState>,
    refreshLocal: () -> Unit,
    loadAccounts: suspend (CompanionState) -> List<AccountAuthorizationStatus>,
) {
    refreshLocal()
    val requestedFor = state.value
    val accounts = try {
        loadAccounts(requestedFor)
    } catch (cancelled: CancellationException) {
        throw cancelled
    } catch (_: Exception) {
        // Preserve the latest account state, not the pre-request snapshot.
        refreshLocal()
        return
    }
    if (state.value.binding != requestedFor.binding) return
    refreshLocal()
    state.update { current ->
        if (current.binding == requestedFor.binding) current.copy(accountStatuses = accounts) else current
    }
}
