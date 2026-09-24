package com.company.cloudctl.companion.service

import android.content.Context

/**
 * Debug builds never persist a device binding.
 *
 * [CompanionServiceStarter.tryStartIfBound] starts [CompanionSyncService] only
 * when this preference is non-blank, and that service claims. The debug
 * application id is a different package, so it does not see production's
 * preference file. This guard is the second line: enrollment cannot write one
 * into the debug data directory either. Release has no equivalent type and
 * keeps saving bindings.
 */
internal object DebugBindingGuard {
    const val PREFERENCES = "cloudctl_binding"
    const val KEY = "binding"

    fun rejectWrite() {
        throw IllegalStateException("DEBUG_BINDING_FORBIDDEN")
    }

    fun hasBinding(context: Context): Boolean =
        !context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            .getString(KEY, null)
            .isNullOrBlank()
}
