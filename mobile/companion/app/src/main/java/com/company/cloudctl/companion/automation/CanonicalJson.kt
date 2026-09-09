package com.company.cloudctl.companion.automation

import org.json.JSONArray
import org.json.JSONObject

object CanonicalJson {
    fun dumps(value: Any?): String = buildString { write(value) }

    fun recipeHashPayload(root: JSONObject): ByteArray {
        val manifest = JSONObject(root.getJSONObject("manifest").toString())
        manifest.remove("hash")
        val body = JSONObject()
            .put("apiVersion", root.getString("apiVersion"))
            .put("kind", root.getString("kind"))
            .put("manifest", manifest)
            .put("graph", root.getJSONObject("graph"))
        return dumps(body).toByteArray(Charsets.UTF_8)
    }

    private fun StringBuilder.write(value: Any?) {
        when (value) {
            null, JSONObject.NULL -> append("null")
            is Boolean -> append(value)
            is Int, is Long, is Short -> append(value.toString())
            is Double -> append(if (value % 1.0 == 0.0 && value in -1e15..1e15) value.toLong().toString() else value.toString())
            is Float -> write(value.toDouble())
            is Number -> append(value.toString())
            is String -> append(quote(value))
            is JSONObject -> {
                append('{')
                val keys = value.keys().asSequence().sorted().toList()
                keys.forEachIndexed { index, key ->
                    if (index > 0) append(',')
                    append(quote(key))
                    append(':')
                    write(value.get(key))
                }
                append('}')
            }
            is JSONArray -> {
                append('[')
                for (index in 0 until value.length()) {
                    if (index > 0) append(',')
                    write(value.get(index))
                }
                append(']')
            }
            else -> error("unsupported canonical json value ${value::class.java.name}")
        }
    }

    private fun quote(value: String): String = buildString {
        append('"')
        value.forEach { ch ->
            when (ch) {
                '\\' -> append("\\\\")
                '"' -> append("\\\"")
                '\b' -> append("\\b")
                '\u000c' -> append("\\f")
                '\n' -> append("\\n")
                '\r' -> append("\\r")
                '\t' -> append("\\t")
                else -> if (ch.code < 0x20) append("\\u%04x".format(ch.code)) else append(ch)
            }
        }
        append('"')
    }
}
