package com.company.cloudctl.companion.data

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.model.ArtifactDeliveryState
import com.company.cloudctl.companion.model.ArtifactDeliveryStatus
import com.company.cloudctl.companion.model.ArtifactKind
import kotlin.test.Test
import kotlin.test.assertEquals
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class ArtifactDeliveryStoreTest {
    @Test
    fun persistsAndReplacesDeliveryStatusByArtifactId() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        context.getSharedPreferences("cloudctl_artifact_deliveries", Context.MODE_PRIVATE).edit().clear().commit()
        val store = ArtifactDeliveryStore(context)
        store.upsert(ArtifactDeliveryStatus("asset-1", "delivery-1", ArtifactKind.Media, ArtifactDeliveryState.Downloading, 4, 10, 40))
        store.upsert(ArtifactDeliveryStatus("asset-1", "delivery-1", ArtifactKind.Media, ArtifactDeliveryState.Delivered, 10, 10, 100))
        store.upsert(ArtifactDeliveryStatus("asset-1", "delivery-2", ArtifactKind.Media, ArtifactDeliveryState.Queued, 0, 10, 0))

        val status = store.snapshot().first { it.deliveryId == "delivery-1" }
        assertEquals(ArtifactDeliveryState.Delivered, status.state)
        assertEquals(100, status.progressPercent)
        assertEquals(10, status.bytesReceived)
        assertEquals(2, store.snapshot().size)
    }
}
