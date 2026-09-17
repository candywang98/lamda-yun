package com.company.cloudctl.companion.automation.recipes

import com.company.cloudctl.companion.automation.BuiltinRecipes
import com.company.cloudctl.companion.automation.CanonicalJson
import com.company.cloudctl.companion.automation.RecipeEngine
import org.json.JSONObject
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * B16 single-source dual-out golden test: the ONE spec file
 * (automation/recipes/contract/recipe-contract-spec.json) feeds both the
 * Python validator and these Kotlin goldens. Any drift between the JSON spec,
 * the Kotlin constants, or the pinned builtin bytes fails here.
 */
class RecipeContractGoldenTest {

    private fun specFile(): File {
        val relative = "src/main/java/com/company/cloudctl/companion/automation/recipes/contract/recipe-contract-spec.json"
        val candidates = mutableListOf(File(relative), File("app/$relative"))
        var dir: File? = File(System.getProperty("user.dir") ?: ".")
        repeat(6) {
            dir?.let { candidates += File(it, relative) }
            dir = dir?.parentFile
        }
        return candidates.firstOrNull { it.isFile }
            ?: error("recipe-contract-spec.json not found; run from the companion module (cwd=${System.getProperty("user.dir")})")
    }

    private fun spec(): JSONObject = JSONObject(specFile().readText(Charsets.UTF_8))

    @Test
    fun kotlinConstantsMirrorTheSingleSourceSpec() {
        val spec = spec()
        assertEquals("recipe-contract-spec", spec.getString("specId"))
        assertEquals(RecipeContract.SPEC_VERSION, spec.getString("specVersion"))
        assertEquals(RecipeContract.PROTOCOL, spec.getString("protocol"))
        assertEquals(RecipeContract.KIND, spec.getString("kind"))
        assertEquals(RecipeContract.TEMPLATE_PROTOCOL, spec.getString("templateProtocol"))

        val actions = spec.getJSONObject("actions")
        assertEquals(
            RecipeContract.ACTION_WHITELIST,
            actions.getJSONArray("whitelist").let { set -> (0 until set.length()).map { set.getString(it) }.toSet() },
        )
        val caps = actions.getJSONObject("parameterCaps")
        assertEquals(RecipeContract.MAX_WAIT_ATTEMPTS, caps.getInt("maxWaitAttempts"))
        assertEquals(RecipeContract.MAX_NO_PROGRESS_POLLS, caps.getInt("maxNoProgressPolls"))
        assertEquals(RecipeContract.MIN_STATE_DEADLINE_MS, caps.getLong("minStateDeadlineMs"))
        assertEquals(RecipeContract.MAX_INPUT_TEXT_LENGTH, caps.getInt("maxInputTextLength"))
        assertEquals(RecipeContract.MAX_VALUE_REF_LENGTH, caps.getInt("maxValueRefLength"))
        assertEquals(RecipeContract.MAX_MEDIA_ASSETS, caps.getInt("maxMediaAssets"))
        assertEquals(RecipeContract.MAX_STATES, caps.getInt("maxStates"))
        assertEquals(RecipeContract.MAX_STATE_ID_LENGTH, caps.getInt("maxStateIdLength"))

        val graph = spec.getJSONObject("graph")
        val iterations = graph.getJSONArray("maxIterations")
        assertEquals(RecipeContract.GRAPH_MAX_ITERATIONS_RANGE.first, iterations.getInt(0))
        assertEquals(RecipeContract.GRAPH_MAX_ITERATIONS_RANGE.last, iterations.getInt(1))
        val duration = graph.getJSONArray("maxDurationMs")
        assertEquals(RecipeContract.GRAPH_MAX_DURATION_MS_RANGE.first, duration.getLong(0))
        assertEquals(RecipeContract.GRAPH_MAX_DURATION_MS_RANGE.last, duration.getLong(1))

        val wait = spec.getJSONObject("wait")
        assertEquals(
            RecipeContract.ON_EXHAUSTED_VALUES,
            wait.getJSONArray("onExhaustedValues").let { set -> (0 until set.length()).map { set.getString(it) }.toSet() },
        )
        assertEquals(RecipeContract.WAIT_POLL_INTERVAL_MS, wait.getLong("pollIntervalMs"))
        assertEquals(
            RecipeContract.FORBIDDEN_FIELD_FRAGMENTS,
            spec.getJSONArray("forbiddenFieldFragments").let { set -> (0 until set.length()).map { set.getString(it) } },
        )
        val loop = spec.getJSONObject("loopPolicy")
        assertEquals(RecipeContract.BOUNDED_CYCLE_MAX_ITERATIONS, loop.getInt("boundedCycleMaxIterations"))
        assertEquals(
            RecipeContract.IRREVERSIBLE_LOCATORS,
            loop.getJSONArray("irreversibleLocators").let { set -> (0 until set.length()).map { set.getString(it) }.toSet() },
        )
        assertEquals(
            RecipeContract.TEMPLATE_ACTIONS,
            spec.getJSONArray("templateActions").let { set -> (0 until set.length()).map { set.getString(it) }.toSet() },
        )
        assertEquals(
            RecipeContract.TEMPLATE_FORBIDDEN_ACTIONS,
            spec.getJSONArray("templateForbiddenActions").let { set -> (0 until set.length()).map { set.getString(it) }.toSet() },
        )
    }

    /**
     * Frozen bytes: every published builtin package must still hash to its
     * pinned manifest hash AND to the spec's pinnedRecipes entry — an in-place
     * edit of a published recipe cannot pass.
     */
    @Test
    fun publishedRecipeBytesAreImmutableAndHashPinned() {
        val pinned = spec().getJSONObject("pinnedRecipes")
        val engine = RecipeEngine(NoopRecipeUi, elapsedMs = { 0L })
        pinned.keys().forEach { versionId ->
            val encoded = assertNotNull(BuiltinRecipes.packageJson(versionId), "builtin $versionId missing")
            val root = JSONObject(encoded)
            val declared = root.getJSONObject("manifest").getString("hash")
            val computed = RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(root))
            assertEquals(declared, computed, "builtin $versionId canonical hash drifted from its manifest")
            assertEquals(pinned.getString(versionId), computed, "builtin $versionId bytes drifted from the pinned spec hash")
            // The engine still parses the frozen bytes unchanged.
            engine.parse(encoded, expectedHash = declared)
        }
    }

    /** Every published builtin passes the B16 static contract. */
    @Test
    fun publishedBuiltinsPassStaticValidation() {
        val pinned = spec().getJSONObject("pinnedRecipes")
        pinned.keys().forEach { versionId ->
            val encoded = BuiltinRecipes.packageJson(versionId) ?: error("builtin $versionId missing")
            assertEquals(emptyList(), RecipeStaticValidator.validate(encoded), "builtin $versionId must stay statically valid")
        }
    }
}

internal object NoopRecipeUi : com.company.cloudctl.companion.automation.LocalAutomationUi {
    override fun ensureReady(targetPackage: String) = Unit
    override fun inspect(targetPackage: String, locatorRef: String): com.company.cloudctl.companion.automation.LocalNodeState? = null
    override suspend fun tap(targetPackage: String, locatorRef: String) = Unit
    override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = Unit
    override suspend fun screenshot(
        taskId: String,
        label: String,
    ): com.company.cloudctl.companion.automation.ScreenshotEvidence =
        com.company.cloudctl.companion.automation.ScreenshotEvidence("x", 1, "a")
    override fun log(level: com.company.cloudctl.companion.automation.LogLevel, messageCode: String) = Unit
}
