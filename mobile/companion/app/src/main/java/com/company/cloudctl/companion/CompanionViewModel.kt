package com.company.cloudctl.companion

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.company.cloudctl.companion.data.CompanionRepository
import com.company.cloudctl.companion.network.EnrollmentParser
import com.company.cloudctl.companion.network.PinnedHttpsCompanionCloudClient
import com.company.cloudctl.companion.operations.OperationDefinition
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class CompanionViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = CompanionRepository(application, PinnedHttpsCompanionCloudClient())
    val state = repository.state
    private var refreshJob: Job? = null

    init {
        viewModelScope.launch {
            while (isActive) {
                delay(REFRESH_INTERVAL_MILLIS)
                if (state.value.binding != null) refreshIfIdle()
            }
        }
        viewModelScope.launch {
            while (isActive) {
                repository.refreshPresence()
                delay(LOCAL_STATUS_INTERVAL_MILLIS)
            }
        }
    }

    fun enroll(cloudUrl: String, code: String, certificateSha256: String) {
        viewModelScope.launch {
            try {
                repository.enroll(EnrollmentParser.parse(cloudUrl, code, certificateSha256))
            } catch (error: Exception) {
                Log.e("CloudCtlCompanion", "enrollment failed", error)
                repository.reportError(error)
            }
        }
    }

    fun refresh() = refreshIfIdle()
    fun enqueuePlaceholderOperation(
        definition: OperationDefinition,
        parameters: Map<String, String> = emptyMap()
    ) = viewModelScope.launch { repository.enqueuePlaceholderOperation(definition, parameters) }
    fun toggleState(key: String): Boolean = repository.toggleState(key)
    fun setToggle(definition: OperationDefinition, enabled: Boolean) =
        viewModelScope.launch { repository.setToggle(definition, enabled) }
    fun emergencyStop() = viewModelScope.launch { repository.emergencyStop() }
    fun answerConfirmation(approved: Boolean) =
        viewModelScope.launch { repository.answerConfirmation(approved) }

    fun unbind() = viewModelScope.launch { repository.unbind() }

    private fun refreshIfIdle() {
        repository.refreshLocalStatus()
        if (refreshJob?.isActive == true) return
        refreshJob = viewModelScope.launch { repository.refresh() }
    }

    private companion object {
        const val REFRESH_INTERVAL_MILLIS = 30_000L
        const val LOCAL_STATUS_INTERVAL_MILLIS = 5_000L
    }
}
