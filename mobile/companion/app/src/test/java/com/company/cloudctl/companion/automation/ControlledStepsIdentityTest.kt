package com.company.cloudctl.companion.automation

import org.json.JSONObject
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

class ControlledStepsIdentityTest {
    private fun golden(): JSONObject {
        val stream = javaClass.classLoader!!.getResourceAsStream("steps-identity-golden.json")!!
        return JSONObject(stream.readBytes().decodeToString())
    }

    private fun payload(golden: JSONObject): JSONObject = JSONObject()
        .put("taskId", golden.getString("taskId"))
        .put("deviceId", golden.getString("deviceId"))
        .put("targetPackage", "com.taobao.idlefish")
        .put("steps", golden.getJSONArray("steps"))

    @Test
    fun matchesServerGoldenDigestAndKeys() {
        val golden = golden()
        val identity = ControlledActionIdentity.fromStepsPayload(payload(golden))
        assertEquals(golden.getString("stepsSha256"), identity.recipeSha256)
        assertEquals(golden.getString("stepsSha256"), identity.snapshotSha256)
        assertEquals(golden.getString("actionKey"), identity.actionKey)
        assertEquals(golden.getString("parameterHash"), identity.parameterHash)
        assertEquals("click-publish", identity.actionId)
        assertEquals("xianyu.publish_listing.steps.v1", identity.commandType)
        assertEquals(golden.getInt("bindingVersion"), identity.bindingVersion)
    }

    @Test
    fun keyOrderAndExtraFieldsDoNotChangeIdentity() {
        val golden = golden()
        val reordered = JSONObject(payload(golden).toString())
        val steps = reordered.getJSONArray("steps")
        // Rebuild each step with reversed key insertion order plus an unrelated top-level field.
        for (index in 0 until steps.length()) {
            val step = steps.getJSONObject(index)
            val copy = JSONObject()
            step.keys().asSequence().toList().reversed().forEach { copy.put(it, step.get(it)) }
            steps.put(index, copy)
        }
        reordered.put("issuedAt", "2026-09-13T00:00:00Z")
        val identity = ControlledActionIdentity.fromStepsPayload(payload(golden))
        assertEquals(identity.actionKey, ControlledActionIdentity.fromStepsPayload(reordered).actionKey)
    }

    @Test
    fun changedStepContentIsADifferentAction() {
        val golden = golden()
        val changed = payload(golden)
        val steps = org.json.JSONArray(changed.getJSONArray("steps").toString())
        steps.getJSONObject(1).put("value", "Different frozen description")
        changed.put("steps", steps)
        val identity = ControlledActionIdentity.fromStepsPayload(payload(golden))
        val other = ControlledActionIdentity.fromStepsPayload(changed)
        assertNotEquals(identity.actionKey, other.actionKey)
        assertNotEquals(identity.parameterHash, other.parameterHash)
        assertTrue(other.recipeSha256.matches(Regex("[a-f0-9]{64}")))
    }
}
