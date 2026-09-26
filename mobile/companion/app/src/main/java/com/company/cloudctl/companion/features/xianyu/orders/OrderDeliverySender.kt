package com.company.cloudctl.companion.features.xianyu.orders

import com.company.cloudctl.companion.data.AutomationStore
import com.company.cloudctl.companion.network.CloudHttpException
import kotlinx.coroutines.CancellationException
import org.json.JSONObject
import java.time.Instant

/** One due head per run per pass; no device UI, execution lease or legacy event policy. */
class OrderDeliverySender(
    private val store: AutomationStore,
    private val now: () -> Instant = Instant::now,
) {
    suspend fun flush(connectionScope: String, send: suspend (JSONObject) -> JSONObject) {
        for (record in store.dueOrderDeliveries(connectionScope, now())) {
            if (orderPayloadHash(record.payloadJson) != record.payloadSha256) {
                defer(record, "BLOCKED", "PAYLOAD_CORRUPT")
                continue
            }
            try {
                val ack = send(record.envelope())
                if (record.confirms(ack)) store.acknowledgeOrderDelivery(record)
                else defer(record, "PENDING", "ACK_UNCONFIRMED")
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: CloudHttpException) {
                val state = when {
                    error.status == 401 || error.status == 403 -> "AUTH_REQUIRED"
                    error.status == 429 || error.status in 500..599 -> "PENDING"
                    error.status in 400..499 -> "BLOCKED"
                    else -> "PENDING"
                }
                defer(record, state, "HTTP_${error.status}")
            } catch (_: Exception) {
                defer(record, "PENDING", "TRANSPORT_UNCONFIRMED")
            }
        }
    }

    private fun defer(record: PendingOrderDelivery, state: String, code: String) {
        val seconds = (5L shl record.attemptCount.coerceIn(0, 8)).coerceAtMost(300L)
        store.deferOrderDelivery(record, state, code, now().plusSeconds(seconds))
    }
}
