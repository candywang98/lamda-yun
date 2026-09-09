package com.company.cloudctl.companion.automation

import com.company.cloudctl.companion.updates.RecipePackageManager
import com.company.cloudctl.companion.updates.RecipeReference
import org.json.JSONObject
import java.nio.file.Files
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class RecipeCatalogTest {
    @AfterTest
    fun reset() {
        RecipeCatalog.clear()
    }

    @Test
    fun builtinProbeHashMatchesCanonicalEncoder() {
        val encoded = BuiltinRecipes.packageJson("recipe-device-probe-1")!!
        val root = JSONObject(encoded)
        assertEquals(
            "901f795b2512891cd5ee08162626d0ad6a1c92ad9d7b922516c626f9d6f155b4",
            RecipeEngine.sha256Bytes(CanonicalJson.recipeHashPayload(root)),
        )
    }

    @Test
    fun installsSignedCatalogAndRejectsTamper() {
        val rootDir = Files.createTempDirectory("recipe-catalog").toFile()
        val manager = RecipePackageManager(
            rootDir,
            mapOf("test-automation-1" to "A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg="),
        )
        val installed = manager.install(RecipeReference("11111111-1111-7111-8111-111111111111", "c37e24bc039a9d9048424a785b2a641d8d47b1f53d67af8cf0410b574448064e", 1), SIGNED_PROBE)
        assertEquals("downloaded", installed.getString("status"))
        assertEquals("c37e24bc039a9d9048424a785b2a641d8d47b1f53d67af8cf0410b574448064e", installed.getString("sha256"))
        val command = CommandV1(
            protocolVersion = CommandV1Parser.PROTOCOL,
            taskId = "task-1",
            attemptId = "attempt-1",
            commandType = "device.probe_capabilities.v1",
            deviceId = "device-1",
            accountId = "account-1",
            bindingVersion = 1,
            snapshotId = "snap",
            snapshotSha256 = "a".repeat(64),
            recipeVersionId = "11111111-1111-7111-8111-111111111111",
            recipeSha256 = "c37e24bc039a9d9048424a785b2a641d8d47b1f53d67af8cf0410b574448064e",
            engineMinVersion = 1,
            targetPackage = "com.company.cloudctl.companion",
            requiredCapabilities = listOf("accessibility"),
            controlEpoch = 1,
            leaseExpiresAt = "2026-09-08T00:00:00Z",
            mediaDeliveryId = null,
            legacyStepsEnabled = false,
            parameters = JSONObject(),
        )
        assertTrue(RecipeCatalog.jsonFor(command).contains("recipe-device-probe-signed"))
        val tampered = JSONObject(SIGNED_PROBE).put("graph", JSONObject(SIGNED_PROBE).getJSONObject("graph").put("maxIterations", 7)).toString()
        assertFailsWith<IllegalArgumentException> {
            manager.install(RecipeReference("11111111-1111-7111-8111-111111111112", "c37e24bc039a9d9048424a785b2a641d8d47b1f53d67af8cf0410b574448064e", 1), tampered)
        }
    }

    companion object {
        internal const val SIGNED_PROBE =
            """{"apiVersion":"cloudctl.recipe/v1","kind":"LocalRecipePackage","manifest":{"id":"recipe-device-probe-signed","version":"1.0.1","hash":"c37e24bc039a9d9048424a785b2a641d8d47b1f53d67af8cf0410b574448064e","signingKeyId":"test-automation-1","minEngineVersion":1,"platform":"companion","app":"com.company.cloudctl.companion","commandTypes":["device.probe_capabilities.v1"]},"graph":{"startStateId":"probe","maxIterations":8,"maxDurationMs":30000,"states":[{"stateId":"probe","action":"log","onSuccess":"SUCCEEDED","terminal":true}]},"signature":{"algorithm":"Ed25519","keyId":"test-automation-1","digest":"azxODKM26G++62MMTLw8etG+Astk206uV3vZ0Mnu8jA4UmHjzLHhMJeaosNDIebtm/kx3zG5MOvrTVTxZ/9CDg=="}}"""
    }
}
