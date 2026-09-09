package com.company.cloudctl.companion.automation

import com.company.cloudctl.companion.updates.RecipePackageManager
import com.company.cloudctl.companion.updates.RecipeReference
import org.json.JSONObject
import java.nio.file.Files
import java.util.Base64
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class RecipeSignatureVerifierTest {
    private val publicKey = "LZxWUG0N3Ke3PiBS2nGPZm0PMVa2lIJfJQynfu/oR4M="
    private val keys = mapOf("phase1-recipe-1" to publicKey)
    private val hash = "825921a415b7b0eaeb832ce1fb6e97847f9f981a45bb57db990491f1001ebd1f"

    private fun fixture(name: String): ByteArray =
        requireNotNull(javaClass.getResourceAsStream("/recipes/$name")).use { it.readBytes() }

    private fun packageJson() = JSONObject(fixture("published-probe.json").toString(Charsets.UTF_8))

    @Test
    fun publishedGraphMatchesPublisherBytesAndHash() {
        val bytes = CanonicalJson.recipeHashPayload(packageJson())
        assertContentEquals(fixture("published-probe-graph.json"), bytes)
        assertEquals(hash, RecipeEngine.sha256Bytes(bytes))
    }

    @Test
    fun verifiesPublishedSigningBytesAndInstallsPackage() {
        val root = packageJson()
        val signature = root.getJSONObject("signature").getString("digest")
        assertTrue(RecipeSignatureVerifier.verifyEd25519(publicKey, signature, fixture("published-probe-signing.json")))
        RecipeSignatureVerifier.verifyPackage(root, keys)
        val directory = Files.createTempDirectory("published-recipe").toFile()
        try {
            val result = RecipePackageManager(directory, keys).install(RecipeReference("published-probe", root.getJSONObject("manifest").getString("hash"), 1), root.toString())
            assertEquals(hash, result.getString("sha256"))
            assertTrue(directory.resolve("versions/published-probe/package.json").isFile)
        } finally {
            directory.deleteRecursively()
            RecipeCatalog.clear()
        }
    }

    @Test
    fun rejectsModifiedPayloadAndSignature() {
        val signature = packageJson().getJSONObject("signature").getString("digest")
        val bytes = fixture("published-probe-signing.json")
        assertFalse(RecipeSignatureVerifier.verifyEd25519(publicKey, signature, bytes + byteArrayOf(0)))
        val changedSignature = Base64.getDecoder().decode(signature).also { it[0] = (it[0].toInt() xor 1).toByte() }
        assertFalse(RecipeSignatureVerifier.verifyEd25519(publicKey, Base64.getEncoder().encodeToString(changedSignature), bytes))
    }

    @Test
    fun rejectsWrongKeyAndMalformedEncodings() {
        val signature = packageJson().getJSONObject("signature").getString("digest")
        val bytes = fixture("published-probe-signing.json")
        val otherKey = "A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg="
        assertFalse(RecipeSignatureVerifier.verifyEd25519(otherKey, signature, bytes))
        assertFalse(RecipeSignatureVerifier.verifyEd25519("not base64!", signature, bytes))
        assertFalse(RecipeSignatureVerifier.verifyEd25519(Base64.getEncoder().encodeToString(ByteArray(44)), signature, bytes))
        assertFalse(RecipeSignatureVerifier.verifyEd25519(publicKey, "not base64!", bytes))
        assertFalse(RecipeSignatureVerifier.verifyEd25519(publicKey, Base64.getEncoder().encodeToString(ByteArray(63)), bytes))
    }

    @Test
    fun rejectsUntrustedKeyAndModifiedGraphBeforeCreatingDirectory() {
        val parent = Files.createTempDirectory("rejected-recipe").toFile()
        val directory = parent.resolve("recipes")
        try {
            assertFailsWith<IllegalStateException> {
                RecipePackageManager(directory, emptyMap()).install(RecipeReference("untrusted", packageJson().getJSONObject("manifest").getString("hash"), 1), packageJson().toString())
            }
            val tampered = packageJson()
            tampered.getJSONObject("graph").put("maxIterations", 7)
            assertFailsWith<IllegalArgumentException> {
                RecipePackageManager(directory, keys).install(RecipeReference("tampered", packageJson().getJSONObject("manifest").getString("hash"), 1), tampered.toString())
            }
            assertFalse(directory.exists())
        } finally {
            parent.deleteRecursively()
        }
    }

    @Test
    fun rejectsModifiedSignatureBeforeCreatingDirectory() {
        val parent = Files.createTempDirectory("rejected-signature").toFile()
        val directory = parent.resolve("recipes")
        try {
            val tampered = packageJson()
            tampered.getJSONObject("signature").put("digest", Base64.getEncoder().encodeToString(ByteArray(64)))
            assertFailsWith<IllegalArgumentException> {
                RecipePackageManager(directory, keys).install(RecipeReference("tampered", packageJson().getJSONObject("manifest").getString("hash"), 1), tampered.toString())
            }
            assertFalse(directory.exists())
        } finally {
            parent.deleteRecursively()
        }
    }
}
