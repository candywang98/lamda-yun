package com.company.cloudctl.companion.updates

import com.company.cloudctl.companion.automation.CanonicalJson
import com.company.cloudctl.companion.automation.CommandV1Parser
import com.company.cloudctl.companion.automation.RecipeCatalog
import com.company.cloudctl.companion.automation.RecipeEngine
import com.company.cloudctl.companion.automation.RecipeSignatureVerifier
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption

/** Version IDs are server identities, separate from the signed manifest's semantic version. */
data class RecipeReference(val versionId: String, val sha256: String, val engineMinVersion: Int) {
    init {
        require(Regex("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$").matches(versionId)) { "Invalid recipe versionId" }
        require(Regex("^[a-f0-9]{64}$").matches(sha256)) { "Invalid recipe sha256" }
        require(engineMinVersion in 1..RecipeEngine.VERSION) { CommandV1Parser.UNSUPPORTED_RECIPE }
    }
}

class RecipePackageManager(
    private val root: File,
    private val publicKeys: Map<String, String>,
) {
    /** Verification always precedes visibility. Existing version identities are never overwritten. */
    @Synchronized
    fun install(expected: RecipeReference, encoded: String): JSONObject {
        verify(expected, encoded)
        val target = packageFile(expected.versionId)
        if (target.exists()) {
            val previous = target.readText(Charsets.UTF_8)
            verify(expected, previous)
            require(CanonicalJson.dumps(JSONObject(previous)) == CanonicalJson.dumps(JSONObject(encoded))) {
                "recipe version is immutable"
            }
        } else {
            val versions = target.parentFile!!.parentFile!!
            check(versions.mkdirs() || versions.isDirectory)
            val staging = Files.createTempDirectory(versions.toPath(), ".staging-").toFile()
            val temp = File(staging, "package.json")
            try {
                FileOutputStream(temp).use { output ->
                    output.write(encoded.toByteArray(Charsets.UTF_8))
                    output.fd.sync()
                }
                verify(expected, temp.readText(Charsets.UTF_8))
                // Publish the complete directory at once. An existing nonempty version directory
                // cannot be replaced, including by a concurrent installer. Never copy/overwrite.
                Files.move(staging.toPath(), target.parentFile!!.toPath(), StandardCopyOption.ATOMIC_MOVE)
            } finally {
                staging.deleteRecursively()
            }
        }
        RecipeCatalog.putVerified(expected.versionId, encoded)
        return JSONObject().put("status", "downloaded").put("versionId", expected.versionId).put("sha256", expected.sha256)
    }

    @Synchronized
    fun load(expected: RecipeReference): String? {
        val target = packageFile(expected.versionId)
        if (!target.isFile) return null
        return target.readText(Charsets.UTF_8).also {
            verify(expected, it)
            RecipeCatalog.putVerified(expected.versionId, it)
        }
    }

    private fun verify(expected: RecipeReference, encoded: String) {
        val json = JSONObject(encoded)
        require(json.getString("apiVersion") == "cloudctl.recipe/v1") { CommandV1Parser.UNSUPPORTED_PROTOCOL }
        require(json.getString("kind") == "LocalRecipePackage") { CommandV1Parser.UNSUPPORTED_RECIPE }
        val manifest = json.getJSONObject("manifest")
        val computed = RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(json))
        require(manifest.getString("hash") == computed && computed == expected.sha256) { "recipe hash mismatch" }
        require(manifest.getInt("minEngineVersion") == expected.engineMinVersion) { "recipe engine mismatch" }
        // A server version cannot shadow an APK builtin identity.
        require(com.company.cloudctl.companion.automation.BuiltinRecipes.packageJson(expected.versionId) == null) {
            "downloaded recipe cannot replace a builtin identity"
        }
        RecipeSignatureVerifier.verifyPackage(json, publicKeys)
    }

    private fun packageFile(versionId: String): File {
        val versions = File(root, "versions").canonicalFile
        val directory = File(versions, versionId).canonicalFile
        require(directory.parentFile == versions) { "Invalid recipe version path" }
        val target = File(directory, "package.json")
        require(target.canonicalFile.parentFile == directory) { "Invalid recipe package path" }
        return target
    }
}
