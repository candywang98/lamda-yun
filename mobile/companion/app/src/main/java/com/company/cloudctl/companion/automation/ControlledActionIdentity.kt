package com.company.cloudctl.companion.automation

import org.json.JSONObject
import java.security.MessageDigest

/** Immutable identity from the persisted CommandV1 and its verified recipe pin. */
data class ControlledActionIdentity(
    val taskId: String,
    val deviceId: String,
    val accountId: String,
    val bindingVersion: Int,
    val commandType: String,
    val recipeVersionId: String,
    val recipeSha256: String,
    val snapshotSha256: String,
    val actionId: String,
) {
    init {
        listOf(taskId, deviceId, accountId, commandType, recipeVersionId, actionId).forEach {
            require(Regex("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}").matches(it)) { "Invalid action identity field" }
        }
        require(bindingVersion > 0)
        listOf(recipeSha256, snapshotSha256).forEach { require(Regex("[a-f0-9]{64}").matches(it)) }
    }

    val actionKey: String get() = digest("cloudctl.action/v1\n$taskId\n$recipeSha256\n$actionId")
    val parameterHash: String get() = digest(
        "cloudctl.action-parameters/v1\n$taskId\n$commandType\n$accountId\n$bindingVersion\n$snapshotSha256\n$recipeSha256",
    )

    fun toJson(): JSONObject = JSONObject()
        .put("taskId", taskId).put("deviceId", deviceId).put("accountId", accountId)
        .put("bindingVersion", bindingVersion).put("commandType", commandType)
        .put("recipeVersionId", recipeVersionId).put("recipeSha256", recipeSha256)
        .put("snapshotSha256", snapshotSha256).put("actionId", actionId)

    companion object {
        fun from(command: CommandV1, actionId: String) = ControlledActionIdentity(
            command.taskId, command.deviceId, command.accountId, command.bindingVersion,
            command.commandType, command.recipeVersionId, command.recipeSha256, command.snapshotSha256, actionId,
        )

        fun fromJson(json: JSONObject) = ControlledActionIdentity(
            json.getString("taskId"), json.getString("deviceId"), json.getString("accountId"),
            json.getInt("bindingVersion"), json.getString("commandType"), json.getString("recipeVersionId"),
            json.getString("recipeSha256"), json.getString("snapshotSha256"), json.getString("actionId"),
        )

        private fun digest(value: String): String = MessageDigest.getInstance("SHA-256")
            .digest(value.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    }
}
