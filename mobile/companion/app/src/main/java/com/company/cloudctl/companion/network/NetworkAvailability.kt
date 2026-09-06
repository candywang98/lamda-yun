package com.company.cloudctl.companion.network

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import kotlinx.coroutines.suspendCancellableCoroutine
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.coroutines.resume

class NetworkAvailability(context: Context) {
    private val connectivity = context.getSystemService(ConnectivityManager::class.java)

    fun isValidated(): Boolean {
        val network = connectivity.activeNetwork ?: return false
        val capabilities = connectivity.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }

    suspend fun awaitValidated() {
        if (isValidated()) return
        suspendCancellableCoroutine { continuation ->
            val completed = AtomicBoolean(false)
            lateinit var callback: ConnectivityManager.NetworkCallback
            fun finish() {
                if (completed.compareAndSet(false, true)) {
                    runCatching { connectivity.unregisterNetworkCallback(callback) }
                    continuation.resume(Unit)
                }
            }
            callback = object : ConnectivityManager.NetworkCallback() {
                override fun onCapabilitiesChanged(
                    network: Network,
                    capabilities: NetworkCapabilities,
                ) {
                    if (
                        capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
                        capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
                    ) {
                        finish()
                    }
                }
            }
            continuation.invokeOnCancellation {
                if (completed.compareAndSet(false, true)) {
                    runCatching { connectivity.unregisterNetworkCallback(callback) }
                }
            }
            connectivity.registerNetworkCallback(
                NetworkRequest.Builder()
                    .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    .build(),
                callback,
            )
            if (isValidated()) finish()
        }
    }
}
