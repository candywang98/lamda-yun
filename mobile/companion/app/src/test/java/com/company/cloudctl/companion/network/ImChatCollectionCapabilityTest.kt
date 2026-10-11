package com.company.cloudctl.companion.network

import com.company.cloudctl.companion.im.CollectionFixture
import com.company.cloudctl.companion.im.IM_CHAT_COLLECTION_PROTOCOL
import org.json.JSONObject
import kotlin.test.*

class ImChatCollectionCapabilityTest {
    @Test fun staleCollectionLeaseCannotBeMarkedDelivered() {
        val error = CloudHttpException(409, "mobile task lease expired")
        assertEquals(DeliveryFailureAction.PERMANENT_REJECTION,
            OutboxRetryPolicy.classify(error, "/companion/v2/im/chat-collections/task:complete"))
        assertEquals(DeliveryFailureAction.ACCEPT_AS_DELIVERED,
            OutboxRetryPolicy.classify(error, "/companion/v2/tasks/task/complete"))
    }

    @Test fun advertisesExplicitCapabilityAndDiagnosticClearsIt() {
        val body = addImChatCollectionCapability(JSONObject(), false)
        assertEquals(IM_CHAT_COLLECTION_PROTOCOL, body.getString("imChatCollectionProtocol"))
        assertFalse(addImChatCollectionCapability(body, true).has("imChatCollectionProtocol"))
    }
    @Test fun collectClaimPreservesCloudEpoch() {
        val payload = buildClaimedTaskPayload(CollectionFixture.payload(93))
        assertEquals(93L, payload.getLong("controlEpoch"))
    }
    @Test fun collectClaimMissingEpochIsRejected() {
        val payload = CollectionFixture.payload().apply { remove("controlEpoch") }
        assertFails { buildClaimedTaskPayload(payload) }
    }
}
