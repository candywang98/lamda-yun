package com.company.cloudctl.companion.automation.recipes

import com.company.cloudctl.companion.automation.CanonicalJson
import com.company.cloudctl.companion.automation.RecipeEngine
import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * B16 acceptance: static validation accepts bounded (finite repeat/retry)
 * loops and rejects non-terminating loops, irreversible submit actions inside
 * loop bodies, eval/shell-style fields and per-action cap violations. The same
 * cases are proven on the Python side by
 * `scripts/validate-recipe-contract.py --self-test` (exit 0).
 */
class RecipeStaticValidatorTest {

    private fun packageOf(states: JSONArray, maxIterations: Int = 40, maxDurationMs: Long = 600_000): String {
        val root = JSONObject()
            .put("apiVersion", RecipeContract.PROTOCOL)
            .put("kind", RecipeContract.KIND)
            .put(
                "manifest",
                JSONObject()
                    .put("id", "recipe-test")
                    .put("version", "1.0.0")
                    .put("hash", "0".repeat(64))
                    .put("signingKeyId", "test")
                    .put("minEngineVersion", 1)
                    .put("platform", "xianyu")
                    .put("app", "com.taobao.idlefish")
                    .put("commandTypes", JSONArray(listOf("xianyu.publish_listing.v1"))),
            )
            .put(
                "graph",
                JSONObject()
                    .put("startStateId", states.getJSONObject(0).getString("stateId"))
                    .put("maxIterations", maxIterations)
                    .put("maxDurationMs", maxDurationMs)
                    .put("states", states),
            )
            .put("signature", JSONObject().put("algorithm", "Ed25519").put("keyId", "test").put("digest", "unsigned"))
        val hash = RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(root))
        root.getJSONObject("manifest").put("hash", hash)
        return root.toString()
    }

    private fun state(stateId: String, action: String, onSuccess: String, onFailure: String?, locatorRef: String? = null) =
        JSONObject()
            .put("stateId", stateId)
            .put("action", action)
            .apply { locatorRef?.let { put("locatorRef", it) } }
            .put("onSuccess", onSuccess)
            .apply { if (onFailure != null) put("onFailure", onFailure) }

    @Test
    fun boundedRetryCycleWithTerminalExitIsAllowed() {
        // open -> await -> (onFailure) open is a FINITE retry: await has a
        // bounded budget and a terminal success exit.
        val states = JSONArray()
            .put(state("open", "tap", "await", "FAILED", "xianyu_home_sell"))
            .put(
                state("await", "wait", "SUCCEEDED", "open", "xianyu_publish_page")
                    .put("maxAttempts", 3)
                    .put("noProgressBudget", 2)
                    .put("deadlineMs", 20_000)
                    .put("onExhausted", "FAIL"),
            )
        val violations = RecipeStaticValidator.validate(packageOf(states))
        assertEquals(emptyList(), violations, "a bounded retry cycle with a terminal exit must validate")
        // The engine accepts the same bytes (parse-level integration).
        RecipeEngine(NoopRecipeUi, elapsedMs = { 0L }).parse(packageOf(states))
    }

    @Test
    fun nonTerminatingLoopIsRejected() {
        val states = JSONArray()
            .put(state("a", "wait", "b", "b", "xianyu_home_sell"))
            .put(state("b", "wait", "a", "a", "xianyu_home_sell"))
        val violations = RecipeStaticValidator.validate(packageOf(states))
        assertTrue(
            violations.any { it.code == "LOOP_NON_TERMINATING" },
            "a cycle whose states can never reach a terminal must be rejected: $violations",
        )
    }

    @Test
    fun irreversibleSubmitInsideLoopBodyIsRejected() {
        val states = JSONArray()
            .put(state("loop", "tap", "loop2", "FAILED", "xianyu_publish_button"))
            .put(state("loop2", "wait", "loop", "FAILED", "xianyu_home_sell"))
        val violations = RecipeStaticValidator.validate(packageOf(states))
        assertTrue(
            violations.any { it.code == "IRREVERSIBLE_IN_LOOP" },
            "a publish-button tap inside a retry loop must be rejected: $violations",
        )
    }

    @Test
    fun commitStateInsideLoopIsRejectedAndCommitMustNotCarryRetryBudgets() {
        val states = JSONArray()
            .put(state("before", "wait", "commit", "FAILED", "xianyu_home_sell"))
            .put(
                state("commit", "tap", "before", null, "xianyu_add_image")
                    .put("postcondition", "xianyu_home_sell"),
            )
        val withCommit = JSONObject(packageOf(states))
        withCommit.getJSONObject("graph").put("commitActionId", "commit")
        // re-hash after the graph edit
        val hash = RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(withCommit))
        withCommit.getJSONObject("manifest").put("hash", hash)
        val violations = RecipeStaticValidator.validate(withCommit.toString())
        assertTrue(
            violations.any { it.code == "IRREVERSIBLE_IN_LOOP" && it.detail.contains("commit") },
            "a commit state on a cycle must be rejected: $violations",
        )

        val budgeted = JSONArray()
            .put(
                state("commit", "tap", "SUCCEEDED", null, "xianyu_add_image")
                    .put("postcondition", "xianyu_home_sell")
                    .put("maxAttempts", 3),
            )
        val budgetedRoot = JSONObject(packageOf(budgeted))
        budgetedRoot.getJSONObject("graph").put("commitActionId", "commit")
        val budgetHash = RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(budgetedRoot))
        budgetedRoot.getJSONObject("manifest").put("hash", budgetHash)
        assertTrue(
            RecipeStaticValidator.validate(budgetedRoot.toString()).any { it.code == "COMMIT_NOT_RETRYABLE" },
            "retry budgets on the irreversible commit must be rejected",
        )
    }

    @Test
    fun evalShellAndJsFieldsAreRejectedEvenOnHashConsistentPackages() {
        val states = JSONArray()
            .put(
                state("await", "wait", "SUCCEEDED", "FAILED", "xianyu_publish_page")
                    .put("eval", "1+1"),
            )
        val violations = RecipeStaticValidator.validate(packageOf(states))
        assertTrue(
            violations.any { it.code == "FORBIDDEN_FIELD" },
            "eval fields must be rejected — signature is provenance, not a sandbox: $violations",
        )
    }

    @Test
    fun perActionParameterCapsAreEnforced() {
        val overAttempts = JSONArray()
            .put(
                state("await", "wait", "SUCCEEDED", "FAILED", "xianyu_publish_page")
                    .put("maxAttempts", RecipeContract.MAX_WAIT_ATTEMPTS + 1),
            )
        assertTrue(
            RecipeStaticValidator.validate(packageOf(overAttempts)).any { it.code == "MAX_ATTEMPTS_OUT_OF_RANGE" },
        )
        val overText = JSONArray()
            .put(
                state("fill", "input", "SUCCEEDED", "FAILED", "xianyu_description")
                    .put("valueRef", "x".repeat(RecipeContract.MAX_VALUE_REF_LENGTH + 1)),
            )
        assertTrue(
            RecipeStaticValidator.validate(packageOf(overText)).any { it.code == "VALUE_REF_INVALID" },
        )
        val boundsOnNonRetryable = JSONArray()
            .put(
                state("extract", "extract", "SUCCEEDED", "FAILED")
                    .put("maxAttempts", 2),
            )
        assertTrue(
            RecipeStaticValidator.validate(packageOf(boundsOnNonRetryable)).any { it.code == "BOUNDS_ON_NON_RETRYABLE" },
        )
    }

    @Test
    fun inPlaceEditOfPublishedBytesFailsTheHashCheck() {
        val states = JSONArray()
            .put(state("await", "wait", "SUCCEEDED", "FAILED", "xianyu_publish_page"))
        val encoded = packageOf(states)
        val tampered = JSONObject(encoded)
        tampered.getJSONObject("graph").put("maxDurationMs", 600_001)
        assertTrue(
            RecipeStaticValidator.validate(tampered.toString()).any { it.code == "HASH_MISMATCH" },
            "editing published bytes in place must break the pinned hash",
        )
        assertFailsWith<IllegalArgumentException> {
            RecipeEngine(NoopRecipeUi, elapsedMs = { 0L }).parse(
                tampered.toString(),
                expectedHash = JSONObject(encoded).getJSONObject("manifest").getString("hash"),
            )
        }
    }

    @Test
    fun unknownActionsAndUnknownEdgeTargetsAreRejected() {
        val unknownAction = JSONArray().put(state("shell", "shell", "SUCCEEDED", "FAILED"))
        assertTrue(
            RecipeStaticValidator.validate(packageOf(unknownAction)).any { it.code == "ACTION_NOT_WHITELISTED" },
        )
        val dangling = JSONArray().put(state("await", "wait", "nowhere", "FAILED", "xianyu_publish_page"))
        assertTrue(
            RecipeStaticValidator.validate(packageOf(dangling)).any { it.code == "EDGE_TARGET_UNKNOWN" },
        )
    }
}
