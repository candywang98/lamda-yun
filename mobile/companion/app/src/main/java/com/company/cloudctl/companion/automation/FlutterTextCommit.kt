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

    /**
     * A description readback only counts when the whole expected text is present
     * (whitespace-normalized). Prefix matching once let a stale draft that merely
     * shared an opening pass as a successful fill, so it is deliberately rejected.
     */
    fun accepted(haystack: String, expected: String): Boolean {
        if (expected.isBlank()) return false
        if (expected in haystack) return true
        val compactExpected = expected.replace(whitespace, "")
        val compactHaystack = haystack.replace(whitespace, "")
        return compactExpected.length >= 8 && compactExpected in compactHaystack
    }

    private val whitespace = Regex("\\s+")
}
