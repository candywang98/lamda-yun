package com.company.cloudctl.companion.automation

/**
 * Idlefish numeric sheet keys. Do not strip trailing zeros from whole numbers:
 * "10" and "199" must be typed as-is. Only trim fractional trailing zeros.
 */
internal object PriceKeypad {
    fun keys(value: String): String {
        val trimmed = value.trim()
        if (trimmed.isEmpty()) return trimmed
        val decimal = trimmed.indexOf('.')
        if (decimal < 0) return trimmed
        return trimmed.trimEnd('0').trimEnd('.')
    }

    fun acceptedOnForm(haystack: String, value: String): Boolean {
        val typed = keys(value)
        if (typed.isEmpty()) return false
        return typed in haystack || "¥$typed" in haystack || "$typed.00" in haystack
    }
}
