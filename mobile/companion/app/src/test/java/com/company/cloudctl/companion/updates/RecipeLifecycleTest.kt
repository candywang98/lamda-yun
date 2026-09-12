package com.company.cloudctl.companion.updates

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.automation.*
import com.company.cloudctl.companion.data.AutomationStore
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import java.io.File
import java.io.IOException
import java.nio.file.Files
import kotlin.test.*

@RunWith(RobolectricTestRunner::class)
@org.robolectric.annotation.Config(sdk = [35])
class RecipeLifecycleTest {
    private lateinit var context: Context
    private lateinit var store: AutomationStore
    private lateinit var directory: File
    private lateinit var manager: RecipePackageManager
    private lateinit var lifecycle: RecipeLifecycle
    private val oldBody = RecipeCatalogTest.SIGNED_PROBE
    private val newBody = javaClass.getResource("/recipes/published-probe.json")!!.readText()
    private val old = reference("version-old", oldBody)
    private val newer = reference("version-new", newBody)
    private val type = "device.probe_capabilities.v1"
    private val keys = mapOf(
        "test-automation-1" to "A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg=",
        "phase1-recipe-1" to "LZxWUG0N3Ke3PiBS2nGPZm0PMVa2lIJfJQynfu/oR4M=",
    )

    @Before fun setup() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase(AutomationStore.DATABASE_NAME)
        store = AutomationStore(context)
        directory = Files.createTempDirectory("recipe-lifecycle").toFile()
        recreate()
        RecipeCatalog.clear()
    }

    @After fun cleanup() {
        store.close()
        context.deleteDatabase(AutomationStore.DATABASE_NAME)
        directory.deleteRecursively()
        RecipeCatalog.clear()
    }

    private fun recreate() {
        manager = RecipePackageManager(directory, keys)
        lifecycle = RecipeLifecycle(manager, store)
    }

    private fun restart() {
        store.close()
        RecipeCatalog.clear()
        store = AutomationStore(context)
        recreate()
        lifecycle.restore()
    }

    private fun reference(id: String, body: String) = RecipeReference(id, JSONObject(body).getJSONObject("manifest").getString("hash"), 1)
    private fun listing(vararg refs: RecipeReference): String = JSONObject().put("protocolVersion", "cloudctl.recipe/v1")
        .put("items", JSONArray(refs.map { ref -> JSONObject()
            .put("versionId", ref.versionId).put("sha256", ref.sha256).put("engineMinVersion", ref.engineMinVersion)
            .put("commandType", type).put("downloadPath", "/companion/v2/recipes/${ref.versionId}") })).toString()
    private fun download(id: String): RecipeDownload = when (id) {
        old.versionId -> RecipeDownload(oldBody, old.sha256)
        newer.versionId -> RecipeDownload(newBody, newer.sha256)
        else -> error("Unexpected exact-version download: $id")
    }
    private fun sync(ref: RecipeReference) = lifecycle.synchronize(listing(ref), ::download)
    private fun command(ref: RecipeReference = old) = CommandV1(
        CommandV1Parser.PROTOCOL, "task-1", "attempt-1", type, "device-1", "account-1", 1,
        "snapshot-1", "a".repeat(64), ref.versionId, ref.sha256, ref.engineMinVersion,
        "com.company.cloudctl.companion", emptyList(), 1, "2099-01-01T00:00:00Z", null, false, JSONObject(),
    )
    private fun queue() { store.enqueueTask("task-1", taskPayload(old), "lease-1", 0) }
    private fun taskPayload(ref: RecipeReference): String = JSONObject().put("taskId", "task-1")
        .put("recipe", JSONObject().put("versionId", ref.versionId).put("sha256", ref.sha256).put("engineMinVersion", 1)).toString()
    private fun idle() {
        store.finish("task-1", true)
        store.pendingEvents().forEach { store.markDelivered(it.id) }
        lifecycle.activatePending()
    }
    private fun assertOld() {
        assertEquals(old.versionId, RecipeCatalog.activeVersion(type))
        assertEquals(oldBody, manager.load(old))
    }

    @Test fun idleActivationAndRestartRestoresVerifiedCatalog() {
        sync(old)
        restart()
        assertOld()
        assertNull(store.pendingRecipeCatalog())
    }

    @Test fun runningUpdatePersistsPendingAndActivatesOnlyAfterTerminalAcknowledgment() {
        sync(old); queue(); assertNotNull(store.claimNext())
        sync(newer)
        assertOld()
        assertNotNull(store.pendingRecipeCatalog())
        restart()
        assertOld()
        store.finish("task-1", true)
        lifecycle.activatePending()
        assertOld()
        store.pendingEvents().forEach { store.markDelivered(it.id) }
        lifecycle.activatePending()
        assertEquals(newer.versionId, RecipeCatalog.activeVersion(type))
    }

    @Test fun pausedAndResumeCheckKeepOldVersionAcrossRestart() {
        sync(old); queue(); store.claimNext()
        store.markPaused("task-1", "step-1", 0, "operator")
        sync(newer); restart(); assertOld()
        store.markResumeCheck("task-1", "lease-2")
        lifecycle.activatePending(); assertOld()
        assertTrue(store.claimResume()!!.payload.contains(old.versionId))
        idle()
        assertEquals(newer.versionId, RecipeCatalog.activeVersion(type))
    }

    @Test fun queuedClaimAndUnreconciledActionBlockActivation() {
        sync(old); queue(); sync(newer); assertOld()
        store.claimNext()
        store.recordActionIntent("action-1", "task-1", "params")
        idle(); assertOld()
        store.markActionApplied("action-1")
        lifecycle.activatePending()
        // Confirming the journal alone does not reconcile the task after an uncertain finish.
        assertOld()
        assertTrue(store.hasBlockingHead())
    }

    @Test fun unknownIrreversibleOutcomeKeepsActivationBlockedAcrossRestart() {
        sync(old); queue(); store.claimNext()
        store.recordActionIntent("action-1", "task-1", "params")
        store.markActionUnknown("action-1")
        sync(newer)
        idle(); restart(); assertOld()
        assertNotNull(store.pendingRecipeCatalog())
    }

    @Test fun rollbackUsesRetainedOldPackageWithoutRedownload() {
        sync(old); sync(newer)
        lifecycle.synchronize(listing(old)) { error("retained package should be reused") }
        assertOld()
        assertEquals(newBody, manager.load(newer))
    }

    @Test fun missingHistoricalClaimDownloadsExactVersionWithoutChangingActiveMapping() {
        sync(newer)
        val requested = mutableListOf<String>()
        val json = lifecycle.ensureCommand(command()) { id -> requested += id; download(id) }
        assertEquals(listOf(old.versionId), requested)
        assertEquals(oldBody, json)
        assertEquals(newer.versionId, RecipeCatalog.activeVersion(type))
        restart()
        assertEquals(oldBody, lifecycle.ensureCommand(command()) { error("historical version retained") })
    }

    @Test fun historicalDownloadFailureCannotFallBackToActiveOrBuiltin() {
        sync(newer)
        assertFailsWith<IOException> { lifecycle.ensureCommand(command()) { throw IOException("unavailable") } }
        assertFailsWith<IllegalStateException> { RecipeCatalog.jsonFor(command()) }
        assertEquals(newer.versionId, RecipeCatalog.activeVersion(type))
    }

    @Test fun wrongBuiltinHashFailsClosedWithoutDownloading() {
        assertFailsWith<IllegalArgumentException> {
            lifecycle.ensureCommand(command(old.copy(versionId = "recipe-device-probe-1"))) { error("no download") }
        }
    }

    @Test fun interruptedDownloadPreservesActiveAndPendingSnapshot() {
        sync(old); queue(); sync(newer)
        val pending = store.pendingRecipeCatalog()
        val missing = old.copy(versionId = "version-third")
        assertFailsWith<IOException> { lifecycle.synchronize(listing(missing)) { throw IOException("interrupted") } }
        assertOld()
        assertEquals(pending, store.pendingRecipeCatalog())
    }

    @Test fun wrongHeaderHashCanonicalHashAndSignaturePreserveOldPackage() {
        sync(old)
        assertFailsWith<IllegalArgumentException> {
            lifecycle.synchronize(listing(newer)) { RecipeDownload(newBody, old.sha256) }
        }
        assertFailsWith<IllegalArgumentException> {
            lifecycle.synchronize(listing(newer)) { RecipeDownload(oldBody, newer.sha256) }
        }
        val tampered = JSONObject(newBody).also { it.getJSONObject("signature").put("digest", "AAAA") }.toString()
        assertFailsWith<IllegalArgumentException> {
            lifecycle.synchronize(listing(newer)) { RecipeDownload(tampered, newer.sha256) }
        }
        assertOld()
        assertFalse(File(directory, "versions/${newer.versionId}/package.json").exists())
    }

    @Test fun immutableVersionRejectsDifferentValidSignedPackage() {
        sync(old)
        assertFailsWith<IllegalArgumentException> { manager.install(newer.copy(versionId = old.versionId), newBody) }
        assertOld()
    }

    @Test fun stagingFailureAndOrphanTempPreserveOtherVersions() {
        sync(old)
        File(directory, "versions/${newer.versionId}").writeText("blocks staging directory")
        assertFailsWith<IOException> { manager.install(newer, newBody) }
        File(directory, "versions/${old.versionId}/.package-interrupted.tmp").writeText("partial")
        restart(); assertOld()
    }

    @Test fun traversalAndSymlinkVersionPathsAreRejected() {
        listOf("../escape", "..", ".", "/absolute", "a/b", "a\\b", "%2e%2e", "").forEach { id ->
            assertFailsWith<IllegalArgumentException> { RecipeReference(id, old.sha256, 1) }
        }
        sync(old)
        val link = File(directory, "versions/link")
        Files.createSymbolicLink(link.toPath(), directory.toPath())
        try {
            assertFailsWith<IllegalArgumentException> { manager.install(old.copy(versionId = "link"), oldBody) }
        } finally {
            link.delete()
        }
        assertOld()
    }

    @Test fun incompatibleExpectedOrManifestEngineNeverBecomesVisible() {
        sync(old)
        assertFailsWith<IllegalArgumentException> { RecipeReference("engine-future", old.sha256, RecipeEngine.VERSION + 1) }
        val json = JSONObject(newBody).also { it.getJSONObject("manifest").put("minEngineVersion", 2) }
        val hash = RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(json))
        json.getJSONObject("manifest").put("hash", hash)
        val failure = assertFailsWith<IllegalArgumentException> {
            manager.install(newer.copy(sha256 = hash), json.toString())
        }
        assertEquals("recipe engine mismatch", failure.message)
        assertOld()
    }

    @Test fun malformedDuplicatePartialAndWrongPathCatalogsPreserveMappings() {
        sync(old)
        val wrongPath = JSONObject(listing(newer)).also {
            it.getJSONArray("items").getJSONObject(0).put("downloadPath", "https://other/recipe")
        }.toString()
        val wrongProtocol = JSONObject(listing(newer)).put("protocolVersion", "cloudctl.recipe/v9").toString()
        listOf("{}", listing(old, newer), wrongPath, wrongProtocol).forEach { invalid ->
            assertFails { lifecycle.synchronize(invalid, ::download) }
            assertOld()
        }
        assertNull(store.pendingRecipeCatalog())
    }

    @Test fun revokeEmptyCatalogWaitsForIdleAndRetainsHistoricalPackage() {
        sync(old); queue(); store.claimNext()
        lifecycle.synchronize(listing(), ::download); assertOld()
        restart(); assertOld()
        idle()
        assertNull(RecipeCatalog.activeVersion(type))
        assertEquals(oldBody, lifecycle.ensureCommand(command()) { error("old package retained") })
    }

    @Test fun nestedCommandPinSurvivesLeaseRenewalAndRejectsVersionOrHashDrift() {
        fun payload(ref: RecipeReference, attempt: String): String = JSONObject().put("taskId", "task-1")
            .put("command", JSONObject().put("taskId", "task-1").put("protocolVersion", CommandV1Parser.PROTOCOL)
                .put("attemptId", attempt).put("lease", JSONObject().put("controlEpoch", attempt))
                .put("recipe", JSONObject().put("versionId", ref.versionId).put("sha256", ref.sha256)
                    .put("engineMinVersion", ref.engineMinVersion))).toString()
        store.enqueueTask("task-1", payload(old, "attempt-1"), "lease-1", 0)
        assertTrue(store.enqueueTask("task-1", payload(old, "attempt-2"), "lease-2", 0))
        assertFailsWith<IllegalArgumentException> {
            store.enqueueTask("task-1", payload(newer, "attempt-3"), "lease-3", 0)
        }
        assertFailsWith<IllegalArgumentException> {
            store.enqueueTask("task-1", payload(old.copy(sha256 = newer.sha256), "attempt-3"), "lease-3", 0)
        }
        restart()
        assertTrue(store.claimNext()!!.payload.contains(old.versionId))
    }

    @Test fun unresolvedCommitPinsCatalogAfterFinishReplacementLeaseAndReopen() {
        sync(old); queue(); store.claimNext()
        store.recordActionIntent("commit", "task-1", "hash")
        sync(newer)
        restart()
        assertOld()
        assertTrue(store.hasBlockingHead())
        assertFalse(store.markResumeCheck("task-1", "lease-new"))
        assertFalse(store.enqueueTask("task-1", taskPayload(old), "lease-new", 20))
        store.finish("task-1", true)
        lifecycle.activatePending()
        assertOld()
        store.markActionUnknown("commit")
        restart()
        store.finish("task-1", false)
        lifecycle.activatePending()
        assertOld()
        assertNotNull(store.pendingRecipeCatalog())
        assertNull(store.claimNext())
    }

    @Test fun replacementLeaseCannotChangeFrozenRecipeAndSingleRunnerIsEnforced() {
        queue()
        assertFailsWith<IllegalArgumentException> { store.enqueueTask("task-1", taskPayload(newer), "lease-2", 0) }
        assertNotNull(store.claimNext())
        store.enqueueTask("task-2", "{}", "lease-2", 0)
        assertNull(store.claimNext())
        assertNull(store.claimResume())
    }

    @Test fun multiCommandPackageActivatesCompleteMappingAndExecutesSecondCommandSelection() {
        val secondType = "xianyu.collect_orders.v1"
        val json = JSONObject(oldBody)
        val manifest = json.getJSONObject("manifest")
        manifest.put("commandTypes", JSONArray(listOf(type, secondType)))
        manifest.put("signingKeyId", "ephemeral-test")
        val hash = RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(json))
        manifest.put("hash", hash)
        val payload = CanonicalJson.dumps(JSONObject().put("artifactSha256", hash).put("manifest", manifest)
            .put("sbomRef", "recipe://local").put("sbomSha256", hash)).toByteArray(Charsets.UTF_8)
        val key = org.bouncycastle.crypto.params.Ed25519PrivateKeyParameters(java.security.SecureRandom())
        val signer = org.bouncycastle.crypto.signers.Ed25519Signer()
        signer.init(true, key)
        signer.update(payload, 0, payload.size)
        val base64 = java.util.Base64.getEncoder()
        json.put("signature", JSONObject().put("algorithm", "Ed25519").put("keyId", "ephemeral-test")
            .put("digest", base64.encodeToString(signer.generateSignature())))
        val multiManager = RecipePackageManager(directory, mapOf("ephemeral-test" to base64.encodeToString(key.generatePublicKey().encoded)))
        val multiLifecycle = RecipeLifecycle(multiManager, store)
        val ref = RecipeReference("version-multi", hash, 1)
        val catalog = JSONObject(listing(ref))
        val items = catalog.getJSONArray("items")
        items.put(JSONObject(items.getJSONObject(0).toString()).put("commandType", secondType))
        multiLifecycle.synchronize(catalog.toString()) { RecipeDownload(json.toString(), hash) }
        assertEquals(ref.versionId, RecipeCatalog.activeVersion(type))
        assertEquals(ref.versionId, RecipeCatalog.activeVersion(secondType))
        assertEquals(json.toString(), multiLifecycle.ensureCommand(command(ref).copy(commandType = secondType)) {
            error("verified multi-command package already exists")
        })
    }

    @Test fun versionFourDatabaseUpgradeRetainsCatalogAndPendingTask() {
        sync(old)
        queue()
        store.writableDatabase.execSQL("DROP TABLE controlled_action")
        store.writableDatabase.execSQL("ALTER TABLE event_outbox DROP COLUMN superseded_at")
        store.writableDatabase.execSQL("ALTER TABLE event_outbox DROP COLUMN superseded_reason")
        store.writableDatabase.version = 4
        restart()
        assertEquals(5, store.readableDatabase.version)
        assertOld()
        assertTrue(store.claimNext()!!.payload.contains(old.versionId))
        assertNull(store.controlledActionIdentity("not-present"))
    }

    @Test fun versionThreeDatabaseUpgradeRetainsPinnedTasks() {
        queue()
        // Reconstruct the real v3 schema, excluding both later schema additions.
        store.writableDatabase.execSQL("DROP TABLE controlled_action")
        store.writableDatabase.execSQL("ALTER TABLE event_outbox DROP COLUMN superseded_at")
        store.writableDatabase.execSQL("ALTER TABLE event_outbox DROP COLUMN superseded_reason")
        store.writableDatabase.execSQL("DROP TABLE recipe_catalog")
        store.writableDatabase.version = 3
        restart()
        assertEquals(5, store.readableDatabase.version)
        assertEquals(AutomationStore.EMPTY_RECIPE_CATALOG, store.activeRecipeCatalog())
        assertTrue(store.claimNext()!!.payload.contains(old.versionId))
    }

    @Test fun restartReverifiesDiskAndRejectsCorruption() {
        sync(old)
        File(directory, "versions/${old.versionId}/package.json").writeText(newBody)
        RecipeCatalog.clear()
        assertFailsWith<IllegalArgumentException> { lifecycle.restore() }
        assertNull(RecipeCatalog.activeVersion(type))
        assertFails { lifecycle.ensureCommand(command()) { error("cannot overwrite immutable corrupted version") } }
    }
}
