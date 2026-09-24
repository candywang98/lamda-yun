package com.company.cloudctl.companion.data

import com.company.cloudctl.companion.service.DebugBindingGuard

/**
 * Debug variant of the hook [CompanionRepository.saveBinding] calls.
 *
 * A debug install refuses to persist the preference that
 * [com.company.cloudctl.companion.service.CompanionServiceStarter] treats as
 * "bound". Release compiles a same-named type that does not refuse.
 */
internal object BindingWritePolicy {
    fun beforeSave() {
        DebugBindingGuard.rejectWrite()
    }
}
