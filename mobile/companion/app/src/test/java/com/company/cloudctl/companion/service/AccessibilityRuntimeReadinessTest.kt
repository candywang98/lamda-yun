package com.company.cloudctl.companion.service

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertSame

class AccessibilityRuntimeReadinessTest {
    @Test
    fun `capture gates claim without sleeping`() = runBlocking {
        val service = Any()
        val sleeps = mutableListOf<Long>()
        var enabled = true
        var active: Any? = null
        val waiter = waiter(
            enabled = { enabled },
            active = { active },
            sleep = { sleeps += it },
        )

        assertSame(AccessibilityRuntimeReadiness.NotActive, waiter.capture())
        active = service
        val ready = assertIs<AccessibilityRuntimeReadiness.Ready<Any>>(waiter.capture())
        assertSame(service, ready.service)
        enabled = false
        assertSame(AccessibilityRuntimeReadiness.NotEnabled, waiter.capture())
        assertEquals(emptyList(), sleeps)
    }

    @Test
    fun `capture rejects a changing runtime instance`() {
        val first = Any()
        val second = Any()
        var activeReads = 0

        val result = waiter(
            active = {
                activeReads++
                if (activeReads == 1) first else second
            },
        ).capture()

        assertSame(AccessibilityRuntimeReadiness.NotActive, result)
        assertEquals(2, activeReads)
    }

    @Test
    fun `disabled setting fails immediately without reading runtime state`() = runBlocking {
        var activeReads = 0
        val sleeps = mutableListOf<Long>()

        val result = waiter(
            enabled = { false },
            active = {
                activeReads++
                Any()
            },
            sleep = { sleeps += it },
        ).await()

        assertSame(AccessibilityRuntimeReadiness.NotEnabled, result)
        assertEquals(0, activeReads)
        assertEquals(emptyList(), sleeps)
    }

    @Test
    fun `already active returns the single captured instance without waiting`() = runBlocking {
        val first = Any()
        var activeReads = 0
        val sleeps = mutableListOf<Long>()

        val result = waiter(
            active = {
                activeReads++
                first
            },
            sleep = { sleeps += it },
        ).await()

        val ready = assertIs<AccessibilityRuntimeReadiness.Ready<Any>>(result)
        assertSame(first, ready.service)
        assertEquals(2, activeReads)
        assertEquals(emptyList(), sleeps)
    }

    @Test
    fun `enabled setting waits within the budget and returns the captured service`() = runBlocking {
        val service = Any()
        var activeReads = 0
        val sleeps = mutableListOf<Long>()

        val result = waiter(
            timeoutMillis = 1_000,
            pollIntervalMillis = 400,
            active = {
                activeReads++
                service.takeIf { activeReads >= 3 }
            },
            sleep = { sleeps += it },
        ).await()

        val ready = assertIs<AccessibilityRuntimeReadiness.Ready<Any>>(result)
        assertSame(service, ready.service)
        assertEquals(4, activeReads)
        assertEquals(listOf(400L, 400L), sleeps)
    }

    @Test
    fun `enabled setting times out using the bounded logical budget`() = runBlocking {
        var activeReads = 0
        val sleeps = mutableListOf<Long>()

        val result = waiter(
            timeoutMillis = 1_000,
            pollIntervalMillis = 400,
            active = {
                activeReads++
                null
            },
            sleep = { sleeps += it },
        ).await()

        assertSame(AccessibilityRuntimeReadiness.NotActive, result)
        assertEquals(4, activeReads)
        assertEquals(listOf(400L, 400L, 200L), sleeps)
        assertEquals(1_000L, sleeps.sum())
    }

    @Test
    fun `cancellation during wait propagates without another active read`() = runBlocking {
        var activeReads = 0

        assertFailsWith<CancellationException> {
            waiter(
                active = {
                    activeReads++
                    null
                },
                sleep = { throw CancellationException("cancelled") },
            ).await()
        }
        assertEquals(1, activeReads)
    }

    private fun waiter(
        timeoutMillis: Long = 1_000,
        pollIntervalMillis: Long = 100,
        enabled: () -> Boolean = { true },
        active: () -> Any? = { null },
        sleep: suspend (Long) -> Unit = {},
    ) = AccessibilityRuntimeReadinessWaiter(
        timeoutMillis = timeoutMillis,
        pollIntervalMillis = pollIntervalMillis,
        isEnabled = enabled,
        activeService = active,
        sleep = sleep,
    )
}
