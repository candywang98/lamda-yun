package com.company.cloudctl.companion.automation

/**
 * Release keeps the diagnostic seam closed.
 *
 * There is no install method and no diagnostic package constant. The debug
 * policy type is not on this source set, so release cannot name it. The policy
 * the process reads is [DiagnosticInputPolicyProvider], which is this closed
 * instance and has no setter.
 */
internal object ReleaseDiagnosticInputPolicy {
    val policy: DiagnosticInputPolicy = DiagnosticInputPolicyProvider.policy
}
