package com.company.cloudctl.companion.control

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.json.JSONObject

/**
 * Locks the client wire models onto the FROZEN contract fixtures
 * (control-plane/v1@20260917.1, K14 @a560507). The contracts/ tree is on the
 * unit-test classpath via the app source set, so these tests fail the moment
 * a fixture or the parser drifts.
 */
class ControlPlaneModelsTest {
    private fun fixture(name: String): String =
        requireNotNull(javaClass.classLoader.getResourceAsStream("control-plane/v1/fixtures/$name")) {
            "fixture not found: $name"
        }.readBytes().toString(Charsets.UTF_8)

    @Test
    fun `positive control batch parses with monotonic seq and consistent range`() {
        val raw = JSONObject(fixture("k14-positive-control-batch.json"))
        assertEquals("control-plane/v1@20260917.1", raw.getString("contract"))
        val batch = ControlPlaneJson.parseControlBatch(raw.getJSONObject("response").toString())

        assertEquals(1302L, batch.from)
        assertEquals(1307L, batch.through)
        assertEquals(1307L, batch.highWatermark)
        assertEquals(
            listOf("CANCEL", "SET_CONFIRM_DEADLINE", "ABANDON"),
            batch.events.map { it.type.name },
        )
        assertEquals(listOf(1302L, 1305L, 1307L), batch.events.map { it.seq })
        assertEquals(listOf("task-aaa", "task-bbb", "task-ccc"), batch.events.map { it.taskId })
        assertEquals(listOf(41L, 7L, 3L), batch.events.map { it.taskRevision })
        // fixture invariants: from > after(request), through <= highWatermark
        assertTrue(batch.from > raw.getJSONObject("request").getLong("after"))
        assertTrue(batch.through <= batch.highWatermark)
    }

    @Test
    fun `cursor too old fixture maps to 410 CURSOR_TOO_OLD with snapshotRequired`() {
        val raw = JSONObject(fixture("k14-negative-cursor-too-old.json"))
        val expect = raw.getJSONObject("expect")
        val body = JSONObject()
            .put("code", expect.getString("code"))
            .put("snapshotRequired", expect.getBoolean("snapshotRequired"))
            .toString()

        val parsed = ControlPlaneJson.parseCursorTooOld(expect.getInt("status"), body)
        assertNotNull(parsed) { "410 CURSOR_TOO_OLD must map to the snapshot fallback" }
        assertEquals(410, expect.getInt("status"))

        assertNull(ControlPlaneJson.parseCursorTooOld(200, body))
        assertNull(ControlPlaneJson.parseCursorTooOld(410, JSONObject().put("code", "OTHER").toString()))
    }

    @Test
    fun `cancel ack fixture branches map to the two frozen results`() {
        val raw = JSONObject(fixture("k14-positive-cancel-ack.json"))
        val branches = raw.getJSONArray("branches")
        assertEquals("APPLIED", branches.getJSONObject(0).getString("branch"))
        assertEquals("DEFERRED_RECONCILING", branches.getJSONObject(1).getString("branch"))

        val applied = ControlPlaneJson.buildControlAckPayload("task-x", 41, ControlAckResults.CANCEL_APPLIED, null)
        assertEquals("CANCEL_APPLIED", applied.getString("result"))
        val deferred = ControlPlaneJson.buildControlAckPayload(
            "task-x", 41, ControlAckResults.CANCEL_DEFERRED_RECONCILING, "irreversible committed",
        )
        assertEquals("CANCEL_DEFERRED_RECONCILING", deferred.getString("result"))
        assertEquals("irreversible committed", deferred.getString("reason"))
    }

    @Test
    fun `torn batch is rejected instead of applied`() {
        val torn = JSONObject()
            .put("from", 10).put("through", 20).put("highWatermark", 30)
            .put(
                "events",
                org.json.JSONArray()
                    .put(JSONObject().put("seq", 12).put("taskId", "t").put("taskRevision", 1).put("type", "CANCEL"))
                    .put(JSONObject().put("seq", 11).put("taskId", "t").put("taskRevision", 1).put("type", "CANCEL")),
            )
            .toString()
        assertFailsWith<IllegalArgumentException> { ControlPlaneJson.parseControlBatch(torn) }

        val outside = JSONObject()
            .put("from", 10).put("through", 15).put("highWatermark", 30)
            .put(
                "events",
                org.json.JSONArray()
                    .put(JSONObject().put("seq", 99).put("taskId", "t").put("taskRevision", 1).put("type", "CANCEL")),
            )
            .toString()
        assertFailsWith<IllegalArgumentException> { ControlPlaneJson.parseControlBatch(outside) }
    }

    @Test
    fun `reconcile snapshot parses task rows`() {
        val snapshot = ControlPlaneJson.parseReconcileSnapshot(
            JSONObject()
                .put("controlHighWatermark", 1307)
                .put(
                    "tasks",
                    org.json.JSONArray()
                        .put(
                            JSONObject()
                                .put("taskId", "task-aaa")
                                .put("status", "CANCELLED")
                                .put("businessState", "CANCELLED")
                                .put("taskRevision", 42)
                                .put("terminal", true)
                                .put("ledgerBlocks", true),
                        ),
                )
                .toString(),
        )
        assertEquals(1307L, snapshot.controlHighWatermark)
        assertEquals(1, snapshot.tasks.size)
        assertEquals("task-aaa", snapshot.tasks[0].taskId)
        assertTrue(snapshot.tasks[0].terminal)
        assertTrue(snapshot.tasks[0].ledgerBlocks)
    }
}
