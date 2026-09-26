package com.company.cloudctl.companion.service

import com.company.cloudctl.companion.features.xianyu.orders.orderAwareCommandOrNull
import com.company.cloudctl.companion.features.xianyu.orders.parseOrderAwareTask
import com.company.cloudctl.companion.network.ClaimedTask

internal fun acceptedClaimDeviceId(claimed: ClaimedTask, configuredDeviceId: String): String {
    val command = orderAwareCommandOrNull(claimed.taskPayload)
    val deviceId = command?.deviceId ?: parseOrderAwareTask(claimed.taskPayload).deviceId
    require(deviceId == configuredDeviceId && claimed.deviceId == configuredDeviceId) {
        "Task belongs to another device"
    }
    return deviceId
}
