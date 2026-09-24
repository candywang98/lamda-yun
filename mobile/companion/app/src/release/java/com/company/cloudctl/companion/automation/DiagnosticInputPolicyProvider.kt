package com.company.cloudctl.companion.automation

/**
 * Release variant. The policy is the closed one and there is no other.
 * [ReleaseDiagnosticInputPolicy] no longer has a method that writes a field,
 * because there is no field to write.
 */
internal object DiagnosticInputPolicyProvider {
    val policy: DiagnosticInputPolicy = DiagnosticInputPolicy.Closed
}
