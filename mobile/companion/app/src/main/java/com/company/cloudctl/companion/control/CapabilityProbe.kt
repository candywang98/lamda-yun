package com.company.cloudctl.companion.control

import android.content.Context
import android.provider.Settings
import com.company.cloudctl.companion.automation.CloudCtlAccessibilityService
import com.company.cloudctl.companion.data.CapabilityProbeStatus

/**
 * B17 startup capability self-check. Each capability is probed through an
 * injected detector so the policy is pure-JVM testable; [production] wires
 * the real Android detectors.
 *
 * `detected == null` means "cannot be verified in-process" (e.g. ADB motion
 * injection requires an external channel) — the profile then shows UNKNOWN
 * instead of a false negative.
 */
class CapabilityProbe(
    private val accessibilityBound: () -> Boolean,
    private val accessibilityEnabledInSettings: () -> Boolean,
    private val defaultImeComponent: () -> String?,
    private val ownImeComponent: () -> String,
    private val writeSecureSettingsGranted: () -> Boolean,
    private val adbMotionInjectionAvailable: () -> Boolean?,
) {
    fun probe(): Map<String, CapabilityProbeStatus> = mapOf(
        CAP_ACCESSIBILITY_BOUND to CapabilityProbeStatus(
            CAP_ACCESSIBILITY_BOUND,
            accessibilityBound() && accessibilityEnabledInSettings(),
            if (accessibilityBound() && accessibilityEnabledInSettings()) {
                "accessibility service enabled and bound"
            } else {
                "accessibility service not enabled or not bound"
            },
        ),
        CAP_IME_DEFAULT to CapabilityProbeStatus(
            CAP_IME_DEFAULT,
            defaultImeComponent()?.let { it.equals(ownImeComponent(), ignoreCase = true) } == true,
            "default IME ${defaultImeComponent() ?: "unset"}",
        ),
        // Detection only: the merge writer (SecureSettingsMergeWriter) stays
        // unwired by default — nothing writes secure settings on its own.
        CAP_WRITE_SECURE_SETTINGS to CapabilityProbeStatus(
            CAP_WRITE_SECURE_SETTINGS,
            writeSecureSettingsGranted(),
            if (writeSecureSettingsGranted()) {
                "WRITE_SECURE_SETTINGS granted; merge writer available but disabled"
            } else {
                "WRITE_SECURE_SETTINGS not granted (adb pm grant required)"
            },
        ),
        CAP_ADB_MOTION_INJECTION to CapabilityProbeStatus(
            CAP_ADB_MOTION_INJECTION,
            adbMotionInjectionAvailable(),
            "external adb channel; cannot be verified in-process",
        ),
    )

    companion object {
        const val CAP_ACCESSIBILITY_BOUND = "CAP_ACCESSIBILITY_BOUND"
        const val CAP_IME_DEFAULT = "CAP_IME_DEFAULT"
        const val CAP_WRITE_SECURE_SETTINGS = "CAP_WRITE_SECURE_SETTINGS"
        const val CAP_ADB_MOTION_INJECTION = "CAP_ADB_MOTION_INJECTION"

        /** Real-device detectors; every read is best-effort and fails to false/null. */
        fun production(context: Context, packageName: String = context.packageName): CapabilityProbe {
            val relativeAccessibility = "$packageName/.automation.CloudCtlAccessibilityService"
            return CapabilityProbe(
                accessibilityBound = { CloudCtlAccessibilityService.active != null },
                accessibilityEnabledInSettings = {
                    runCatching {
                        val enabled = Settings.Secure.getString(
                            context.contentResolver,
                            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
                        ).orEmpty()
                        enabled.split(':').any {
                            it.equals(relativeAccessibility, ignoreCase = true) ||
                                it.equals("$packageName/$relativeAccessibility", ignoreCase = true)
                        }
                    }.getOrDefault(false)
                },
                defaultImeComponent = {
                    runCatching {
                        Settings.Secure.getString(
                            context.contentResolver,
                            Settings.Secure.DEFAULT_INPUT_METHOD,
                        )
                    }.getOrNull()
                },
                ownImeComponent = { "$packageName/.ime.CloudCtlInputMethod" },
                writeSecureSettingsGranted = {
                    runCatching {
                        context.checkSelfPermission(android.Manifest.permission.WRITE_SECURE_SETTINGS) ==
                            android.content.pm.PackageManager.PERMISSION_GRANTED
                    }.getOrDefault(false)
                },
                // No in-process channel can prove adb `input` reachability;
                // real-device verification belongs to Q13 device acceptance.
                adbMotionInjectionAvailable = { null },
            )
        }
    }
}
