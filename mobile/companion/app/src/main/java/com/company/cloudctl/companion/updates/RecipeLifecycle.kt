package com.company.cloudctl.companion.updates

import com.company.cloudctl.companion.automation.BuiltinRecipes
import com.company.cloudctl.companion.automation.CommandV1
import com.company.cloudctl.companion.automation.RecipeCatalog
import org.json.JSONObject

interface RecipeLifecycleStore {
    fun activeRecipeCatalog(): String
    fun pendingRecipeCatalog(): String?
    fun stageRecipeCatalog(encoded: String)
    /** Atomically checks task state and activates the complete pending snapshot only while idle. */
    fun activatePendingRecipeCatalog(): String
}

data class RecipeDownload(val body: String, val sha256: String?)

/** Network callbacks use the validated exact version ID; catalog downloadPath is never trusted. */
class RecipeLifecycle(
    private val packages: RecipePackageManager,
    private val store: RecipeLifecycleStore,
) {
    fun restore() {
        val active = parse(store.activeRecipeCatalog())
        active.values.forEach { requireNotNull(packages.load(it)) { "active recipe package missing" } }
        RecipeCatalog.activate(active.mapValues { it.value.versionId })
        activatePending()
    }

    fun synchronize(listing: String, download: (String) -> RecipeDownload) {
        val desired = parse(listing)
        desired.forEach { (commandType, ref) ->
            val encoded = ensure(ref, download)
            val types = JSONObject(encoded).getJSONObject("manifest").getJSONArray("commandTypes")
            require((0 until types.length()).any { types.getString(it) == commandType }) { "recipe command type mismatch" }
        }
        // Partial or invalid responses never replace either known-good snapshot.
        store.stageRecipeCatalog(listing)
        activatePending()
    }

    fun activatePending() {
        store.pendingRecipeCatalog()?.let { pending ->
            parse(pending).values.forEach { requireNotNull(packages.load(it)) { "pending recipe package missing" } }
        }
        val active = parse(store.activatePendingRecipeCatalog())
        active.values.forEach { requireNotNull(packages.load(it)) { "active recipe package missing" } }
        RecipeCatalog.activate(active.mapValues { it.value.versionId })
    }

    fun ensureCommand(command: CommandV1, download: (String) -> RecipeDownload): String {
        val ref = RecipeReference(command.recipeVersionId, command.recipeSha256, command.engineMinVersion)
        if (BuiltinRecipes.packageJson(ref.versionId) == null) ensure(ref, download)
        // Exact builtin identity AND hash must match, otherwise fail closed.
        return RecipeCatalog.jsonFor(command)
    }

    private fun ensure(ref: RecipeReference, download: (String) -> RecipeDownload): String {
        packages.load(ref)?.let { return it }
        val response = download(ref.versionId)
        require(response.sha256?.lowercase() == ref.sha256) { "recipe download checksum mismatch" }
        packages.install(ref, response.body)
        return response.body
    }

    private fun parse(encoded: String): Map<String, RecipeReference> {
        val root = JSONObject(encoded)
        require(root.getString("protocolVersion") == "cloudctl.recipe/v1") { "Invalid recipe catalog protocol" }
        val items = root.getJSONArray("items")
        val result = linkedMapOf<String, RecipeReference>()
        for (index in 0 until items.length()) {
            val item = items.getJSONObject(index)
            val command = item.getString("commandType")
            require(command.isNotBlank() && command !in result) { "Duplicate or empty recipe command type" }
            val ref = RecipeReference(item.getString("versionId"), item.getString("sha256"), item.getInt("engineMinVersion"))
            require(item.getString("downloadPath") == "/companion/v2/recipes/${ref.versionId}") { "Invalid recipe download path" }
            result[command] = ref
        }
        return result
    }
}
