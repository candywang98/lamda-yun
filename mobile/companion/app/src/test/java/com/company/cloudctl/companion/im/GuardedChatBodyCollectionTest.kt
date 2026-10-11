package com.company.cloudctl.companion.im

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class GuardedChatBodyCollectionTest {
    private class Page {
        var foreground = true
        var peer: String? = "小白"
        var input = true
        var evidenceAvailable = true
        var evidenceReads = 0
        var reads = 0
        val swipes = mutableListOf<Boolean>()
        val queued = mutableListOf<List<ChatBubble>>()
        var bubbles = listOf(ChatBubble("真实正文", 200f, 300, 80))
        var beforeEvidence: () -> Unit = {}
        var onRead: () -> Unit = {}
        var onSwipe: (Boolean) -> Unit = {}
        var onHasBody: () -> Unit = {}
        val collector = GuardedChatBodyCollection(
            targetForeground = { foreground },
            evidence = {
                evidenceReads++
                beforeEvidence()
                if (evidenceAvailable) ImReplyBoundary.ChatEvidence(peer, input, false) else null
            },
            snapshot = { reads++; onRead(); bubbles },
            swipe = { swipes += it; onSwipe(it) },
        )
        suspend fun collect(limit: Int = 0) = collector.collect(
            peer = "小白",
            maxBackwardSwipes = limit,
            hasBody = { onHasBody(); ChatPageReading.latestInbound(it) != null },
            queue = { queued += it },
        )
    }

    @Test fun rejectsWrongUnknownBlankAndMissingEvidenceBeforeReading() = runBlocking {
        for (name in listOf("大白", null, "", "  ")) {
            val page = Page().apply { peer = name }
            assertFalse(page.collect(3))
            assertEquals(0, page.reads)
            assertTrue(page.swipes.isEmpty())
            assertTrue(page.queued.isEmpty())
        }
        val missing = Page().apply { evidenceAvailable = false }
        assertFalse(missing.collect())
        assertEquals(0, missing.reads)
    }

    @Test fun rejectsMissingInputAndLostForegroundBeforeReading() = runBlocking {
        val input = Page().apply { input = false }
        val foreground = Page().apply { foreground = false }
        for (page in listOf(input, foreground)) {
            assertFalse(page.collect())
            assertEquals(0, page.reads)
        }
    }

    @Test fun checksForegroundAgainAfterEvidenceRead() = runBlocking {
        val page = Page().apply { beforeEvidence = { foreground = false } }
        assertFalse(page.collect())
        assertEquals(0, page.reads)
    }

    @Test fun driftDuringSnapshotDiscardsBodyWithoutNavigation() = runBlocking {
        val page = Page().apply { onRead = { peer = "大白" } }
        assertFalse(page.collect(3))
        assertEquals(1, page.reads)
        assertTrue(page.queued.isEmpty())
        assertTrue(page.swipes.isEmpty())
    }

    @Test fun foregroundLostDuringSnapshotDiscardsBody() = runBlocking {
        val page = Page().apply { onRead = { foreground = false } }
        assertFalse(page.collect())
        assertTrue(page.queued.isEmpty())
    }

    @Test fun driftBeforeScrollStopsWithoutScrolling() = runBlocking {
        val page = Page().apply { bubbles = emptyList(); onHasBody = { peer = "大白" } }
        assertFalse(page.collect(3))
        assertTrue(page.swipes.isEmpty())
        assertTrue(page.queued.isEmpty())
    }

    @Test fun driftDuringBackwardScrollNeverRestoresOtherConversation() = runBlocking {
        val page = Page().apply { bubbles = emptyList(); onSwipe = { peer = "大白" } }
        assertFalse(page.collect(3))
        assertEquals(listOf(true), page.swipes)
        assertEquals(1, page.reads)
        assertTrue(page.queued.isEmpty())
    }

    @Test fun driftDuringScrolledSnapshotNeverRestores() = runBlocking {
        val page = Page().apply {
            bubbles = emptyList()
            onRead = { if (reads == 2) peer = "大白" }
        }
        assertFalse(page.collect(3))
        assertEquals(listOf(true), page.swipes)
        assertTrue(page.queued.isEmpty())
    }

    @Test fun driftDuringRestoreStopsRemainingRestoresAndQueue() = runBlocking {
        val page = Page().apply {
            bubbles = emptyList()
            onSwipe = { backward -> if (!backward) peer = "大白" }
        }
        assertFalse(page.collect(2))
        assertEquals(listOf(true, true, false), page.swipes)
        assertTrue(page.queued.isEmpty())
    }

    @Test fun finalEvidenceCheckPreventsEnqueueAfterBodySelection() = runBlocking {
        val page = Page().apply { onHasBody = { peer = "大白" } }
        assertFalse(page.collect())
        assertEquals(1, page.reads)
        assertTrue(page.queued.isEmpty())
    }

    @Test fun exceptionsAtEvidenceSnapshotAndSwipeFailClosed() = runBlocking {
        val evidence = Page().apply { beforeEvidence = { error("evidence unavailable") } }
        val snapshot = Page().apply { onRead = { error("snapshot unavailable") } }
        val swipe = Page().apply { bubbles = emptyList(); onSwipe = { error("swipe failed") } }
        for (page in listOf(evidence, snapshot, swipe)) {
            assertFalse(page.collect(3))
            assertTrue(page.queued.isEmpty())
            assertTrue(page.swipes.none { !it })
        }
    }

    @Test fun cancellationPropagatesWithoutRestoringOrQueueing() = runBlocking {
        val page = Page().apply { onRead = { throw CancellationException("stop") } }
        assertFailsWith<CancellationException> { page.collect(3) }
        assertTrue(page.swipes.isEmpty())
        assertTrue(page.queued.isEmpty())
    }

    @Test fun noInboundCompletesBoundedReadAndRestoreWithoutQueue() = runBlocking {
        val page = Page().apply { bubbles = emptyList() }
        assertTrue(page.collect(2))
        assertEquals(3, page.reads)
        assertEquals(listOf(true, true, false, false), page.swipes)
        assertTrue(page.queued.isEmpty())
    }

    @Test fun visibleBodyQueuesWithoutScrollAndDoesNotRequireVisibleTriggerEvidence() = runBlocking {
        val page = Page().apply { peer = " 小白 " }
        assertTrue(page.collect(3))
        assertEquals(listOf(page.bubbles), page.queued)
        assertEquals(1, page.reads)
        assertTrue(page.swipes.isEmpty())
    }

    @Test fun hiddenBodyQueuesCapturedBodyAfterSafeRestore() = runBlocking {
        val body = listOf(ChatBubble("之前的正文", 200f, 300, 80))
        val page = Page().apply {
            bubbles = emptyList()
            onSwipe = { backward -> bubbles = if (backward) body else emptyList() }
        }
        assertTrue(page.collect(3))
        assertEquals(listOf(true, false), page.swipes)
        assertEquals(listOf(body), page.queued)
    }
}
