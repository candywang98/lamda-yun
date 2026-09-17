package com.company.cloudctl.companion.automation.recipes

import com.company.cloudctl.companion.automation.CommandV1
import com.company.cloudctl.companion.automation.CommandV1Parser
import com.company.cloudctl.companion.automation.RecipeEngine
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * B16 dev experience: parse the declarative template, compile it to a
 * LocalRecipePackage, validate it statically, and replay it OFFLINE against a
 * fixture — no device, no adb. Also proves the compiled graph is cycle-free
 * (each step runs at most once) and that templates cannot express a submit.
 */
class FixtureReplayTemplateTest {

    private fun resource(relative: String): File {
        val path = "src/main/java/com/company/cloudctl/companion/automation/recipes/$relative"
        val candidates = mutableListOf(File(path), File("app/$path"))
        var dir: File? = File(System.getProperty("user.dir") ?: ".")
        repeat(6) {
            dir?.let { candidates += File(it, path) }
            dir = dir?.parentFile
        }
        return candidates.firstOrNull { it.isFile }
            ?: error("$relative not found (cwd=${System.getProperty("user.dir")})")
    }

    private fun command(hash: String, body: String = "自用闲置好书") = CommandV1(
        protocolVersion = CommandV1Parser.PROTOCOL,
        taskId = "task-fixture",
        attemptId = "attempt-1",
        commandType = "xianyu.publish_listing.v1",
        deviceId = "device-1",
        accountId = "account-1",
        bindingVersion = 1,
        snapshotId = "snap",
        snapshotSha256 = "a".repeat(64),
        recipeVersionId = "recipe-xianyu-publish-dev-3",
        recipeSha256 = hash,
        engineMinVersion = 1,
        targetPackage = "com.taobao.idlefish",
        requiredCapabilities = listOf("accessibility"),
        controlEpoch = 1,
        leaseExpiresAt = "2026-09-07T00:00:00Z",
        mediaDeliveryId = null,
        legacyStepsEnabled = false,
        parameters = JSONObject().put("listingBody", body),
    )

    @Test
    fun templateCompilesToAStaticallyValidCycleFreePackage() {
        val template = RecipeTemplate.parse(resource("templates/xianyu-publish-open-only.template.json").readText())
        val compiled = RecipeTemplateCompiler.compile(template)
        assertEquals(emptyList(), RecipeStaticValidator.validate(compiled.encoded))
        // Hash fixity: the embedded manifest hash matches a fresh canonical recompute.
        val root = JSONObject(compiled.encoded)
        assertEquals(
            compiled.hash,
            com.company.cloudctl.companion.automation.RecipeEngine.sha256Bytes(
                com.company.cloudctl.companion.automation.CanonicalJson.recipeHashPayload(root),
            ),
        )
        // The compiled graph is acyclic: every state's next hop is unique and forward.
        val states = root.getJSONObject("graph").getJSONArray("states")
        val ids = (0 until states.length()).map { states.getJSONObject(it).getString("stateId") }
        assertEquals(ids.toSet().size, ids.size)
        (0 until states.length()).forEach { index ->
            val state = states.getJSONObject(index)
            val onSuccess = state.getString("onSuccess")
            assertTrue(
                onSuccess == "SUCCEEDED" || onSuccess == "WAITING_USER" || ids.indexOf(onSuccess) > index,
                "compiled graphs must be forward-only (no retry cycles): $onSuccess at #$index",
            )
        }
        // Open-only red line: no submit/publish locator anywhere in the template output.
        assertTrue(
            (0 until states.length()).none {
                RecipeContract.IRREVERSIBLE_LOCATORS.contains(states.getJSONObject(it).optString("locatorRef"))
            },
        )
    }

    @Test
    fun offlineFixtureReplayRunsTheCompiledPackageEndToEnd() = runBlocking {
        val template = RecipeTemplate.parse(resource("templates/xianyu-publish-open-only.template.json").readText())
        val compiled = RecipeTemplateCompiler.compile(template)

        val replay = FixtureReplay.parse(resource("fixtures/xianyu-publish-open-only.replay.json").readText())
        val engine = RecipeEngine(replay, elapsedMs = { 0L })
        val recipe = engine.parse(compiled.encoded, expectedHash = compiled.hash)
        val journal = mutableListOf<String>()
        val outcome = engine.execute(recipe, command(recipe.hash)) { id, state -> journal += "$id:$state" }

        assertEquals("WAITING_USER", outcome, "an open-only template ends at the operator checkpoint")
        assertEquals(
            listOf(
                "wait-home:STARTED", "wait-home:SUCCEEDED",
                "open-sell:STARTED", "open-sell:SUCCEEDED",
                "wait-menu:STARTED", "wait-menu:SUCCEEDED",
                "open-publish:STARTED", "open-publish:SUCCEEDED",
                "await-form:STARTED", "await-form:SUCCEEDED",
                "fill-description:STARTED", "fill-description:SUCCEEDED",
                "await-confirm:STARTED", "await-confirm:SUCCEEDED",
            ),
            journal,
        )
        assertEquals(listOf("xianyu_home_sell", "xianyu_publish_entry"), replay.taps)
        assertEquals(listOf("xianyu_description" to "自用闲置好书"), replay.texts)
    }

    @Test
    fun offlineFixtureReplayFailsClosedWhenTheFormNeverAppears() = runBlocking {
        val template = RecipeTemplate.parse(resource("templates/xianyu-publish-open-only.template.json").readText())
        val compiled = RecipeTemplateCompiler.compile(template)

        // Only the home frame ever exists: open-sell's bounded postcondition wait
        // (maxAttempts 3) exhausts and the run fails closed without any input.
        val replay = FixtureReplay.of(
            "com.taobao.idlefish",
            FixtureReplay.Frame("home", mapOf("xianyu_home_sell" to node())),
        )
        val engine = RecipeEngine(replay, elapsedMs = { 0L })
        val recipe = engine.parse(compiled.encoded, expectedHash = compiled.hash)
        val journal = mutableListOf<String>()
        val outcome = engine.execute(recipe, command(recipe.hash)) { id, state -> journal += "$id:$state" }
        assertEquals("FAILED", outcome)
        assertEquals("open-sell:FAILED", journal.last())
        assertTrue(replay.texts.isEmpty(), "no description may be typed after navigation exhausted its budget")
    }

    @Test
    fun templatesCannotExpressSubmitOrEval() {
        val base = resource("templates/xianyu-publish-open-only.template.json").readText()
        val submit = JSONObject(base).getJSONArray("steps").put(
            JSONObject().put("stepId", "publish").put("action", "submit"),
        )
        val submitRoot = JSONObject(base).put("steps", submit)
        val failure = assertFailsWith<IllegalArgumentException> {
            RecipeTemplate.parse(submitRoot.toString())
        }
        assertTrue("submit" in failure.message.orEmpty(), failure.message)

        val evil = JSONObject(base).put("evalHook", "run")
        assertTrue(
            assertFailsWith<IllegalArgumentException> { RecipeTemplate.parse(evil.toString()) }
                .message.orEmpty().isNotBlank(),
        )
    }

    private fun node() = com.company.cloudctl.companion.automation.LocalNodeState(
        enabled = true, visible = true, clickable = true, editable = true, text = null,
    )
}
