package com.company.cloudctl.companion.automation.recipes

/**
 * B16 single-source dual-out: these Kotlin constants mirror
 * `automation/recipes/contract/recipe-contract-spec.json` value-for-value.
 * RecipeContractGoldenTest reads that one JSON file and fails on any drift,
 * so the JSON spec stays the single source and this object can never rot.
 */
object RecipeContract {
    const val SPEC_VERSION = "2026-09-17.1"
    const val PROTOCOL = "cloudctl.recipe/v1"
    const val KIND = "LocalRecipePackage"
    const val TEMPLATE_PROTOCOL = "cloudctl.recipe-template/v1"

    val ACTION_WHITELIST: Set<String> = setOf(
        "tap", "input", "scroll", "extract", "wait", "launch", "media", "log", "checkpoint",
    )

    // Per-action / per-parameter caps.
    const val MAX_WAIT_ATTEMPTS = 80
    const val MAX_NO_PROGRESS_POLLS = 80
    const val MIN_STATE_DEADLINE_MS = 1000L
    const val MAX_INPUT_TEXT_LENGTH = 1024
    const val MAX_VALUE_REF_LENGTH = 64
    const val MAX_MEDIA_ASSETS = 49
    const val MAX_STATES = 64
    const val MAX_STATE_ID_LENGTH = 128

    val GRAPH_MAX_ITERATIONS_RANGE = 1..200
    val GRAPH_MAX_DURATION_MS_RANGE = 1000L..900_000L

    val ON_EXHAUSTED_VALUES: Set<String> = setOf("FAIL", "WAITING_USER")
    const val WAIT_POLL_INTERVAL_MS = 250L

    /** Key fragments that may never appear anywhere in a recipe/template (no eval, no shell, no JS). */
    val FORBIDDEN_FIELD_FRAGMENTS: List<String> = listOf(
        "eval", "shell", "javascript", "script", "bytecode", "dex", "frida",
        "argv", "payload", "exec", "runtime", "expression",
    )

    /** Loop policy: bounded cycles are legal, dead cycles and irreversible-in-cycle are not. */
    const val BOUNDED_CYCLE_MAX_ITERATIONS = 200
    val IRREVERSIBLE_LOCATORS: Set<String> = setOf(
        "xianyu_publish_button", "xhs_publish_button", "dy_publish_button", "xianyu_delete_confirm",
    )

    // Declarative template DSL (cloudctl.recipe-template/v1).
    val TEMPLATE_ACTIONS: Set<String> = setOf("navigate", "wait", "input", "media", "checkpoint")
    val TEMPLATE_FORBIDDEN_ACTIONS: Set<String> = setOf("submit", "shell", "eval", "js", "tapPublish")

    val VALUE_REF_PATTERN: Regex = Regex("^[A-Za-z0-9_]{1,${MAX_VALUE_REF_LENGTH}}$")
    val STATE_ID_PATTERN: Regex = Regex("^[A-Za-z0-9][A-Za-z0-9._:-]{0,${MAX_STATE_ID_LENGTH - 1}}$")
}
