package com.company.cloudctl.companion.features.xianyu.orders

import com.company.cloudctl.companion.automation.OrderDirection
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * O10 验收用例（Android 侧）——断点续传与账号+版本绑定：
 * A 设备订单断点不归 B 账号；版本升级作废旧断点；run 切换只许开新采集；
 * 断网重放的旧屏不改断点；编码 fail-closed。
 */
class OrderCheckpointTest {
    private fun checkpoint(
        account: String = "xianyu-alpha",
        version: Int = 1,
        device: String = "device-A",
        direction: OrderDirection = OrderDirection.SOLD,
        run: String = "run-20260917-a",
        lastScreen: Int = 2,
        seenKeys: Int = 5,
    ) = OrderCheckpoint(account, version, device, direction, run, lastScreen, seenKeys)

    @Test
    fun fullyMatchingIdentityResumes() {
        val result = checkpoint().bindsTo("xianyu-alpha", 1, "device-A", OrderDirection.SOLD, "run-20260917-a")
        assertIs<OrderCheckpoint.BindResult.Resume>(result)
    }

    @Test
    fun deviceACheckpointRefusesDeviceBAndAccountB() {
        // A 设备订单不归 B 账号：账号不匹配拒绝恢复。
        val accountMismatch = checkpoint().bindsTo("xianyu-beta", 1, "device-A", OrderDirection.SOLD, "run-20260917-a")
        assertEquals(
            OrderCheckpoint.REASON_ACCOUNT_MISMATCH,
            assertIs<OrderCheckpoint.BindResult.Refused>(accountMismatch).reason,
        )
        // 设备不匹配同样拒绝。
        val deviceMismatch = checkpoint().bindsTo("xianyu-alpha", 1, "device-B", OrderDirection.SOLD, "run-20260917-a")
        assertEquals(
            OrderCheckpoint.REASON_DEVICE_MISMATCH,
            assertIs<OrderCheckpoint.BindResult.Refused>(deviceMismatch).reason,
        )
    }

    @Test
    fun versionBumpInvalidatesOldCheckpoint() {
        val result = checkpoint().bindsTo("xianyu-alpha", 2, "device-A", OrderDirection.SOLD, "run-20260917-a")
        assertEquals(
            OrderCheckpoint.REASON_VERSION_MISMATCH,
            assertIs<OrderCheckpoint.BindResult.Refused>(result).reason,
        )
    }

    @Test
    fun directionAndRunSwitchAreRefusedForResume() {
        val direction = checkpoint().bindsTo("xianyu-alpha", 1, "device-A", OrderDirection.BOUGHT, "run-20260917-a")
        assertEquals(
            OrderCheckpoint.REASON_DIRECTION_MISMATCH,
            assertIs<OrderCheckpoint.BindResult.Refused>(direction).reason,
        )
        // 四元组匹配但 runKey 不同：允许开新采集，不允许当断点续传。
        val run = checkpoint().bindsTo("xianyu-alpha", 1, "device-A", OrderDirection.SOLD, "run-20260917-b")
        assertEquals(
            OrderCheckpoint.REASON_RUN_SWITCHED,
            assertIs<OrderCheckpoint.BindResult.Refused>(run).reason,
        )
    }

    @Test
    fun advanceOnlyMovesForwardAndOfflineReplayKeepsCheckpoint() {
        val base = checkpoint(lastScreen = 2, seenKeys = 5)
        // 断网重传：第 2 屏重放不前进、不重复计键。
        assertEquals(base, base.advance(screen = 2, newKeys = 3))
        assertEquals(base, base.advance(screen = 1, newKeys = 3))
        // 前进：第 3 屏 +4 键。
        val advanced = base.advance(screen = 3, newKeys = 4)
        assertEquals(3, advanced.lastScreen)
        assertEquals(9, advanced.seenKeyCount)
        // 不可变：原断点不变。
        assertEquals(2, base.lastScreen)
        assertEquals(5, base.seenKeyCount)
    }

    @Test
    fun encodeDecodeRoundTripAndGarbageFailsClosed() {
        val cp = checkpoint()
        assertEquals(cp, OrderCheckpoint.decode(cp.encode()))
        // 账号/键里的分隔符敏感字符不影响编码。
        val tricky = OrderCheckpoint("xianyu|甲", 3, "device-A", OrderDirection.BOUGHT, "run|键", 3, 12)
        assertEquals(tricky, OrderCheckpoint.decode(tricky.encode()))
        // 解不开 → null：空串、垃圾、格式标记不对、屏号越界。
        assertNull(OrderCheckpoint.decode(""))
        assertNull(OrderCheckpoint.decode("garbage"))
        assertNull(OrderCheckpoint.decode(OrderPageCursor("r", OrderDirection.SOLD, 1, listOf("k")).encode()))
        assertNull(OrderCheckpoint.decode(encodeControlSeparated(OrderCheckpoint.FORMAT, "acc", "1", "dev", "SOLD", "run", "0", "1")))
        assertNull(OrderCheckpoint.decode(encodeControlSeparated(OrderCheckpoint.FORMAT, "acc", "1", "dev", "SOLD", "run", "99", "1")))
    }

    @Test
    fun accountBindingComposesWithSeenRegistryFlow() {
        // 端到端口径：A 账号采集 2 屏后断网，B 账号想带着 A 的断点续传 → 拒绝；
        // 拒绝后正确处置是开新 run（screen=1）。
        val registry = OrderSeenRegistry()
        val page1 = registry.absorbPage(1, listOf(snapshot("SOLD|买家A|闲置键盘|2500")))
        val page2 = registry.absorbPage(2, listOf(snapshot("SOLD|买家B|闲置鼠标|3000")))
        val checkpointA = checkpoint(lastScreen = 2, seenKeys = page1.newRows.size + page2.newRows.size)
        val resumeAsB = checkpointA.bindsTo("xianyu-beta", 1, "device-A", OrderDirection.SOLD, "run-20260917-a")
        assertTrue(resumeAsB is OrderCheckpoint.BindResult.Refused)
        // 新 run 的断点从第 1 屏起步。
        val freshRun = checkpoint(account = "xianyu-beta", run = "run-20260917-b", lastScreen = 1, seenKeys = 1)
        assertEquals(1, freshRun.lastScreen)
    }

    private fun snapshot(key: String) = com.company.cloudctl.companion.automation.OrderRowSnapshot(
        direction = OrderDirection.SOLD,
        orderKey = key,
    )
}
