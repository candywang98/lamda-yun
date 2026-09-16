package com.company.cloudctl.companion.device

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * B11 验收（fleet-identity/v1 §2/§3）：online 与 executable 分离、维度分开
 * 上报；输入（IME）与无障碍未就绪时不领取需要它们的任务。
 */
class ClaimEligibilityPolicyTest {
    private fun readySnapshot(
        transportOnline: Boolean = true,
        accessibilityEnabled: Boolean = true,
        accessibilityActive: Boolean = true,
        imeReady: Boolean = true,
        screenUnlocked: Boolean = true,
        engineVersion: Int = ClaimEligibilityPolicy.ENGINE_FLOOR,
    ) = RuntimeReadinessSnapshot(
        transportOnline = transportOnline,
        accessibilityEnabled = accessibilityEnabled,
        accessibilityActive = accessibilityActive,
        imeReady = imeReady,
        screenUnlocked = screenUnlocked,
        engineVersion = engineVersion,
        observedAtEpochMillis = 0L,
    )

    @Test
    fun `fully ready device is executable and may claim`() {
        val snapshot = readySnapshot()
        assertTrue(ClaimEligibilityPolicy.executable(snapshot))
        assertEquals(
            ClaimEligibility.Eligible,
            ClaimEligibilityPolicy.shouldClaim(snapshot, setOf(RequiredCapability.ACCESSIBILITY, RequiredCapability.IME)),
        )
    }

    @Test
    fun `transport offline is ineligible even when everything else is ready`() {
        val snapshot = readySnapshot(transportOnline = false)
        assertFalse(ClaimEligibilityPolicy.executable(snapshot))
        assertEquals(
            "TRANSPORT_OFFLINE",
            (ClaimEligibilityPolicy.shouldClaim(snapshot, setOf(RequiredCapability.ACCESSIBILITY)) as ClaimEligibility.Ineligible).reasonCode,
        )
    }

    @Test
    fun `enabled and active are separate dimensions with separate codes`() {
        val disabled = readySnapshot(accessibilityEnabled = false, accessibilityActive = false)
        assertEquals(
            "ACCESSIBILITY_NOT_ENABLED",
            (ClaimEligibilityPolicy.shouldClaim(disabled, setOf(RequiredCapability.ACCESSIBILITY)) as ClaimEligibility.Ineligible).reasonCode,
        )
        // 已启用但未激活（重绑瞬态/绑定未完成）：单独的状态与单独的错误码。
        val inactive = readySnapshot(accessibilityEnabled = true, accessibilityActive = false)
        assertEquals(
            "ACCESSIBILITY_NOT_ACTIVE",
            (ClaimEligibilityPolicy.shouldClaim(inactive, setOf(RequiredCapability.ACCESSIBILITY)) as ClaimEligibility.Ineligible).reasonCode,
        )
    }

    @Test
    fun `ime not ready only blocks tasks that need ime`() {
        val snapshot = readySnapshot(imeReady = false)
        assertEquals(
            "IME_NOT_READY",
            (ClaimEligibilityPolicy.shouldClaim(snapshot, setOf(RequiredCapability.IME)) as ClaimEligibility.Ineligible).reasonCode,
        )
        // §3 能力求交：纯监听任务不需要 IME，不被其拖累（锁屏门另测）。
        assertEquals(
            ClaimEligibility.Eligible,
            ClaimEligibilityPolicy.shouldClaim(snapshot, setOf(RequiredCapability.IM_LISTEN)),
        )
    }

    @Test
    fun `locked screen blocks claiming for every task family`() {
        val snapshot = readySnapshot(screenUnlocked = false)
        assertFalse(ClaimEligibilityPolicy.executable(snapshot))
        for (requires in listOf(
            setOf(RequiredCapability.ACCESSIBILITY),
            setOf(RequiredCapability.IM_LISTEN),
            emptySet(),
        )) {
            assertEquals(
                "SCREEN_LOCKED",
                (ClaimEligibilityPolicy.shouldClaim(snapshot, requires) as ClaimEligibility.Ineligible).reasonCode,
            )
        }
    }

    @Test
    fun `engine below the required floor is ineligible`() {
        val snapshot = readySnapshot(engineVersion = ClaimEligibilityPolicy.ENGINE_FLOOR - 1)
        assertEquals(
            "ENGINE_BELOW_MIN",
            (ClaimEligibilityPolicy.shouldClaim(snapshot, emptySet()) as ClaimEligibility.Ineligible).reasonCode,
        )
        assertEquals(
            ClaimEligibility.Eligible,
            ClaimEligibilityPolicy.shouldClaim(
                readySnapshot(engineVersion = 2),
                emptySet(),
                requiredEngine = 2,
            ),
        )
    }

    @Test
    fun `executable false implies claim ineligible`() {
        for (snapshot in listOf(
            readySnapshot(transportOnline = false),
            readySnapshot(accessibilityEnabled = false),
            readySnapshot(accessibilityActive = false),
            readySnapshot(imeReady = false),
            readySnapshot(screenUnlocked = false),
            readySnapshot(engineVersion = 0),
        )) {
            assertFalse(ClaimEligibilityPolicy.executable(snapshot))
            assertIs<ClaimEligibility.Ineligible>(
                ClaimEligibilityPolicy.shouldClaim(snapshot, RequiredCapability.entries.toSet()),
            )
        }
    }
}
