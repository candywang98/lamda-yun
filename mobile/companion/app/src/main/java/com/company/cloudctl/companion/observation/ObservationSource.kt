package com.company.cloudctl.companion.observation

/**
 * ui-observation/v1@20260916.1 §1 — frozen snapshot source labels.
 *
 * `source ∈ {a11y_tree, a11y_event, uiautomator_dump, screenshot}`. Every
 * Observation/fixture MUST carry one; trees from different sources MUST NOT
 * be merged into one fixture or be used to cross-prove equality. Screenshot
 * is auxiliary evidence only and can never prove a UI-structure assertion on
 * its own (§7). Equality assertions (treeDigest) hold only within the same
 * source.
 */
enum class ObservationSource(val wire: String) {
    A11Y_TREE("a11y_tree"),
    A11Y_EVENT("a11y_event"),
    UIAUTOMATOR_DUMP("uiautomator_dump"),
    SCREENSHOT("screenshot");

    companion object {
        fun fromWire(value: String): ObservationSource =
            entries.firstOrNull { it.wire == value }
                ?: throw IllegalArgumentException(
                    "unknown ui-observation/v1 source label: $value (frozen set: " +
                        entries.joinToString("/") { it.wire } + ")",
                )
    }
}
