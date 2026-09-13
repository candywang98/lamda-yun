package com.company.cloudctl.companion.automation

/**
 * Idlefish publish fields are Flutter semantics views, not Android EditTexts.
 * Numeric prices go through the on-screen keypad; descriptions must not.
 */
internal object FlutterTextCommit {
    fun isNumericPrice(value: String): Boolean {
        if (value.isEmpty()) return false
        var digits = 0
        var dots = 0
        for (character in value) {
            when {
                character.isDigit() -> digits += 1
                character == '.' -> {
                    dots += 1
                    if (dots > 1) return false
                }
                else -> return false
            }
        }
        return digits > 0
    }

    fun accepted(haystack: String, expected: String): Boolean {
        if (expected.isBlank()) return false
        if (expected in haystack) return true
        val compactExpected = expected.replace(whitespace, "")
        val compactHaystack = haystack.replace(whitespace, "")
        if (compactExpected.length >= 8 && compactExpected in compactHaystack) return true
        val prefix = expected.take(16)
        return prefix.length >= 8 && prefix in haystack
    }

    private val whitespace = Regex("\\s+")
}
