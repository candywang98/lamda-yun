package com.company.cloudctl.companion.automation

import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** B05: recipe-xianyu-publish-2 open-only graph, valueRef binding, ordered media. */
private class RecordingUi : LocalAutomationUi {
    val taps = mutableListOf<String>()
    val texts = mutableListOf<Pair<String, String>>()
    override fun ensureReady(targetPackage: String) = Unit
    override fun inspect(targetPackage: String, locatorRef: String) = LocalNodeState(true, true, true, true, "")
    override suspend fun tap(targetPackage: String, locatorRef: String) {
        taps += locatorRef
    }
    override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) {
        texts += locatorRef to value
    }
    override suspend fun screenshot(taskId: String, label: String) = ScreenshotEvidence("x", 1, "a")
    override fun log(level: LogLevel, messageCode: String) = Unit
}

class PublishRecipeV2Test {
    private val elapsed = { 0L }
    private val v2Hash = "f6adebdca3575cce16b64b62b6e27730de77868d64cceff3e83bee2223f62372"

    private fun command(parameters: JSONObject) = CommandV1(
        protocolVersion = CommandV1Parser.PROTOCOL,
        taskId = "task-1",
        attemptId = "attempt-1",
        commandType = "xianyu.publish_listing.v1",
        deviceId = "device-1",
        accountId = "account-1",
        bindingVersion = 1,
        snapshotId = "snap",
        snapshotSha256 = "a".repeat(64),
        recipeVersionId = "recipe-xianyu-publish-2",
        recipeSha256 = v2Hash,
        engineMinVersion = 1,
        targetPackage = "com.taobao.idlefish",
        requiredCapabilities = listOf("accessibility"),
        controlEpoch = 1,
        leaseExpiresAt = "2026-09-07T00:00:00Z",
        mediaDeliveryId = null,
        legacyStepsEnabled = false,
        parameters = parameters,
    )

    private fun publishParameters(mediaCount: Int, listingBody: String = "自用闲置好书", price: String = "12.80") =
        JSONObject()
            .put("listingBody", listingBody)
            .put("price", price)
            .put("mediaAssetIds", JSONArray(List(mediaCount) { "asset-$it" }))

    @Test
    fun v2LiteralIsHashPinnedOpenOnlyAndParameterBound() {
        val encoded = BuiltinRecipes.packageJson("recipe-xianyu-publish-2")
            ?: error("v2 literal missing from BuiltinRecipes")
        val engine = RecipeEngine(RecordingUi(), elapsedMs = elapsed)
        val parsed = engine.parse(encoded, expectedHash = v2Hash)
        assertNull(parsed.commitActionId)
        val states = parsed.states
        assertEquals("listingBody", states.getValue("fill-description").valueRef)
        // v1.1.0 (device-verified 2026-09-16): gallery_next opens the image edit
        // page; its 完成 exit is part of the graph, and price states are gone
        // (operator enters price at the WAITING_USER checkpoint).
        assertEquals("xianyu_crop_done", states.getValue("confirm-crop").locatorRef)
        assertEquals("xianyu_publish_page", states.getValue("await-form-back").locatorRef)
        assertTrue(states.keys.none { it.startsWith("await-price") || it.startsWith("fill-price") })
        assertEquals("WAITING_USER", states.getValue("await-confirm").onSuccess)
        assertTrue(states.getValue("await-confirm").terminal)
        // Open-only red line: no state references the publish button and no submit
        // action exists anywhere in the graph.
        assertTrue(states.values.none { it.locatorRef == "xianyu_publish_button" })
        assertTrue(states.values.all { it.action != "submit" })
        // Ordered media: the graph taps the add-image entry and the engine expands tiles.
        assertEquals("xianyu_add_image", states.getValue("select-media").locatorRef)
        // The v1 stub stays byte-identical alongside v2.
        val v1 = BuiltinRecipes.packageJson("recipe-xianyu-publish-1") ?: error("v1 literal missing")
        assertEquals(
            "a2331b8076dd28cd34f574f359b7e549ebef1f0ebd060bff2fad0ab410a84c0f",
            JSONObject(v1).getJSONObject("manifest").getString("hash"),
        )
    }

    @Test
    fun jsonForResolvesV2ForNewCommandsAndKeepsV1ForPinnedOnes() {
        val v2Command = command(publishParameters(2))
        val encoded = BuiltinRecipes.jsonFor(v2Command)
        assertEquals("recipe-xianyu-publish-2", JSONObject(encoded).getJSONObject("manifest").getString("id"))
        val v1Command = v2Command.copy(
            recipeVersionId = "recipe-xianyu-publish-1",
            recipeSha256 = "a2331b8076dd28cd34f574f359b7e549ebef1f0ebd060bff2fad0ab410a84c0f",
        )
        assertEquals(
            "recipe-xianyu-publish-1",
            JSONObject(BuiltinRecipes.jsonFor(v1Command)).getJSONObject("manifest").getString("id"),
        )
    }

    @Test
    fun inputStatesBindValuesFromCommandParameters() = runBlocking {
        val ui = RecordingUi()
        val engine = RecipeEngine(ui, elapsedMs = elapsed)
        val parsed = engine.parse(
            BuiltinRecipes.packageJson("recipe-xianyu-publish-2")!!,
            expectedHash = v2Hash,
        )
        engine.execute(parsed, command(publishParameters(2)), journal = { _, _ -> })
        assertEquals(listOf("xianyu_description" to "自用闲置好书"), ui.texts)
        // The edit-page exit runs between media and the description fill.
        assertTrue("xianyu_crop_done" in ui.taps)
    }

    @Test
    fun mediaExpandsToOrderedCoverTilesThenNext() = runBlocking {
        val ui = RecordingUi()
        val engine = RecipeEngine(ui, elapsedMs = elapsed)
        val parsed = engine.parse(
            BuiltinRecipes.packageJson("recipe-xianyu-publish-2")!!,
            expectedHash = v2Hash,
        )
        engine.execute(parsed, command(publishParameters(3)), journal = { _, _ -> })
        val mediaSlice = ui.taps.dropWhile { it != "xianyu_add_image" }.take(5)
        assertEquals(
            listOf(
                "xianyu_add_image",
                "xianyu_gallery_select_1",
                "xianyu_gallery_select_2",
                "xianyu_gallery_select_3",
                "xianyu_gallery_next",
            ),
            mediaSlice.filter { it != "xianyu_gallery_select_0" },
        )
        // The shutter tile 0 is only used as the gallery-open wait postcondition,
        // never tapped.
        assertTrue("xianyu_gallery_select_0" !in ui.taps)
    }

    @Test
    fun mediaFailsClosedOnEmptyOrOversizedLists() = runBlocking {
        val engine = RecipeEngine(RecordingUi(), elapsedMs = elapsed)
        val parsed = engine.parse(
            BuiltinRecipes.packageJson("recipe-xianyu-publish-2")!!,
            expectedHash = v2Hash,
        )
        for (count in listOf(0, 50)) {
            // The graph carries onFailure=FAILED, so the engine terminates through
            // graph semantics instead of rethrowing.
            val outcome = engine.execute(parsed, command(publishParameters(count)), journal = { _, _ -> })
            assertEquals("FAILED", outcome)
        }
    }

    @Test
    fun inputFailsClosedOnMissingOrBlankParameters() = runBlocking {
        val engine = RecipeEngine(RecordingUi(), elapsedMs = elapsed)
        val encoded = BuiltinRecipes.packageJson("recipe-xianyu-publish-2")!!
        val parsed = engine.parse(encoded, expectedHash = v2Hash)
        // listingBody blank -> fail closed at the description fill: the graph
        // routes through onFailure=FAILED and nothing is ever typed.
        val outcome = engine.execute(
            parsed,
            command(publishParameters(1, listingBody = "  ")),
            journal = { _, _ -> },
        )
        assertEquals("FAILED", outcome)
    }
}
