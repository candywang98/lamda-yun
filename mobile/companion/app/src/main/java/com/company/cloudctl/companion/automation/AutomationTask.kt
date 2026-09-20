package com.company.cloudctl.companion.automation

import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

data class AutomationTask(
    val taskId: String,
    val deviceId: String,
    val targetPackage: String,
    val issuedAt: Instant,
    val expiresAt: Instant,
    val maxRunSeconds: Int,
    val steps: List<AutomationStep>,
)

sealed interface AutomationStep {
    val stepId: String
    val timeoutMs: Long

    data class Find(override val stepId: String, override val timeoutMs: Long, val locatorRef: String) : AutomationStep
    data class TapText(override val stepId: String, override val timeoutMs: Long, val value: String) : AutomationStep
    data class Tap(
        override val stepId: String,
        override val timeoutMs: Long,
        val locatorRef: String,
        val postconditionLocatorRef: String?,
    ) : AutomationStep
    data class Input(
        override val stepId: String,
        override val timeoutMs: Long,
        val locatorRef: String,
        val value: String,
        val sensitive: Boolean,
    ) : AutomationStep
    data class Wait(
        override val stepId: String,
        override val timeoutMs: Long,
        val locatorRef: String,
        val condition: NodeCondition,
        val pollMs: Long,
    ) : AutomationStep
    data class Screenshot(override val stepId: String, override val timeoutMs: Long, val label: String) : AutomationStep
    data class Assert(
        override val stepId: String,
        override val timeoutMs: Long,
        val locatorRef: String,
        val predicate: NodeCondition,
    ) : AutomationStep
    data class Log(
        override val stepId: String,
        override val timeoutMs: Long,
        val level: LogLevel,
        val messageCode: String,
    ) : AutomationStep

    /**
     * Structured coordinate tap on the frozen xianyu maintenance layout
     * (contract xianyu-maintenance-anchors-20260915). Coordinates are never
     * supplied by the task: they are derived from the tab, the layout action
     * and the card index under the 1080x2400 resolution guard. [value] is an
     * optional human-readable backup label for evidence only.
     */
    data class TapLayout(
        override val stepId: String,
        override val timeoutMs: Long,
        val tab: XianyuMaintenanceLayout.Tab,
        val layoutAction: XianyuMaintenanceLayout.LayoutAction,
        val cardIndex: Int,
        val value: String?,
    ) : AutomationStep

    /**
     * Badge assertion over a published-goods tab description (「1\n在卖」 → 1).
     * Exactly one of [expectedDelta] (relative to the badge baseline captured
     * at the gated/first strike of the same run) and [expectedValue] (absolute)
     * is set; the contract freezes the signal: 下架成功⇒在卖 N-1, 删除成功⇒已下架 N-1.
     */
    data class AssertBadge(
        override val stepId: String,
        override val timeoutMs: Long,
        val locatorRef: String,
        val expectedDelta: Int?,
        val expectedValue: Int?,
    ) : AutomationStep

    /**
     * Order-sync slice 1 (contract order-sync/20260915.1 §5): reads up to
     * [maxRows] current-screen order rows inside the list container resolved
     * from [locatorRef]. Rows without a parseable order key are skipped
     * (NO_KEY) and never fail the task; short reads and empty lists succeed.
     * The container locator fails closed with LOCATOR_UNVERIFIED while §7
     * keeps it unverified (see TargetLocatorRegistry).
     */
    data class ReadOrders(
        override val stepId: String,
        override val timeoutMs: Long,
        val direction: OrderDirection,
        val maxRows: Int,
        val locatorRef: String,
    ) : AutomationStep

    /**
     * Order-sync slice 2 (contract order-sync-slice2/20260915.1 §1): swipe up
     * one screen strictly inside the bounds of the node resolved from
     * [locatorRef] — the xianyu orders list container (xianyu-anchors §3).
     * A full-screen swipe is forbidden: it would drag the bottom tab bar and
     * the top banners. The step body carries exactly the slice1 parameter
     * set (locatorRef); the screen ordinal lives only in runtime logs, never
     * in the hashed step fields (exact key-set parsing enforces that).
     */
    data class SwipeUp(
        override val stepId: String,
        override val timeoutMs: Long,
        val locatorRef: String,
    ) : AutomationStep

    /**
     * W4 maintenance v2 (contract xianyu-anchors-20260915 §1/§2): locate the
     * published-list card whose text contains [titleContains] on the [tab]
     * list and tap its bounds center to enter the detail page. The card is
     * the ancestor block holding the title text; zero or several matching
     * cards fail the step with CARD_TITLE_NOT_FOUND / CARD_TITLE_AMBIGUOUS
     * before any gesture (zero side effects). Card heights are uneven, so no
     * cardIndex→y formula is ever used here.
     */
    data class TapCardByTitle(
        override val stepId: String,
        override val timeoutMs: Long,
        val tab: XianyuMaintenanceLayout.Tab,
        val titleContains: String,
    ) : AutomationStep

    /**
     * xy-tasks-24 listing collection (listing-collect/20260920.2): run the
     * whole read-only loop on the 在卖 tab of 我发布的 — popup dismissal,
     * per-screen card reads, semantic scrolling and the
     * 「所有宝贝加载完成」 end anchor, with per-screen pushes through the
     * listings reporter. The only gestures are popup dismiss and the list's
     * own scroll action; a card tap never happens.
     */
    /** P35 标准权限软重启：CLEAR_TASK 重建目标 App 根任务（非 force-stop）。 */
    data class AppRestart(
        override val stepId: String,
        override val timeoutMs: Long,
    ) : AutomationStep

    data class CollectListings(
        override val stepId: String,
        override val timeoutMs: Long,
        val maxScreens: Int,
    ) : AutomationStep

    /**
     * P34 auto-review of pending sold orders (xy-review/20260921): run the
     * whole loop on the 待评价 tab of 我卖出的 — per order open the editor by
     * its 「去评价，按钮」 entry, tap the 好评 rating column, fill [comment],
     * capture before/after evidence, then tap 提交评价 — or stop right after
     * the filled-editor screenshot when [dryRun] (the editor is left open,
     * never submitted). The loop ends at [maxOrders], when no 去评价 entry
     * remains, or at the step window edge; zero pending orders is a success.
     */
    data class ReviewOrders(
        override val stepId: String,
        override val timeoutMs: Long,
        val maxOrders: Int,
        val comment: String,
        val dryRun: Boolean,
    ) : AutomationStep
}

enum class NodeCondition { EXISTS, NOT_EXISTS, ENABLED }
enum class LogLevel { DEBUG, INFO, WARN, ERROR }

/** Order-sync slice 1 (contract order-sync/20260915.1 §5): collection direction. */
enum class OrderDirection { SOLD, BOUGHT }

object AutomationTaskParser {
    private val idPattern = Regex("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    private val locatorPattern = Regex("^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    private val messagePattern = Regex("^[A-Z0-9_]{1,80}$")

    /** The only locator refs whose descriptions carry the maintenance badge signal. */
    val BADGE_TAB_LOCATOR_REFS = setOf(
        "xianyu_pub_tab_onsale",
        "xianyu_pub_tab_draft",
        "xianyu_pub_tab_delisted",
    )

    fun parse(encoded: String): AutomationTask {
        require(encoded.toByteArray().size <= 256 * 1024) { "Task payload exceeds limit" }
        val root = JSONObject(encoded)
        requireKeys(
            root,
            setOf("protocolVersion", "taskId", "deviceId", "targetPackage", "issuedAt", "expiresAt", "maxRunSeconds", "steps") +
                optional(root, "mediaDelivery") +
                optional(root, "commandType") +
                optional(root, "accountId") +
                optional(root, "bindingVersion") +
                optional(root, "attemptId") +
                optional(root, "command"),
        )
        if (root.has("mediaDelivery")) {
            require(root.optJSONObject("mediaDelivery") != null) { "Media delivery must be an object" }
            validateMediaDelivery(root.getJSONObject("mediaDelivery"))
        }
        require(root.getString("protocolVersion") == "cloudctl.mobile/v1") { "Unsupported task protocol" }
        val targetPackage = root.getString("targetPackage")
        require(
            targetPackage in setOf(
                TargetLocatorRegistry.COMPANION_PACKAGE,
                TargetLocatorRegistry.XIANYU_PACKAGE,
                TargetLocatorRegistry.XHS_PACKAGE,
                TargetLocatorRegistry.DOUYIN_PACKAGE,
            )
        ) {
            "Tasks must target an allowlisted application"
        }
        val stepsJson = root.getJSONArray("steps")
        require(stepsJson.length() in 1..100) { "Task step count is invalid" }
        val steps = List(stepsJson.length()) { parseStep(stepsJson.getJSONObject(it)) }
        require(steps.map { it.stepId }.toSet().size == steps.size) { "Step IDs must be unique" }
        val issuedAt = Instant.parse(root.getString("issuedAt"))
        val expiresAt = Instant.parse(root.getString("expiresAt"))
        require(expiresAt.isAfter(issuedAt)) { "Task expiry must follow issue time" }
        return AutomationTask(
            taskId = id(root.getString("taskId")),
            deviceId = id(root.getString("deviceId")),
            targetPackage = targetPackage,
            issuedAt = issuedAt,
            expiresAt = expiresAt,
            maxRunSeconds = root.getInt("maxRunSeconds").also { require(it in 1..900) },
            steps = steps,
        )
    }

    private fun parseStep(value: JSONObject): AutomationStep {
        val action = value.getString("action")
        val common = setOf("stepId", "action", "timeoutMs")
        val stepId = id(value.getString("stepId"))
        // collectListings / reviewOrders run the whole multi-screen (or
        // multi-order) loop inside one step, so their window is the task-scale
        // bound (backend schema allows 900s).
        val loopScaleActions = setOf("ui.collectListings", "xianyu.reviewOrders")
        val timeout = value.getLong("timeoutMs").also {
            require(it in 100..if (action in loopScaleActions) 900_000L else 60_000L)
        }
        return when (action) {
            "ui.find" -> AutomationStep.Find(stepId, timeout, locator(value, common + "locatorRef"))
            "ui.tapText" -> {
                val keys = common + setOf("value")
                requireKeys(value, keys)
                val target = value.getString("value")
                require(target.length in 1..64 && '\u0000' !in target) { "tapText value is invalid" }
                AutomationStep.TapText(stepId, timeout, target)
            }
            "ui.tap" -> {
                val keys = common + setOf("locatorRef") + optional(value, "postconditionLocatorRef")
                requireKeys(value, keys)
                AutomationStep.Tap(
                    stepId,
                    timeout,
                    locator(value, keys),
                    optionalString(value, "postconditionLocatorRef")?.let { locatorPattern.requireMatch(it) },
                )
            }
            "ui.input" -> {
                val keys = common + setOf("locatorRef", "value", "replace") + optional(value, "sensitive")
                requireKeys(value, keys)
                require(value.getBoolean("replace")) { "Input must replace existing text" }
                val text = value.getString("value")
                require(text.length <= 1024 && '\u0000' !in text) { "Input value is invalid" }
                AutomationStep.Input(stepId, timeout, locator(value, keys), text, value.optBoolean("sensitive"))
            }
            "ui.wait" -> {
                val keys = common + setOf("locatorRef", "condition", "pollMs")
                requireKeys(value, keys)
                AutomationStep.Wait(
                    stepId, timeout, locator(value, keys),
                    enumValue<NodeCondition>(value.getString("condition")),
                    value.getLong("pollMs").also { require(it in 100..2000) },
                )
            }
            "ui.screenshot" -> {
                val keys = common + "label"
                requireKeys(value, keys)
                val label = value.getString("label")
                require(label.length in 1..80) { "Screenshot label is invalid" }
                AutomationStep.Screenshot(stepId, timeout, label)
            }
            "ui.assert" -> {
                val keys = common + setOf("locatorRef", "predicate")
                requireKeys(value, keys)
                AutomationStep.Assert(stepId, timeout, locator(value, keys), enumValue<NodeCondition>(value.getString("predicate")))
            }
            "ui.tapLayout" -> {
                val keys = common + setOf("layoutAction", "tab", "cardIndex") + optional(value, "value")
                requireKeys(value, keys)
                val layoutAction = layoutActionOf(value.getString("layoutAction"))
                val tab = tabOf(value.getString("tab"))
                val cardIndex = value.getInt("cardIndex").also { require(it in 0..9) { "cardIndex is invalid" } }
                val label = optionalString(value, "value")?.also {
                    require(it.length in 1..80 && '\u0000' !in it) { "tapLayout value is invalid" }
                }
                AutomationStep.TapLayout(stepId, timeout, tab, layoutAction, cardIndex, label)
            }
            "ui.assertBadge" -> {
                val keys = common + setOf("locatorRef") +
                    optional(value, "expectedDelta") + optional(value, "expectedValue")
                requireKeys(value, keys)
                val badgeRef = locator(value, keys)
                require(badgeRef in BADGE_TAB_LOCATOR_REFS) { "assertBadge requires a xianyu published-tab locator" }
                val delta = optionalInt(value, "expectedDelta")?.also { require(it in -50..50) { "expectedDelta is invalid" } }
                val expected = optionalInt(value, "expectedValue")?.also { require(it in 0..9999) { "expectedValue is invalid" } }
                require((delta != null) != (expected != null)) { "assertBadge takes exactly one expected measure" }
                AutomationStep.AssertBadge(stepId, timeout, badgeRef, delta, expected)
            }
            "ui.readOrders" -> {
                val keys = common + setOf("direction", "maxRows", "locatorRef")
                requireKeys(value, keys)
                AutomationStep.ReadOrders(
                    stepId,
                    timeout,
                    enumValue<OrderDirection>(value.getString("direction")),
                    value.getInt("maxRows").also { require(it in 1..10) { "readOrders maxRows is invalid" } },
                    locator(value, keys),
                )
            }
            // Order-sync slice 2 §1: the multi-screen scroll primitive. Key set
            // stays exactly stepId/action/timeoutMs/locatorRef — a step body
            // carrying a "screen" ordinal (or any extra field) is rejected
            // before execution, so screen numbers can never leak into the
            // hashed steps identity.
            "ui.swipeUp" -> {
                val keys = common + "locatorRef"
                requireKeys(value, keys)
                AutomationStep.SwipeUp(stepId, timeout, locator(value, keys))
            }
            "ui.tapCardByTitle" -> {
                val keys = common + setOf("titleContains", "tab")
                requireKeys(value, keys)
                val title = value.getString("titleContains")
                require(title.length in 1..64 && '\u0000' !in title) { "tapCardByTitle titleContains is invalid" }
                val tab = tabOf(value.getString("tab"))
                // 草稿 tab 无已标定卡片（契约 §1：本轮实测为空），标题定位不开放。
                require(tab == XianyuMaintenanceLayout.Tab.ONSALE ||
                    tab == XianyuMaintenanceLayout.Tab.DELISTED) { "tapCardByTitle tab must be onsale or delisted" }
                AutomationStep.TapCardByTitle(stepId, timeout, tab, title)
            }
            "app.restart" -> {
                requireKeys(value, common)
                AutomationStep.AppRestart(stepId, timeout)
            }
            "ui.collectListings" -> {
                val keys = common + setOf("tab", "maxScreens")
                requireKeys(value, keys)
                val tab = tabOf(value.getString("tab"))
                require(tab == XianyuMaintenanceLayout.Tab.ONSALE) { "collectListings tab must be onsale" }
                AutomationStep.CollectListings(
                    stepId,
                    timeout,
                    value.getInt("maxScreens").also { require(it in 1..40) { "collectListings maxScreens is invalid" } },
                )
            }
            "xianyu.reviewOrders" -> {
                val keys = common + setOf("maxOrders", "comment", "dryRun")
                requireKeys(value, keys)
                val comment = value.getString("comment")
                require(comment.length in 1..200 && '\u0000' !in comment) { "reviewOrders comment is invalid" }
                AutomationStep.ReviewOrders(
                    stepId,
                    timeout,
                    value.getInt("maxOrders").also { require(it in 1..50) { "reviewOrders maxOrders is invalid" } },
                    comment,
                    value.getBoolean("dryRun"),
                )
            }
            "run.log" -> {
                val keys = common + setOf("level", "messageCode")
                requireKeys(value, keys)
                AutomationStep.Log(
                    stepId, timeout, enumValue<LogLevel>(value.getString("level")),
                    messagePattern.requireMatch(value.getString("messageCode")),
                )
            }
            else -> error("Unknown action is not permitted")
        }
    }

    private fun layoutActionOf(value: String): XianyuMaintenanceLayout.LayoutAction =
        enumValues<XianyuMaintenanceLayout.LayoutAction>().firstOrNull { it.name.lowercase() == value }
            ?: error("Unsupported layout action")

    private fun tabOf(value: String): XianyuMaintenanceLayout.Tab =
        enumValues<XianyuMaintenanceLayout.Tab>().firstOrNull { it.name.lowercase() == value }
            ?: error("Unsupported layout tab")

    private fun locator(value: JSONObject, keys: Set<String>): String {
        requireKeys(value, keys)
        return locatorPattern.requireMatch(value.getString("locatorRef"))
    }

    private fun id(value: String) = idPattern.requireMatch(value)
    private fun Regex.requireMatch(value: String): String = value.also { require(matches(it)) { "Value violates task contract" } }
    private inline fun <reified T : Enum<T>> enumValue(value: String): T = enumValues<T>().firstOrNull { it.name == value }
        ?: error("Unsupported enum value")
    private fun optional(value: JSONObject, key: String) = if (value.has(key)) setOf(key) else emptySet()

    private fun optionalString(value: JSONObject, key: String): String? {
        if (!value.has(key) || value.isNull(key)) return null
        return value.opt(key) as? String
    }

    private fun optionalInt(value: JSONObject, key: String): Int? {
        if (!value.has(key) || value.isNull(key)) return null
        return value.opt(key) as? Int
    }

    private fun validateMediaDelivery(value: JSONObject) {
        requireKeys(value, setOf("deliveryId", "assetIds"))
        id(value.getString("deliveryId"))
        val assetIds = value.getJSONArray("assetIds")
        require(assetIds.length() in 1..50) { "Media delivery asset count is invalid" }
        val ids = List(assetIds.length()) { index -> id(assetIds.getString(index)) }
        require(ids.toSet().size == ids.size) { "Media delivery asset IDs must be unique" }
    }
    private fun requireKeys(value: JSONObject, expected: Set<String>) {
        require(value.keys().asSequence().toSet() == expected) { "Unknown or missing task field" }
    }
}
