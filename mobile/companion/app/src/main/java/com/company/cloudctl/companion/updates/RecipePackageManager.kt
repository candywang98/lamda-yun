package com.company.cloudctl.companion.updates

import com.company.cloudctl.companion.automation.CanonicalJson
import com.company.cloudctl.companion.automation.CommandV1Parser
import com.company.cloudctl.companion.automation.RecipeCatalog
import com.company.cloudctl.companion.automation.RecipeEngine
import com.company.cloudctl.companion.automation.RecipeSignatureVerifier
import org.json.JSONObject
import java.io.File

class RecipePackageManager(
    private val root: File,
    private val publicKeys: Map<String, String>,
    private val runningRecipeHash: () -> String? = { null },
) {
    fun install(versionId: String, encoded: String): JSONObject {
        val rootJson = JSONObject(encoded)
        require(rootJson.getString("apiVersion") == "cloudctl.recipe/v1") { CommandV1Parser.UNSUPPORTED_PROTOCOL }
        require(rootJson.getString("kind") == "LocalRecipePackage") { CommandV1Parser.UNSUPPORTED_RECIPE }
        val computed = RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(rootJson))
        val manifest = rootJson.getJSONObject("manifest")
        require(manifest.getString("hash") == computed) { "recipe hash does not match canonical graph" }
        RecipeSignatureVerifier.verifyPackage(rootJson, publicKeys)
        val versionDir = File(File(root, "versions"), versionId)
        val temp = File(root, "tmp-$versionId.json")
        temp.parentFile?.mkdirs()
        temp.writeText(encoded)
        val storedHash = RecipeEngine.sha256Bytes(temp.readBytes())
        require(storedHash == RecipeEngine.sha256Bytes(encoded.toByteArray(Charsets.UTF_8))) {
            "recipe package temp file checksum mismatch"
        }
        if (versionDir.exists()) versionDir.deleteRecursively()
        versionDir.mkdirs()
        val target = File(versionDir, "package.json")
        if (!temp.renameTo(target)) {
            temp.copyTo(target, overwrite = true)
            temp.delete()
        }
        val current = runningRecipeHash()
        if (current != null && current != computed) {
            return JSONObject().put("status", "downloaded").put("versionId", versionId).put("sha256", computed)
        }
        RecipeCatalog.putVerified(versionId, encoded)
        return JSONObject().put("status", "active").put("versionId", versionId).put("sha256", computed)
    }
}
