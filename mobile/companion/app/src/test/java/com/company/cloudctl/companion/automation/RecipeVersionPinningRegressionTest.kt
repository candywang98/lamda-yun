package com.company.cloudctl.companion.automation

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * B16 acceptance, P14 non-regression: a running or paused task keeps reading
 * ITS pinned recipe version even after the active catalog has moved on; the
 * builtin v1 stub stays byte-identical for commands pinned to it; a hash
 * mismatch on the pinned version fails closed. Covers RecipeCatalog pinning
 * semantics without touching RecipeLifecycle's server sync.
 */
class RecipeVersionPinningRegressionTest {

    @AfterTest
    fun resetCatalog() {
        RecipeCatalog.clear()
    }

    private fun packageBytes(id: String, app: String, commandType: String): String {
        val root = JSONObject()
            .put("apiVersion", "cloudctl.recipe/v1")
            .put("kind", "LocalRecipePackage")
            .put(
                "manifest",
                JSONObject()
                    .put("id", id)
                    .put("version", "1.0.0")
                    .put("hash", "0".repeat(64))
                    .put("signingKeyId", "p14-test")
                    .put("minEngineVersion", 1)
                    .put("platform", "xianyu")
                    .put("app", app)
                    .put("commandTypes", JSONArray(listOf(commandType))),
            )
            .put(
                "graph",
                JSONObject()
                    .put("startStateId", "only")
                    .put("maxIterations", 8)
                    .put("maxDurationMs", 30_000)
                    .put(
                        "states",
                        JSONArray().put(
                            JSONObject().put("stateId", "only").put("action", "log")
                                .put("onSuccess", "SUCCEEDED").put("onFailure", JSONObject.NULL),
                        ),
                    ),
            )
            .put("signature", JSONObject().put("algorithm", "Ed25519").put("keyId", "p14-test").put("digest", "unsigned"))
        val hash = RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(root))
        root.getJSONObject("manifest").put("hash", hash)
        return root.toString()
    }

    private fun commandFor(versionId: String, sha256: String) = CommandV1(
        protocolVersion = CommandV1Parser.PROTOCOL,
        taskId = "task-pin",
        attemptId = "attempt-1",
        commandType = "xianyu.publish_listing.v1",
        deviceId = "device-1",
        accountId = "account-1",
        bindingVersion = 1,
        snapshotId = "snap",
        snapshotSha256 = "a".repeat(64),
        recipeVersionId = versionId,
        recipeSha256 = sha256,
        engineMinVersion = 1,
        targetPackage = "com.taobao.idlefish",
        requiredCapabilities = listOf("accessibility"),
        controlEpoch = 1,
        leaseExpiresAt = "2026-09-07T00:00:00Z",
        mediaDeliveryId = null,
        legacyStepsEnabled = false,
        parameters = JSONObject(),
    )

    private fun hashOf(encoded: String): String =
        JSONObject(encoded).getJSONObject("manifest").getString("hash")

    @Test
    fun runningTaskKeepsItsPinnedVersionAfterTheActiveCatalogMovesOn() {
        val pinnedBytes = packageBytes("recipe-pin-old", "com.taobao.idlefish", "xianyu.publish_listing.v1")
        val successorBytes = packageBytes("recipe-pin-new", "com.taobao.idlefish", "xianyu.publish_listing.v1")
        RecipeCatalog.putVerified("recipe-pin-old", pinnedBytes)
        RecipeCatalog.putVerified("recipe-pin-new", successorBytes)
        // The task was claimed while recipe-pin-old was active...
        RecipeCatalog.activate(mapOf("xianyu.publish_listing.v1" to "recipe-pin-old"))
        val claimedCommand = commandFor("recipe-pin-old", hashOf(pinnedBytes))
        // ...the operator then rolls the active catalog forward mid-run.
        RecipeCatalog.activate(mapOf("xianyu.publish_listing.v1" to "recipe-pin-new"))
        // The running/paused task still resolves ITS pinned version and bytes.
        assertEquals(pinnedBytes, RecipeCatalog.jsonFor(claimedCommand))
        assertEquals("recipe-pin-old", JSONObject(RecipeCatalog.jsonFor(claimedCommand)).getJSONObject("manifest").getString("id"))
        // New commands resolve the new active version instead.
        assertEquals(
            "recipe-pin-new",
            JSONObject(RecipeCatalog.jsonFor(commandFor("recipe-pin-new", hashOf(successorBytes))))
                .getJSONObject("manifest").getString("id"),
        )
    }

    @Test
    fun builtinV1StubStaysReadableForPinnedCommandsBesideV2() {
        val v1Bytes = BuiltinRecipes.packageJson("recipe-xianyu-publish-1") ?: error("v1 builtin missing")
        val v1Hash = hashOf(v1Bytes)
        RecipeCatalog.activate(mapOf("xianyu.publish_listing.v1" to "recipe-xianyu-publish-2"))
        val resolved = RecipeCatalog.jsonFor(commandFor("recipe-xianyu-publish-1", v1Hash))
        assertEquals(v1Bytes, resolved, "a command pinned to v1 must keep reading the frozen v1 bytes")
        // Hash pinning: the frozen literal never regenerates differently.
        assertEquals(
            "a2331b8076dd28cd34f574f359b7e549ebef1f0ebd060bff2fad0ab410a84c0f",
            RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(JSONObject(v1Bytes))),
        )
        // A different recipe must never collide with the pin.
        val other = packageBytes("recipe-pin-other", "com.taobao.idlefish", "xianyu.publish_listing.v1")
        assertNotEquals(v1Hash, hashOf(other))
    }

    @Test
    fun pinnedVersionWithTamperedHashFailsClosed() {
        val pinnedBytes = packageBytes("recipe-pin-guard", "com.taobao.idlefish", "xianyu.publish_listing.v1")
        RecipeCatalog.putVerified("recipe-pin-guard", pinnedBytes)
        RecipeCatalog.activate(mapOf("xianyu.publish_listing.v1" to "recipe-pin-guard"))
        val tampered = commandFor("recipe-pin-guard", "b".repeat(64))
        val failure = assertFailsWith<IllegalArgumentException> {
            RecipeCatalog.jsonFor(tampered)
        }
        assertEquals("recipe hash mismatch", failure.message)
    }

    @Test
    fun unknownRecipeVersionFailsClosed() {
        RecipeCatalog.activate(mapOf("xianyu.publish_listing.v1" to "recipe-xianyu-publish-2"))
        val unknown = commandFor("recipe-never-published", "c".repeat(64))
        val failure = assertFailsWith<IllegalStateException> {
            RecipeCatalog.jsonFor(unknown)
        }
        assertEquals(CommandV1Parser.UNSUPPORTED_RECIPE, failure.message)
    }

    @Test
    fun engineRejectsExecutionWhenPackageBytesDifferFromCommandPin() {
        // Even if the catalog somehow served other bytes, execute() re-checks
        // the pin before the first UI side effect (P14 rollback semantics).
        val ui = RecordingUi()
        val engine = RecipeEngine(ui, elapsedMs = { 0L })
        val bytes = packageBytes("recipe-pin-exec", "com.taobao.idlefish", "xianyu.publish_listing.v1")
        val recipe = engine.parse(bytes)
        val pinnedToOtherHash = commandFor("recipe-pin-exec", "d".repeat(64))
        assertFailsWith<IllegalArgumentException> {
            kotlinx.coroutines.runBlocking {
                engine.execute(recipe, pinnedToOtherHash) { _, _ -> }
            }
        }
        assertTrue(ui.taps.isEmpty() && ui.logs.isEmpty(), "no UI side effect may happen on a pin mismatch")
    }

    private class RecordingUi : LocalAutomationUi {
        val taps = mutableListOf<String>()
        val logs = mutableListOf<String>()
        override fun ensureReady(targetPackage: String) = Unit
        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? = LocalNodeState(true, true, true, true, "")
        override suspend fun tap(targetPackage: String, locatorRef: String) {
            taps += locatorRef
        }
        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = Unit
        override suspend fun screenshot(taskId: String, label: String) = ScreenshotEvidence("x", 1, "a")
        override fun log(level: LogLevel, messageCode: String) {
            logs += messageCode
        }
    }
}
