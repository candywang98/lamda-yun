package com.company.cloudctl.companion.automation

/**
 * Closed diagnostic seam for a debug-only isolated input field.
 *
 * Production allowlists stay here. This type never names a diagnostic package,
 * locator, or step: the release source set implements [Closed] and the debug
 * source set is the only place that can admit one fixed package and one fixed
 * locator. Main code must not reference that debug type — release would not
 * compile it.
 *
 * Admission is read-only. It does not authorize tap, swipe, back, restart,
 * send, publish, review, price, clipboard, or a second step.
 */
internal interface DiagnosticInputPolicy {
    fun admits(targetPackage: String, locatorRef: String): Boolean

    /**
     * How the admitted field is resolved. Production packages return null and
     * keep using [TargetLocatorRegistry].
     */
    fun locator(targetPackage: String, locatorRef: String): ApprovedLocator?

    /** True when a fresh run of this package must not press BACK or relaunch. */
    fun skipsRootNavigation(targetPackage: String): Boolean

    object Closed : DiagnosticInputPolicy {
        override fun admits(targetPackage: String, locatorRef: String): Boolean = false
        override fun locator(targetPackage: String, locatorRef: String): ApprovedLocator? = null
        override fun skipsRootNavigation(targetPackage: String): Boolean = false
    }

    companion object {
        /**
         * The policy compiled into this variant. Debug and release each provide
         * [DiagnosticInputPolicyProvider] in their own source set. There is no
         * setter: a caller in the same process cannot install a different policy.
         */
        val installed: DiagnosticInputPolicy
            get() = DiagnosticInputPolicyProvider.policy
    }
}
