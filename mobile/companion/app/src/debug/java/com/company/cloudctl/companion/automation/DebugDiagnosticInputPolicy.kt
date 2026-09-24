package com.company.cloudctl.companion.automation

/**
 * Debug-only admission of one isolated multiline field.
 *
 * This file lives in src/debug. The release variant does not compile it, so
 * the diagnostic package cannot be admitted by a release APK even if a caller
 * tries to install a policy. It does not add the package to
 * [TargetLocatorRegistry], the cloud task parser, or any business allowlist.
 */
internal object DebugDiagnosticInputPolicy : DiagnosticInputPolicy {
    const val PACKAGE = "com.company.cloudctl.inputharness"
    const val FIELD = "harness_multiline_field"
    const val VIEW_ID = "com.company.cloudctl.inputharness:id/harness_multiline_field"

    override fun admits(targetPackage: String, locatorRef: String): Boolean =
        targetPackage == PACKAGE && locatorRef == FIELD

    override fun locator(targetPackage: String, locatorRef: String): ApprovedLocator? =
        if (admits(targetPackage, locatorRef)) ApprovedLocator.ResourceId(VIEW_ID) else null

    override fun skipsRootNavigation(targetPackage: String): Boolean = targetPackage == PACKAGE
}
