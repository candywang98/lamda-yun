package com.company.cloudctl.companion.automation

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class BuiltinRecipesTest {
    @Test
    fun loadsHashPinnedProbeRecipe() {
        val command = command(
            commandType = "device.probe_capabilities.v1",
            recipeVersionId = "recipe-device-probe-1",
            recipeSha256 = "901f795b2512891cd5ee08162626d0ad6a1c92ad9d7b922516c626f9d6f155b4",
            targetPackage = "com.company.cloudctl.companion",
        )
        val encoded = BuiltinRecipes.jsonFor(command)
        val manifest = JSONObject(encoded).getJSONObject("manifest")
        assertEquals("recipe-device-probe-1", manifest.getString("id"))
        assertEquals(command.recipeSha256, manifest.getString("hash"))
        assertEquals(command.targetPackage, manifest.getString("app"))
    }

    @Test
    fun publishRecipeIsOpenOnlyAndHashPinned() {
        val command = command(
            commandType = "xianyu.publish_listing.v1",
            recipeVersionId = "recipe-xianyu-publish-1",
            recipeSha256 = "a2331b8076dd28cd34f574f359b7e549ebef1f0ebd060bff2fad0ab410a84c0f",
            targetPackage = "com.taobao.idlefish",
        )
        assertTrue(ClaimedTaskInterpreter.isOpenOnly(command))
        BuiltinRecipes.jsonFor(command)
        assertFailsWith<IllegalArgumentException> {
            BuiltinRecipes.jsonFor(command.copy(recipeSha256 = "c".repeat(64)))
        }
    }

    private fun command(
        commandType: String,
        recipeVersionId: String,
        recipeSha256: String,
        targetPackage: String,
    ) = CommandV1(
        protocolVersion = CommandV1Parser.PROTOCOL,
        taskId = "task-1",
        attemptId = "attempt-1",
        commandType = commandType,
        deviceId = "device-1",
        accountId = "account-1",
        bindingVersion = 1,
        snapshotId = "snap",
        snapshotSha256 = "a".repeat(64),
        recipeVersionId = recipeVersionId,
        recipeSha256 = recipeSha256,
        engineMinVersion = 1,
        targetPackage = targetPackage,
        requiredCapabilities = listOf("accessibility"),
        controlEpoch = 1,
        leaseExpiresAt = "2026-09-08T00:00:00Z",
        mediaDeliveryId = null,
        legacyStepsEnabled = false,
        parameters = org.json.JSONObject(),
    )
}
