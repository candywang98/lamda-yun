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

    /** Keypad-typeable: digits plus at most one decimal point. */
    fun keypadable(value: String): Boolean {
        val typed = keys(value)
        return typed.isNotEmpty() &&
            typed.count { it == '.' } <= 1 &&
            typed.all { it.isDigit() || it == '.' }
    }

    private val groupedAmount = Regex("\\d{1,3}(?:,\\d{3})+(?:\\.\\d+)?")
    private val plainAmount = Regex("\\d+(?:\\.\\d+)?")

    /**
     * The number tokens actually displayed on the form, comma-grouped amounts like
     * "1,299.00" included. Acceptance compares TOKENS numerically, never substring
     * presence: an amount that ACCUMULATED on an uncleared field ("10199" after
     * typing "199" over a leftover "10") must not pass for the intended price even
     * though "199" is a substring of it.
     */
    fun displayedAmounts(haystack: String): List<String> {
        val grouped = groupedAmount.findAll(haystack).map { it.value }.toList()
        val remainder = groupedAmount.replace(haystack, " ")
        return grouped + plainAmount.findAll(remainder).map { it.value }
    }

    /** Numeric equality of the intended price against every displayed amount token. */
    fun acceptedOnForm(haystack: String, value: String): Boolean {
        val typed = keys(value)
        if (typed.isEmpty()) return false
        val expected = typed.toBigDecimalOrNull() ?: return false
        return displayedAmounts(haystack).any { token ->
            val shown = token.replace(",", "").toBigDecimalOrNull() ?: return@any false
            shown.compareTo(expected) == 0
        }
    }
}

/**
 * One price fill as a provable sequence: clear the field, type digit-by-digit,
 * then verify the displayed amount by numeric-equal readback. Anything short of
 * a reliable readback resolves [Outcome.WAITING_USER] — an unverified price is
 * never recorded as a full-field success.
 */
internal class KeypadEntry(expectedValue: String) {
    enum class Outcome(val wire: String) {
        VERIFIED("PRICE_VERIFIED"),
        WAITING_USER("WAITING_USER"),
    }

    val digits: String = PriceKeypad.keys(expectedValue)

    init {
        require(PriceKeypad.keypadable(expectedValue)) { "Value is not keypad-typeable: $expectedValue" }
    }

    /** Delete-key taps that empty a field currently showing [shownAmount] ("¥" ignored). */
    fun clearsNeeded(shownAmount: String?): Int =
        shownAmount?.filter { it.isDigit() || it == '.' }?.length ?: 0

    /**
     * Mid-flight accumulation guard: after [typedCount] digits the field must show
     * EXACTLY the typed prefix. A leftover ("9" still shown after typing "1" gives
     * "91") is inconsistent: stop typing, clear again, restart — never accumulate.
     */
    fun prefixConsistent(shownAmount: String?, typedCount: Int): Boolean {
        if (typedCount <= 0 || typedCount > digits.length) return false
        return shownAmount != null && shownAmount == digits.substring(0, typedCount)
    }

    /** Terminal outcome once the sheet settles; only the readback decides it. */
    fun outcome(formHaystack: String?): Outcome =
        if (formHaystack != null && PriceKeypad.acceptedOnForm(formHaystack, digits)) {
            Outcome.VERIFIED
        } else {
            Outcome.WAITING_USER
        }

    /** Convenience for callers journaling the terminal price status. */
    fun outcomeWire(formHaystack: String?): String = outcome(formHaystack).wire
}
