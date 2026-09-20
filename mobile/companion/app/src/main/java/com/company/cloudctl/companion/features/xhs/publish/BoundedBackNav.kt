package com.company.cloudctl.companion.features.xhs.publish

/**
 * F14 任务卡 §1：有界返回导航——「无界 back」禁止。
 *
 * 每次返回都必须带步骤证据（当前页 locator 命中）；超过预算即以
 * NAV_BOUNDED_EXIT 有界退出，不继续盲按 back。
 */
class BoundedBackNav(
    private val maxBacks: Int = 3,
    private val backsUsed: Int = 0,
) {
    init {
        require(maxBacks in 1..10) { "maxBacks must be within 1..10" }
        require(backsUsed in 0..maxBacks) { "backsUsed out of budget" }
    }

    sealed interface Decision {
        /** 允许一次返回：必须附带页面证据后回填 [onBackEvidence]。 */
        data class AllowBack(val remainingAfter: Int) : Decision

        /** 预算耗尽：有界退出（失败可解释，不再 back）。 */
        data class BoundedExit(val reason: String) : Decision
    }

    fun requestBack(): Decision = when {
        backsUsed < maxBacks -> Decision.AllowBack(maxBacks - backsUsed - 1)
        else -> Decision.BoundedExit("NAV_BOUNDED_EXIT: back 预算 $maxBacks 已耗尽")
    }

    /** 返回后的页面证据：命中预期 locator 才记一次成功返回。 */
    fun onBackEvidence(expectedLocatorHit: Boolean): BoundedBackNav =
        if (expectedLocatorHit) BoundedBackNav(maxBacks, backsUsed + 1) else this

    fun backsUsed(): Int = backsUsed
}
