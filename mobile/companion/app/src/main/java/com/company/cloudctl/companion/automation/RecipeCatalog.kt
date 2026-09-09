package com.company.cloudctl.companion.automation

import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap

object RecipeCatalog {
    private val verified = ConcurrentHashMap<String, String>()

    fun putVerified(versionId: String, encoded: String) {
        verified[versionId] = encoded
    }

    fun clear() {
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
        require(manifest.getJSONArray("commandTypes").getString(0) == command.commandType) {
            CommandV1Parser.UNSUPPORTED_RECIPE
        }
        return encoded
    }
}
