package com.company.cloudctl.companion.ime

internal object ImeAvailability {
    const val RELATIVE_ID = ".ime.CloudCtlInputMethod"

    fun candidates(packageName: String): Set<String> = setOf(
        "$packageName/$packageName$RELATIVE_ID",
        "$packageName/$RELATIVE_ID",
    )

    fun listed(csv: String?, packageName: String): Boolean {
        val wanted = candidates(packageName)
        return csv.orEmpty()
            .split(':', ';')
            .map { it.trim() }
            .any { item -> wanted.any { it.equals(item, ignoreCase = true) } }
    }
}
