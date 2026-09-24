package com.company.cloudctl.companion.im

import com.company.cloudctl.companion.data.ImOutboxStore
import com.company.cloudctl.companion.network.CloudHttpException
import com.company.cloudctl.companion.network.DeliveryFailureAction
import com.company.cloudctl.companion.network.OutboxRetryPolicy
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.time.Instant

/**
 * Drains the persistent IM outbox. Confirm only after the server accepts the
 * row or reports it as a duplicate. Retryable failures keep the row and use
 * [OutboxRetryPolicy]. A permanent 4xx stays queryable and is not retried.
 *
 * [uploadHeld] is the C6 pause: real notifications still enqueue, but this
 * method confirms nothing and uploads nothing.
 */
class ImOutboxDelivery(
    private val store: ImOutboxStore,
    private val sender: (JSONObject) -> JSONObject,
    private val clock: () -> Instant = Instant::now,
) {
    fun deliverOnce(deviceId: String): ImDeliveryReport {
        val now = clock()
        if (deviceId.isBlank()) {
            return ImDeliveryReport(held = store.uploadHeld(), sent = 0, confirmed = 0, retried = 0, permanent = 0)
        }
        store.sealUnbound(deviceId, now)
        if (store.uploadHeld()) {
            Log.i(TAG, "IM_OUTBOX_HOLD")
            return ImDeliveryReport(held = true, sent = 0, confirmed = 0, retried = 0, permanent = 0)
        }
        val batch = store.due(now, ImOutboxStore.BATCH_LIMIT, deviceId)
        if (batch.isEmpty()) {
            return ImDeliveryReport(held = false, sent = 0, confirmed = 0, retried = 0, permanent = 0)
        }
        val payload = JSONObject().put(
            "messages",
            JSONArray().apply { batch.forEach { put(it.toUploadJson()) } },
        )
        return try {
            val response = sender(payload)
            val accepted = response.optInt("accepted", -1)
            val duplicates = response.optInt("duplicates", -1)
            val accounted = if (response.has("accepted") && response.has("duplicates") && accepted >= 0 && duplicates >= 0) {
                accepted + duplicates
            } else {
                -1
            }
            // Confirm only when every row is accepted or an explicit duplicate.
            // An empty body, accepted=0, or a partial count leaves the batch
            // unconfirmed and retries it. There is no per-row id to confirm a subset.
            if (accounted != batch.size) {
                return retryAll(batch, "IM_OUTBOX_UNACCOUNTED", now)
            }
            val confirmed = batch.count { store.confirm(it.id, now) }
            ImDeliveryReport(
                held = false,
                sent = batch.size,
                confirmed = confirmed,
                retried = 0,
                permanent = 0,
                accepted = accepted,
                duplicates = duplicates,
            )
        } catch (error: CloudHttpException) {
            classify(batch, error, now)
        } catch (error: IOException) {
            retryAll(batch, error.javaClass.simpleName, now)
        }
    }

    private fun classify(batch: List<ImInboundEvent>, error: CloudHttpException, now: Instant): ImDeliveryReport {
        return when (OutboxRetryPolicy.classify(error)) {
            // Task-lease acknowledgements are not acknowledgements for IM rows.
            DeliveryFailureAction.ACCEPT_AS_DELIVERED,
            DeliveryFailureAction.PERMANENT_REJECTION -> {
                val code = "HTTP_${error.status}"
                batch.forEach { store.markPermanent(it.id, code, now) }
                ImDeliveryReport(held = false, sent = batch.size, confirmed = 0, retried = 0, permanent = batch.size)
            }
            DeliveryFailureAction.RETRY -> retryAll(batch, "HTTP_${error.status}", now)
        }
    }

    private fun retryAll(batch: List<ImInboundEvent>, error: String, now: Instant): ImDeliveryReport {
        batch.forEach { row ->
            store.recordRetry(
                row.id,
                error,
                OutboxRetryPolicy.nextAttemptAt(row.id, row.attemptCount + 1, now),
            )
        }
        return ImDeliveryReport(held = false, sent = batch.size, confirmed = 0, retried = batch.size, permanent = 0)
    }
}

private const val TAG = "ImOutbox"

data class ImDeliveryReport(
    val held: Boolean,
    val sent: Int,
    val confirmed: Int,
    val retried: Int,
    val permanent: Int,
    val accepted: Int = 0,
    val duplicates: Int = 0,
)
