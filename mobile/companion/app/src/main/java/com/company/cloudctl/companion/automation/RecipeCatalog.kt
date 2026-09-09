package com.company.cloudctl.companion.automation

import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap

object RecipeCatalog {
    private val verified = ConcurrentHashMap<String, String>()

    fun putVerified(versionId: String, encoded: String) {
        verified[versionId] = encoded
    }

    @Volatile
    private var active: Map<String, String> = emptyMap()

    fun activate(mapping: Map<String, String>) { active = mapping.toMap() }

    fun activeVersion(commandType: String): String? = active[commandType]

    fun clear() {
        active = emptyMap()
        verified.clear()
    }

    fun jsonFor(command: CommandV1): String {
        val encoded = verified[command.recipeVersionId]
            ?: BuiltinRecipes.packageJson(command.recipeVersionId)
            ?: error(CommandV1Parser.UNSUPPORTED_RECIPE)
        val root = JSONObject(encoded)
        val manifest = root.getJSONObject("manifest")
        require(manifest.getString("hash") == command.recipeSha256) { "recipe hash mismatch" }
        require(manifest.getString("app") == command.targetPackage) { "recipe app does not match command" }
        require(command.engineMinVersion in 1..RecipeEngine.VERSION &&
            manifest.getInt("minEngineVersion") == command.engineMinVersion) { "recipe engine mismatch" }
        val types = manifest.getJSONArray("commandTypes")
        require((0 until types.length()).any { types.getString(it) == command.commandType }) {
            CommandV1Parser.UNSUPPORTED_RECIPE
        }
        return encoded
    }
}
