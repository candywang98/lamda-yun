package com.company.cloudctl.companion.control

/**
 * B17 merge-write utility for `enabled_accessibility_services`.
 *
 * Read-modify-write that NEVER drops other services: the existing set is
 * read, our own component is appended only when missing, and the union is
 * written back. A missing WRITE_SECURE_SETTINGS grant throws before any
 * write is attempted.
 *
 * Deliberately NOT wired into startup or sync: [ENABLED_BY_DEFAULT] is false
 * and no production call site exists yet. It ships so the capability check
 * CAP_WRITE_SECURE_SETTINGS can be paired with a safe writer once the fleet
 * onboarding (A14-merged rollout) turns it on.
 */
class SecureSettingsMergeWriter(
    private val checkPermission: () -> Boolean,
    private val readEnabledServices: () -> String?,
    private val writeEnabledServices: (String) -> Boolean,
) {
    class MissingWriteSecureSettingsPermission :
        IllegalStateException("WRITE_SECURE_SETTINGS not granted; refusing to touch enabled_accessibility_services")

    data class MergeResult(val changed: Boolean, val mergedValue: String)

    fun mergeAppendOwnService(ownComponent: String): MergeResult {
        require(ownComponent.isNotBlank()) { "ownComponent must not be blank" }
        if (!checkPermission()) throw MissingWriteSecureSettingsPermission()
        val current = readEnabledServices().orEmpty()
        val services = current.split(':').map { it.trim() }.filter { it.isNotBlank() }
        if (services.any { it.equals(ownComponent, ignoreCase = true) }) {
            return MergeResult(changed = false, mergedValue = current)
        }
        val merged = (services + ownComponent).joinToString(":")
        if (!writeEnabledServices(merged)) {
            throw IllegalStateException("Settings.Secure write of enabled_accessibility_services failed")
        }
        return MergeResult(changed = true, mergedValue = merged)
    }

    companion object {
        /** Disabled until the controller wires it into fleet onboarding. */
        const val ENABLED_BY_DEFAULT = false
    }
}
