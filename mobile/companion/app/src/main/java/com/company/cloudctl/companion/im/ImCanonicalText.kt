package com.company.cloudctl.companion.im

/**
 * Single canonical body used by local dedupe, the persistent outbox, and the
 * upload JSON (pa-im-m3/20260922.1 §4.1). Length is Unicode code points, not
 * UTF-16 code units. The function is idempotent: canonical(canonical(x)) = canonical(x).
 *
 * A short body that already equals some longer body's canonical form shares
 * that key. The contract accepts that collision and does not add a sequence.
 */
object ImCanonicalText {
    const val TRANSPORT_LIMIT = 4_000
    const val BODY_LIMIT = 2_000
    const val TRUNCATED_PREFIX = "TRUNCATED "

    fun canonical(raw: String): String {
        val body = takeCodePoints(raw, TRANSPORT_LIMIT)
        if (codePointCount(body) <= BODY_LIMIT) return body
        // Already "TRUNCATED " plus exactly 2000 code points. A second pass
        // would clip the prefix itself and then add it again, so stop here.
        // A long body that merely begins with the prefix is not this form:
        // its first 2000 code points still need the prefix added once.
        if (body.startsWith(TRUNCATED_PREFIX)) {
            val rest = body.removePrefix(TRUNCATED_PREFIX)
            if (codePointCount(rest) == BODY_LIMIT && codePointCount(body) == TRUNCATED_PREFIX.length + BODY_LIMIT) {
                return body
            }
        }
        return TRUNCATED_PREFIX + takeCodePoints(body, BODY_LIMIT)
    }

    fun codePointCount(value: String): Int = value.codePointCount(0, value.length)

    fun takeCodePoints(value: String, limit: Int): String {
        if (limit <= 0 || value.isEmpty()) return ""
        var count = 0
        var index = 0
        while (index < value.length && count < limit) {
            index += Character.charCount(value.codePointAt(index))
            count += 1
        }
        return value.substring(0, index)
    }
}
