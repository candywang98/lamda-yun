package com.company.cloudctl.companion.updates

import android.content.Context
import android.content.ContextWrapper
import android.database.DatabaseErrorHandler
import android.database.sqlite.SQLiteDatabase
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.company.cloudctl.companion.automation.CanonicalJson
import com.company.cloudctl.companion.automation.CommandV1
import com.company.cloudctl.companion.automation.CommandV1Parser
import com.company.cloudctl.companion.automation.RecipeCatalog
import com.company.cloudctl.companion.automation.RecipeEngine
import com.company.cloudctl.companion.data.AutomationStore
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.IOException
import java.nio.file.Files

/** Real filesystem/SQLite tests; no task execution, networking, or production databases. */
@RunWith(AndroidJUnit4::class)
class RecipeStorageInstrumentationTest {
    private lateinit var directory: File
    private lateinit var databaseContext: Context
    private lateinit var store: AutomationStore
    private lateinit var manager: RecipePackageManager
    private lateinit var lifecycle: RecipeLifecycle
    private lateinit var body: String
    private lateinit var truncatedBody: String
    private lateinit var old: RecipeReference
    private lateinit var newer: RecipeReference
    private lateinit var activeSnapshot: String
    private var pendingSnapshot: String? = null
    private val commandType = "device.probe_capabilities.v1"
    private val keys = mapOf(
        "phase1-recipe-1" to "LZxWUG0N3Ke3PiBS2nGPZm0PMVa2lIJfJQynfu/oR4M=",
    )

    @Before fun setUp() {
        val testContext = InstrumentationRegistry.getInstrumentation().context
        // Instrumentation runs with the target UID; the test APK's private cache
        // may not exist or be writable. Only use a unique disposable cache subtree.
        val cache = InstrumentationRegistry.getInstrumentation().targetContext.cacheDir
        directory = Files.createTempDirectory(cache.toPath(), "recipe-storage-").toFile()
        // AutomationStore has a fixed database name. Redirect both database-open
        // overloads into this directory; never open the target's business database.
        databaseContext = object : ContextWrapper(testContext) {
            override fun getDatabasePath(name: String): File {
                require(name == AutomationStore.DATABASE_NAME)
                return File(directory, name)
            }

            override fun openOrCreateDatabase(
                name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?,
            ): SQLiteDatabase = SQLiteDatabase.openOrCreateDatabase(getDatabasePath(name), factory)

            override fun openOrCreateDatabase(
                name: String, mode: Int, factory: SQLiteDatabase.CursorFactory?,
                errorHandler: DatabaseErrorHandler?,
            ): SQLiteDatabase = SQLiteDatabase.openOrCreateDatabase(getDatabasePath(name).path, factory, errorHandler)
        }
        body = testContext.assets.open("recipes/published-probe.json").bufferedReader().use { it.readText() }
        truncatedBody = testContext.assets.open("recipes/published-probe-truncated.json").bufferedReader().use { it.readText() }
        val manifest = JSONObject(body).getJSONObject("manifest")
        old = RecipeReference("storage-old", manifest.getString("hash"), manifest.getInt("minEngineVersion"))
        // Server identity differs even though the signed content is deliberately identical.
        newer = old.copy(versionId = "storage-new")
        RecipeCatalog.clear()
        openStoreAndLifecycle()
        lifecycle.synchronize(listing(old)) { id ->
            assertEquals(old.versionId, id)
            RecipeDownload(body, old.sha256)
        }
        activeSnapshot = store.activeRecipeCatalog()
        pendingSnapshot = store.pendingRecipeCatalog()
        assertNull(pendingSnapshot)
        assertOldUsable()
    }

    @After fun tearDown() {
        try {
            if (::store.isInitialized) store.close()
        } finally {
            RecipeCatalog.clear()
            // Never deleteDatabase: only remove this test's unique cache subtree.
            if (::directory.isInitialized) directory.deleteRecursively()
        }
    }

    @Test fun interruptedDownloadRetainsOldPackageAndCatalogAcrossReopen() {
        assertNull(manager.load(newer))
        val interruption = IOException("fixture download interrupted")
        val requested = mutableListOf<String>()
        try {
            lifecycle.synchronize(listing(newer)) { id ->
                requested += id
                throw interruption
            }
            fail("Expected the interrupted download to propagate IOException")
        } catch (failure: IOException) {
            assertSame(interruption, failure)
        }
        assertEquals(listOf(newer.versionId), requested)
        assertOldUsable()
        reopen()
        assertOldUsable()
    }

    @Test fun truncatedSignedJsonInstallRetainsOldPackageAndCatalogAcrossReopen() {
        assertTrue(body.startsWith(truncatedBody))
        assertNull(manager.load(newer))
        try {
            manager.install(newer, truncatedBody)
            fail("Expected incomplete signed JSON to fail parsing")
        } catch (failure: JSONException) {
            assertEquals(JSONException::class.java, failure.javaClass)
        }
        assertOldUsable()
        reopen()
        assertOldUsable()
    }

    @Test fun staleTempFileCannotReplaceCompleteOldPackageAcrossReopen() {
        val stale = File(packageFile(old).parentFile, "package.json.tmp")
        stale.writeText(truncatedBody, Charsets.UTF_8)
        reopen()
        assertOldUsable()
        // Reinstalling the same immutable identity must also ignore the orphan temp file.
        manager.install(old, body)
        assertOldUsable()
        reopen()
        assertOldUsable()
    }

    private fun openStoreAndLifecycle() {
        store = AutomationStore(databaseContext)
        assertEquals(directory.canonicalFile, File(store.writableDatabase.path).canonicalFile.parentFile)
        manager = RecipePackageManager(File(directory, "packages"), keys)
        lifecycle = RecipeLifecycle(manager, store)
    }

    private fun reopen() {
        store.close()
        RecipeCatalog.clear()
        openStoreAndLifecycle()
        lifecycle.restore()
    }

    private fun assertOldUsable() {
        assertEquals(activeSnapshot, store.activeRecipeCatalog())
        assertEquals(pendingSnapshot, store.pendingRecipeCatalog())
        assertEquals(old.versionId, RecipeCatalog.activeVersion(commandType))
        assertFalse(packageFile(newer).exists())
        assertNull(manager.load(newer))
        val retained = packageFile(old).readText(Charsets.UTF_8)
        assertEquals(body, retained)
        assertEquals(old.sha256, JSONObject(retained).getJSONObject("manifest").getString("hash"))
        assertEquals(old.sha256, RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(JSONObject(retained))))
        assertEquals(body, manager.load(old)) // Includes real Ed25519 verification.
        assertEquals(body, lifecycle.ensureCommand(command()) { error("Retained old package must not download") })
        assertEquals(body, RecipeCatalog.jsonFor(command()))
    }

    private fun packageFile(ref: RecipeReference) = File(directory, "packages/versions/${ref.versionId}/package.json")

    private fun listing(ref: RecipeReference): String = JSONObject()
        .put("protocolVersion", "cloudctl.recipe/v1")
        .put("items", JSONArray().put(JSONObject()
            .put("versionId", ref.versionId).put("sha256", ref.sha256)
            .put("engineMinVersion", ref.engineMinVersion).put("commandType", commandType)
            .put("downloadPath", "/companion/v2/recipes/${ref.versionId}")))
        .toString()

    private fun command() = CommandV1(
        CommandV1Parser.PROTOCOL, "storage-task", "storage-attempt", commandType,
        "storage-device", "storage-account", 1, "storage-snapshot", "a".repeat(64),
        old.versionId, old.sha256, old.engineMinVersion, "com.company.cloudctl.companion",
        emptyList(), 1, "2099-01-01T00:00:00Z", null, false, JSONObject(),
    )
}
