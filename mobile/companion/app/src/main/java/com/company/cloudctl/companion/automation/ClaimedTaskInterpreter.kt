package com.company.cloudctl.companion.automation

import org.json.JSONObject

object ClaimedTaskInterpreter {
    fun commandOrNull(payload: String): CommandV1? {
        val root = JSONObject(payload)
        val nested = root.optJSONObject("command")
        return when {
            nested != null -> CommandV1Parser.parse(nested.toString())
            root.optString("protocolVersion") == CommandV1Parser.PROTOCOL -> CommandV1Parser.parse(payload)
            else -> null
        }
    }

    fun isOpenOnly(command: CommandV1): Boolean = command.commandType in BuiltinRecipes.OPEN_ONLY_COMMAND_TYPES

    fun recipeHash(payload: JSONObject): String {
        val nested = payload.optJSONObject("command")?.optJSONObject("recipe")?.optString("sha256").orEmpty()
        return nested.ifBlank { payload.optString("recipeHash") }
    }

    fun accountId(payload: JSONObject): String {
        val nested = payload.optJSONObject("command")?.optString("accountId").orEmpty()
        return nested.ifBlank { payload.optString("accountId") }
    }

    fun bindingVersion(payload: JSONObject): Int {
        val command = payload.optJSONObject("command")
        if (command != null && command.has("bindingVersion")) return command.getInt("bindingVersion")
        return payload.optInt("bindingVersion", 0)
    }
}
