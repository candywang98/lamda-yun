package com.company.cloudctl.companion.automation

import org.json.JSONObject

data class CommandV1(
    val protocolVersion: String,
    val taskId: String,
    val attemptId: String,
    val commandType: String,
    val deviceId: String,
    val accountId: String,
    val bindingVersion: Int,
    val snapshotId: String,
    val snapshotSha256: String,
    val recipeVersionId: String,
    val recipeSha256: String,
    val engineMinVersion: Int,
    val targetPackage: String,
    val requiredCapabilities: List<String>,
    val controlEpoch: Int,
    val leaseExpiresAt: String,
    val mediaDeliveryId: String?,
    val legacyStepsEnabled: Boolean,
    val parameters: JSONObject,
)

object CommandV1Parser {
    const val PROTOCOL = "cloudctl.command/v1"
    const val UNSUPPORTED_PROTOCOL = "UNSUPPORTED_PROTOCOL"
    const val UNSUPPORTED_RECIPE = "UNSUPPORTED_RECIPE"
    private val idPattern = Regex("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    private val shaPattern = Regex("^[a-f0-9]{64}$")
    private val commandTypes = setOf(
        "xianyu.publish_listing.v1",
        "xianyu.collect_orders.v1",
        "xiaohongshu.publish_note.v1",
        "device.probe_capabilities.v1",
    )
    private val packages = mapOf(
        "xianyu.publish_listing.v1" to "com.taobao.idlefish",
        "xianyu.collect_orders.v1" to "com.taobao.idlefish",
        "xiaohongshu.publish_note.v1" to "com.xingin.xhs",
    )
    private val forbidden = listOf("shell", "dex", "js", "javascript", "frida", "argv", "payload", "script", "bytecode")
    private val requiredKeys = setOf(
        "protocolVersion",
        "taskId",
        "attemptId",
        "commandType",
        "deviceId",
        "accountId",
        "bindingVersion",
        "snapshot",
        "recipe",
        "targetPackage",
        "requiredCapabilities",
        "lease",
        "parameters",
    )

    fun parse(encoded: String): CommandV1 {
        val root = JSONObject(encoded)
        rejectForbidden(root)
        val keys = root.keys().asSequence().toSet()
        val optional = setOf("mediaDeliveryId", "legacyStepsEnabled")
        require(keys.containsAll(requiredKeys)) { UNSUPPORTED_PROTOCOL }
        require(keys.all { it in requiredKeys + optional }) { "Unknown command field" }
        val protocol = root.getString("protocolVersion")
        require(protocol == PROTOCOL) { UNSUPPORTED_PROTOCOL }
        val commandType = root.getString("commandType")
        require(commandType in commandTypes) { UNSUPPORTED_PROTOCOL }
        val targetPackage = root.getString("targetPackage")
        val expectedPackage = packages[commandType]
        if (expectedPackage != null) {
            require(targetPackage == expectedPackage) { "targetPackage does not match commandType" }
        }
        val snapshot = root.getJSONObject("snapshot")
        val recipe = root.getJSONObject("recipe")
        val lease = root.getJSONObject("lease")
        requireKeys(snapshot, setOf("id", "sha256"))
        requireKeys(recipe, setOf("versionId", "sha256", "engineMinVersion"))
        requireKeys(lease, setOf("controlEpoch", "expiresAt"))
        val engineMinVersion = recipe.getInt("engineMinVersion")
        require(engineMinVersion >= 1) { UNSUPPORTED_RECIPE }
        return CommandV1(
            protocolVersion = protocol,
            taskId = id(root.getString("taskId")),
            attemptId = id(root.getString("attemptId")),
            commandType = commandType,
            deviceId = id(root.getString("deviceId")),
            accountId = id(root.getString("accountId")),
            bindingVersion = root.getInt("bindingVersion").also { require(it >= 1) },
            snapshotId = id(snapshot.getString("id")),
            snapshotSha256 = sha(snapshot.getString("sha256")),
            recipeVersionId = id(recipe.getString("versionId")),
            recipeSha256 = sha(recipe.getString("sha256")),
            engineMinVersion = engineMinVersion,
            targetPackage = targetPackage,
            requiredCapabilities = capabilities(root),
            controlEpoch = lease.getInt("controlEpoch").also { require(it >= 1) },
            leaseExpiresAt = lease.getString("expiresAt"),
            mediaDeliveryId = root.optString("mediaDeliveryId").takeIf(String::isNotBlank)?.let(::id),
            legacyStepsEnabled = root.optBoolean("legacyStepsEnabled", false),
            parameters = root.getJSONObject("parameters"),
        )
    }

    private fun capabilities(root: JSONObject): List<String> {
        val values = root.getJSONArray("requiredCapabilities")
        return List(values.length()) { values.getString(it) }
    }

    private fun rejectForbidden(value: JSONObject) {
        value.keys().asSequence().forEach { key ->
            val lowered = key.lowercase()
            require(forbidden.none { it in lowered }) { "command contains unauthorized execution fields" }
            val child = value.opt(key)
            if (child is JSONObject) rejectForbidden(child)
        }
    }

    private fun requireKeys(value: JSONObject, expected: Set<String>) {
        require(value.keys().asSequence().toSet() == expected) { "Unknown or missing command field" }
    }

    private fun id(value: String): String = value.also { require(idPattern.matches(it)) { "identity field is invalid" } }
    private fun sha(value: String): String = value.also { require(shaPattern.matches(it)) { "sha256 is invalid" } }
}
