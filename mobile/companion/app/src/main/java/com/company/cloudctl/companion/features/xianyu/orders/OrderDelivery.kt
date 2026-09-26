package com.company.cloudctl.companion.features.xianyu.orders

import com.company.cloudctl.companion.automation.AutomationStep
import com.company.cloudctl.companion.automation.AutomationTask
import com.company.cloudctl.companion.automation.AutomationTaskParser
import com.company.cloudctl.companion.automation.CanonicalJson
import com.company.cloudctl.companion.automation.ClaimedTaskInterpreter
import com.company.cloudctl.companion.automation.CommandV1
import com.company.cloudctl.companion.automation.OrderDirection
import com.company.cloudctl.companion.automation.OrderRowParseOutcome
import com.company.cloudctl.companion.automation.OrderRowParser
import com.company.cloudctl.companion.automation.OrderRowSnapshot
import com.company.cloudctl.companion.automation.SkippedOrderRow
import com.company.cloudctl.companion.automation.toSnapshot
import com.company.cloudctl.companion.network.CloudConnection
import com.company.cloudctl.companion.network.buildOrdersScreenPayload
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest

const val ORDER_DELIVERY_PROTOCOL = "order-delivery/1"

fun orderAwareCommandOrNull(encoded: String): CommandV1? {
    val root = JSONObject(encoded)
    if (root.has("orderDelivery")) {
        require(!root.has("command") && root.getString("protocolVersion") == "cloudctl.mobile/v1") {
            "ORDER_DELIVERY_TASK_SHAPE_REJECTED"
        }
        return null
    }
    return ClaimedTaskInterpreter.commandOrNull(encoded)
}

/** Keep the strict legacy task parser unchanged; validate the opt-in sidecar separately. */
fun parseOrderAwareTask(encoded: String): AutomationTask {
    require(encoded.toByteArray(Charsets.UTF_8).size <= 256 * 1024)
    val original = JSONObject(encoded)
    if (!original.has("orderDelivery")) return AutomationTaskParser.parse(encoded)
    val legacy = JSONObject(encoded).apply { remove("orderDelivery") }
    return AutomationTaskParser.parse(legacy.toString()).also {
        checkNotNull(OrderDeliveryIdentity.fromTask(original, it))
    }
}

fun orderPayloadHash(text: String): String = MessageDigest.getInstance("SHA-256")
    .digest(text.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }

fun orderConnectionScope(connection: CloudConnection, deviceId: String): String =
    orderPayloadHash(JSONArray(listOf(
        connection.baseUrl.trimEnd('/'), connection.certificateSha256, deviceId, connection.bearerToken,
    )).toString())

data class OrderDeliveryIdentity(
    val taskId: String,
    val deviceId: String,
    val accountId: String,
    val bindingVersion: Int,
    val mobileBindingId: String,
    val direction: OrderDirection,
    val maxScreens: Int,
    val definitionHash: String,
) {
    fun encode(): String = JSONObject()
        .put("taskId", taskId).put("deviceId", deviceId).put("accountId", accountId)
        .put("bindingVersion", bindingVersion).put("mobileBindingId", mobileBindingId)
        .put("direction", direction.name).put("maxScreens", maxScreens)
        .put("definitionHash", definitionHash).toString()

    companion object {
        fun fromTask(payload: JSONObject, task: AutomationTask): OrderDeliveryIdentity? {
            if (!payload.has("orderDelivery")) return null
            val delivery = payload.getJSONObject("orderDelivery")
            require(delivery.getString("protocolVersion") == ORDER_DELIVERY_PROTOCOL)
            val account = payload.getString("accountId")
            val binding = payload.getInt("bindingVersion")
            val mobile = delivery.getString("mobileBindingId")
            val direction = OrderDirection.valueOf(delivery.getString("direction"))
            val max = delivery.getInt("maxScreens")
            require(account.isNotBlank() && account.length <= 128 && binding > 0 && mobile.isNotBlank())
            require(task.taskId.isNotBlank() && task.taskId.length <= 128 && task.deviceId.isNotBlank())
            require(task.targetPackage == "com.taobao.idlefish" && max in 1..3)
            val reads = task.steps.filterIsInstance<AutomationStep.ReadOrders>()
            require(reads.size == max && reads.all { it.direction == direction })
            val definition = JSONObject().put("steps", payload.getJSONArray("steps"))
                .put("targetPackage", task.targetPackage)
            return OrderDeliveryIdentity(
                task.taskId, task.deviceId, account, binding, mobile, direction, max,
                orderPayloadHash(CanonicalJson.dumps(definition)),
            )
        }

        fun decode(text: String): OrderDeliveryIdentity {
            val v = JSONObject(text)
            return OrderDeliveryIdentity(
                v.getString("taskId"), v.getString("deviceId"), v.getString("accountId"),
                v.getInt("bindingVersion"), v.getString("mobileBindingId"),
                OrderDirection.valueOf(v.getString("direction")), v.getInt("maxScreens"),
                v.getString("definitionHash"),
            )
        }
    }
}

/** Raw visible rows are local recovery evidence; HTTP payload bytes are saved separately. */
data class SavedOrderRead(
    val screen: Int,
    val stepId: String,
    val stepIndex: Int,
    val collectedAt: String,
    val rawRows: List<List<String>>,
) {
    fun parsed(direction: OrderDirection): Pair<List<OrderRowSnapshot>, List<SkippedOrderRow>> {
        val rows = mutableListOf<OrderRowSnapshot>()
        val skipped = mutableListOf<SkippedOrderRow>()
        rawRows.forEachIndexed { index, lines ->
            when (val parsed = OrderRowParser.parse(direction, lines)) {
                is OrderRowParseOutcome.Parsed -> rows += parsed.toSnapshot(direction, lines)
                is OrderRowParseOutcome.Skipped -> skipped += SkippedOrderRow(index, parsed.reason)
            }
        }
        return rows to skipped
    }

    fun payload(identity: OrderDeliveryIdentity): String {
        val rows = parsed(identity.direction).first
        return buildOrdersScreenPayload(
            identity.taskId, identity.accountId, 1, identity.direction, screen, rows,
            rows.withIndex().filter { it.value.isPartiallyVisible() }.map { it.index }, collectedAt,
        ).toString()
    }

    fun encode(): String {
        val value = JSONObject().put("screen", screen).put("stepId", stepId)
            .put("stepIndex", stepIndex).put("collectedAt", collectedAt)
            .put("rawRows", JSONArray(rawRows.map { JSONArray(it) }))
        return value.put("recoveryHash", orderPayloadHash(CanonicalJson.dumps(value))).toString()
    }

    companion object {
        fun decode(text: String): SavedOrderRead {
            val value = JSONObject(text)
            val hash = value.getString("recoveryHash")
            value.remove("recoveryHash")
            check(orderPayloadHash(CanonicalJson.dumps(value)) == hash) { "ORDER_RECOVERY_CORRUPT" }
            val rows = value.getJSONArray("rawRows")
            return SavedOrderRead(
                value.getInt("screen"), value.getString("stepId"), value.getInt("stepIndex"),
                value.getString("collectedAt"),
                (0 until rows.length()).map { index ->
                    val row = rows.getJSONArray(index)
                    (0 until row.length()).map(row::getString)
                },
            )
        }
    }
}

data class OrderResumeState(
    val reads: List<SavedOrderRead>,
    val lastStepIndex: Int,
    val inFlightStepIndex: Int?,
    val stopReason: String?,
)

class OrderDeliverySession(
    val identity: OrderDeliveryIdentity,
    val restored: OrderResumeState,
    val commitRead: (SavedOrderRead) -> Unit,
    val recordStop: (String) -> Unit,
)

data class PendingOrderDelivery(
    val id: Long,
    val taskId: String,
    val kind: String,
    val screen: Int,
    val payloadJson: String,
    val payloadSha256: String,
    val attemptCount: Int,
) {
    fun envelope(): JSONObject = JSONObject()
        .put("protocolVersion", ORDER_DELIVERY_PROTOCOL).put("taskId", taskId)
        .put("kind", kind).put("screen", screen)
        .put("payloadJson", payloadJson).put("payloadSha256", payloadSha256)

    fun confirms(ack: JSONObject): Boolean =
        ack.opt("protocolVersion") == ORDER_DELIVERY_PROTOCOL &&
            ack.opt("taskId") == taskId && ack.opt("kind") == kind &&
            ack.opt("screen") == screen && ack.opt("payloadSha256") == payloadSha256 &&
            ack.opt("accepted") == true && ack.opt("replayed") is Boolean
}
