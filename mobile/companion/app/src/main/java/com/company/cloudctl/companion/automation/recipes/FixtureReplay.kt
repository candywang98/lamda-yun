package com.company.cloudctl.companion.automation.recipes

import com.company.cloudctl.companion.automation.LocalAutomationUi
import com.company.cloudctl.companion.automation.LocalNodeState
import com.company.cloudctl.companion.automation.LogLevel
import com.company.cloudctl.companion.automation.ScreenshotEvidence
import org.json.JSONArray
import org.json.JSONObject

/**
 * B16 offline replay: a scripted LocalAutomationUi driven by a fixture file.
 * No device, no adb — a fixture lists page frames; each tap advances to the
 * next frame, inspect() resolves the current frame's nodes. This is the
 * recipe developer loop: write template -> compile -> replay against a
 * fixture -> assert the journal.
 *
 * Fixture format (cloudctl.recipe-fixture/v1):
 *   { "fixtureId": "...", "targetPackage": "...",
 *     "frames": [ { "digest": "home", "nodes": {"locator": [visible, enabled, text]} }, ... ] }
 */
class FixtureReplay(
    private val targetPackage: String,
    frames: List<Frame>,
) : LocalAutomationUi {
    data class Frame(val digest: String, val nodes: Map<String, LocalNodeState>)

    val taps = mutableListOf<String>()
    val texts = mutableListOf<Pair<String, String>>()
    val logs = mutableListOf<String>()
    private var cursor = 0

    private val frame: Frame
        get() = framesInternal[minOf(cursor, framesInternal.size - 1)]

    private val framesInternal = frames.toList()

    override fun ensureReady(targetPackage: String) {
        require(targetPackage == this.targetPackage) { "fixture is scripted for ${this.targetPackage}" }
    }

    override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? = frame.nodes[locatorRef]

    override fun pageSummary(targetPackage: String): String = frame.digest

    override suspend fun tap(targetPackage: String, locatorRef: String) {
        taps += locatorRef
        advance()
    }

    override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) {
        texts += locatorRef to value
        advance()
    }

    override suspend fun screenshot(taskId: String, label: String) =
        ScreenshotEvidence(path = "/fixtures/$taskId/$label", size = 1L, sha256 = "a".repeat(64))

    override fun log(level: LogLevel, messageCode: String) {
        logs += "${level.name}:$messageCode"
    }

    private fun advance() {
        if (cursor < framesInternal.size - 1) cursor += 1
    }

    companion object {
        fun parse(encoded: String): FixtureReplay {
            val root = JSONObject(encoded)
            require(root.getString("protocol") == "cloudctl.recipe-fixture/v1") { "fixture protocol mismatch" }
            val target = root.getString("targetPackage")
            val framesJson: JSONArray = root.getJSONArray("frames")
            require(framesJson.length() in 1..256) { "fixture frame count is invalid" }
            val frames = (0 until framesJson.length()).map { index ->
                val item = framesJson.getJSONObject(index)
                val nodesJson = item.optJSONObject("nodes") ?: JSONObject()
                val nodes = mutableMapOf<String, LocalNodeState>()
                nodesJson.keys().forEach { locator ->
                    val spec = nodesJson.getJSONArray(locator)
                    nodes[locator] = LocalNodeState(
                        enabled = if (spec.length() > 1) spec.getBoolean(1) else true,
                        visible = spec.getBoolean(0),
                        clickable = true,
                        editable = true,
                        text = if (spec.length() > 2 && !spec.isNull(2)) spec.getString(2) else null,
                    )
                }
                Frame(digest = item.optString("digest").ifBlank { "frame-$index" }, nodes = nodes)
            }
            return FixtureReplay(target, frames)
        }

        /** Fixture factory for tests that script frames inline. */
        fun of(targetPackage: String, vararg frames: Frame): FixtureReplay = FixtureReplay(targetPackage, frames.toList())
    }
}
