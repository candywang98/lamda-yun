package com.company.cloudctl.companion.features.xianyu.orders

import com.company.cloudctl.companion.automation.OrderDirection

/**
 * O10 断点续传绑定（任务卡 §2）：断点与 账号 + 版本 绑定——A 设备的订单断点
 * 不允许 B 账号恢复（换了登录账号 = 换了数据主体，必须开新 run，从第 1 屏重来，
 * 绝不把 A 账号已见集合套在 B 账号的列表上）。
 *
 * 绑定四元组：accountKey（页面账号身份）+ schemaVersion（采集协议版本，升版后
 * 旧断点作废）+ deviceKey（设备）+ direction（SOLD/BOUGHT 是两个独立列表）。
 * runKey 标识采集批次：同绑定不同 runKey 是「新一批采集」，可以开始，但不能当
 * 断点续传用。
 *
 * 编码复用 OrderPagination.kt 的控制分隔 + Base64 方案；解不开 → null（fail-closed）。
 */
data class OrderCheckpoint(
    val accountKey: String,
    val schemaVersion: Int,
    val deviceKey: String,
    val direction: OrderDirection,
    val runKey: String,
    val lastScreen: Int,
    val seenKeyCount: Int,
) {
    /** 断点恢复裁决：只有四元组 + runKey 全匹配才允许 Resume。 */
    fun bindsTo(
        accountKey: String,
        schemaVersion: Int,
        deviceKey: String,
        direction: OrderDirection,
        runKey: String,
    ): BindResult {
        return when {
            this.accountKey != accountKey -> BindResult.Refused(REASON_ACCOUNT_MISMATCH)
            this.schemaVersion != schemaVersion -> BindResult.Refused(REASON_VERSION_MISMATCH)
            this.deviceKey != deviceKey -> BindResult.Refused(REASON_DEVICE_MISMATCH)
            this.direction != direction -> BindResult.Refused(REASON_DIRECTION_MISMATCH)
            this.runKey != runKey -> BindResult.Refused(REASON_RUN_SWITCHED)
            else -> BindResult.Resume
        }
    }

    /**
     * 断点前进：只在 screen > lastScreen 时前进（断网重传的旧屏重放不改断点），
     * seenKeyCount 累加该屏新键。返回新断点，本对象不可变。
     */
    fun advance(screen: Int, newKeys: Int): OrderCheckpoint {
        require(screen >= 1) { "screen is 1-based" }
        require(newKeys >= 0) { "newKeys must not be negative" }
        if (screen <= lastScreen) return this
        return OrderCheckpoint(
            accountKey = accountKey,
            schemaVersion = schemaVersion,
            deviceKey = deviceKey,
            direction = direction,
            runKey = runKey,
            lastScreen = screen,
            seenKeyCount = seenKeyCount + newKeys,
        )
    }

    fun encode(): String = encodeControlSeparated(
        FORMAT,
        accountKey,
        schemaVersion.toString(),
        deviceKey,
        direction.name,
        runKey,
        lastScreen.toString(),
        seenKeyCount.toString(),
    )

    sealed interface BindResult {
        data object Resume : BindResult

        /** reason 为稳定机器码；A 设备订单不归 B 账号 = [REASON_ACCOUNT_MISMATCH]。 */
        data class Refused(val reason: String) : BindResult
    }

    companion object {
        const val FORMAT = "o10cp1"

        /** 恢复方账号与断点账号不同——数据主体变了，禁止恢复。 */
        const val REASON_ACCOUNT_MISMATCH = "ACCOUNT_MISMATCH"

        /** 采集协议版本变了——旧断点的语义不可信，禁止恢复。 */
        const val REASON_VERSION_MISMATCH = "VERSION_MISMATCH"

        /** 设备变了。 */
        const val REASON_DEVICE_MISMATCH = "DEVICE_MISMATCH"

        /** 方向变了（SOLD/BOUGHT 是两个列表，断点不通用）。 */
        const val REASON_DIRECTION_MISMATCH = "DIRECTION_MISMATCH"

        /** 四元组匹配但 runKey 不同：允许开新采集，不允许当断点续传。 */
        const val REASON_RUN_SWITCHED = "RUN_SWITCHED"

        /** 解不开（格式/版本/方向/计数非法）→ null，fail-closed 从第 1 屏重来。 */
        fun decode(raw: String): OrderCheckpoint? {
            val parts = decodeControlSeparated(raw, expectedParts = 8) ?: return null
            if (parts[0] != FORMAT) return null
            val accountKey = parts[1]
            if (accountKey.isEmpty()) return null
            val schemaVersion = parts[2].toIntOrNull() ?: return null
            if (schemaVersion < 1) return null
            val deviceKey = parts[3]
            if (deviceKey.isEmpty()) return null
            val direction = runCatching { OrderDirection.valueOf(parts[4]) }.getOrNull() ?: return null
            val runKey = parts[5]
            if (runKey.isEmpty()) return null
            val lastScreen = parts[6].toIntOrNull() ?: return null
            val seenKeyCount = parts[7].toIntOrNull() ?: return null
            if (lastScreen < 1 || seenKeyCount < 0) return null
            if (lastScreen > OrderScrollPolicy.MAX_SCREENS) return null
            return OrderCheckpoint(
                accountKey = accountKey,
                schemaVersion = schemaVersion,
                deviceKey = deviceKey,
                direction = direction,
                runKey = runKey,
                lastScreen = lastScreen,
                seenKeyCount = seenKeyCount,
            )
        }
    }
}
