package com.company.cloudctl.companion

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.company.cloudctl.companion.automation.ListingRowParseOutcome
import com.company.cloudctl.companion.automation.ListingReading
import com.company.cloudctl.companion.network.CloudConnection
import com.company.cloudctl.companion.network.CloudTaskClient
import com.company.cloudctl.companion.security.SecretStore
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Test
import org.junit.runner.RunWith

/**
 * P43/P44 calibration push (one-shot): parses the REAL card content-descs
 * captured from the 我发布的 list on THIS device (2026-09-20) and pushes
 * them through the production companion client — the same auth/pin/transport
 * the executor will use. This is the legitimate device-push path, not an
 * adb/DB shortcut.
 */
@RunWith(AndroidJUnit4::class)
class ListingPushInstrumentedTest {
    @Test
    fun pushRealCapturedCards() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val binding = context.getSharedPreferences("cloudctl_binding", android.content.Context.MODE_PRIVATE)
            .getString("binding", null) ?: error("device not enrolled")
        val value = JSONObject(binding)
        val token = SecretStore(context).get("binding_token") ?: error("binding token missing")
        val connection = CloudConnection(
            baseUrl = value.getString("cloudUrl"),
            bearerToken = token,
            certificateSha256 = value.getString("certificateSha256"),
        )
        val client = CloudTaskClient(connection)

        // Real card content-descs from the 2026-09-20 OnePlus 9R dump.
        val cards = listOf(
            "恭喜可托管无忧卖, 托管后预估将在1~3天内卖出\n托管\n降价\n编辑\n诊断\n《小升初新思维作文》个人闲置\n曝光2\n   \n浏览2\n   \n想要0\n¥\n18\n.88",
            "恭喜可托管无忧卖, 托管后预估将在1~3天内卖出\n托管\n降价\n编辑\n诊断\n《漫画好玩的心理学》个人闲置\n曝光0\n   \n浏览7\n   \n想要0\n¥\n18\n.88",
            "恭喜可托管无忧卖, 托管后预估将在1~3天内卖出\n托管\n降价\n编辑\n诊断\n《十万个为什么》个人闲置\n曝光13\n   \n浏览2\n   \n想要0\n¥\n8\n.88",
        )
        val rows = JSONArray()
        for (card in cards) {
            val parsed = ListingReading.parseCard(card)
            check(parsed is ListingRowParseOutcome.Parsed) {
                "fixture card failed to parse: $card"
            }
            parsed as ListingRowParseOutcome.Parsed
            rows.put(
                JSONObject()
                    .put("item_key", parsed.itemKey)
                    .put("title", parsed.title)
                    .put("price_cents", parsed.priceCents)
                    .put("price_text", parsed.priceText)
                    .put("status_text", parsed.statusText)
                    .put("exposure_count", parsed.exposureCount)
                    .put("views_count", parsed.viewsCount)
                    .put("wants_count", parsed.wantsCount),
            )
        }
        val payload = JSONObject()
            .put("schema_version", "listing-collect/20260920.2")
            .put("run_key", "q14-calib-20260920")
            .put("screen", 1)
            .put("collected_at", "2026-09-20T22:30:00+00:00")
            .put("rows", rows)
            .put("partial_rows", 0)
        val response = client.sendListingsScreen(payload)
        println("LISTING_PUSH_RESULT $response")
    }
}
