package com.company.cloudctl.companion.model

/** Stable, non-sensitive reasons; never surface raw HTTP bodies or credentials. */
enum class PresenceIssue(val label: String) {
    WAITING_HEARTBEAT("等待首次云端心跳"),
    SYNC_STARTING("正在连接云端"),
    HEARTBEAT_EXPIRED("超过90秒未确认心跳，请检查连接或同步服务"),
    NETWORK_UNAVAILABLE("当前网络未通过系统联网检测"),
    CONNECTION_FAILED("连接云端失败，正在重试"),
    AUTH_REJECTED("设备认证失败，请检查绑定状态"),
    SERVER_REJECTED("云端请求失败，正在重试"),
    BINDING_MISSING("缺少设备绑定或凭据"),
    SYNC_FAILED("同步异常，正在重试"),
    SERVICE_STOPPED("同步服务已停止"),
}
