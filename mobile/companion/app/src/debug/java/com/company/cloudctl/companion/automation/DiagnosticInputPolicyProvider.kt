package com.company.cloudctl.companion.automation

/**
 * Debug variant. The only policy this process can observe is the fixed harness
 * field. Nothing assigns it.
 */
internal object DiagnosticInputPolicyProvider {
    val policy: DiagnosticInputPolicy = DebugDiagnosticInputPolicy
}
