package com.company.cloudctl.companion.operations

/**
 * User-facing operation metadata. The executor is intentionally separate so a
 * placeholder can be replaced by a native or LAMDA-backed implementation later.
 */
data class OperationDefinition(
    val key: String,
    val title: String,
    val module: String,
    val description: String,
    val kind: OperationKind = OperationKind.Action,
    val requiresConfirmation: Boolean = false,
)

enum class OperationKind { Action, Toggle }

data class OperationReceipt(
    val id: String,
    val operationKey: String,
    val title: String,
    val module: String,
    val state: String,
    val detail: String,
    val createdAt: String,
)

interface CompanionOperationExecutor {
    suspend fun enqueue(
        definition: OperationDefinition,
        parameters: Map<String, String> = emptyMap(),
    ): OperationReceipt
}

object OperationCatalog {
    val basic = listOf(
        OperationDefinition("queue.clear", "清空队列", "基础功能", "清理尚未执行的本地占位任务", requiresConfirmation = true),
        OperationDefinition("queue.restart", "重启队列", "基础功能", "重新启动本地任务调度器"),
        OperationDefinition("executor.restart", "重启内核", "基础功能", "重启本地执行器；当前仅记录占位操作"),
        OperationDefinition("cache.clear", "清除缓存", "基础功能", "清理 CloudCtl 本地缓存", requiresConfirmation = true),
    )

    val common = listOf(
        OperationDefinition("message.reply", "消息回复（自动回复、聚合聊天）", "常用功能", "消息自动化入口占位", OperationKind.Toggle),
        OperationDefinition("coin.deduct", "鱼币抵扣", "常用功能", "鱼币抵扣入口占位"),
        OperationDefinition("account.bind", "绑定闲鱼", "常用功能", "账号绑定入口占位", requiresConfirmation = true),
        OperationDefinition("coin.checkin", "签到鱼币", "常用功能", "签到入口占位"),
        OperationDefinition("price.lower", "一键降价", "常用功能", "批量调价入口占位", requiresConfirmation = true),
        OperationDefinition("dynamic.delete", "删除动态", "常用功能", "动态清理入口占位", requiresConfirmation = true),
        OperationDefinition("price.bargain", "一键小刀", "常用功能", "议价入口占位"),
        OperationDefinition("review.good", "一键好评", "常用功能", "评价入口占位", requiresConfirmation = true),
        OperationDefinition("message.delete", "删除消息", "常用功能", "消息清理入口占位", requiresConfirmation = true),
        OperationDefinition("message.leave.delete", "删除留言", "常用功能", "留言清理入口占位", requiresConfirmation = true),
        OperationDefinition("product.refresh", "擦亮商品", "常用功能", "商品刷新入口占位"),
        OperationDefinition("product.publish", "上架商品", "常用功能", "向云端申请闲鱼文字发布任务，由本机无障碍填写发布表单", requiresConfirmation = true),
        OperationDefinition("product.unpublish", "下架商品", "常用功能", "商品下架入口占位", requiresConfirmation = true),
        OperationDefinition("product.delete", "删除商品", "常用功能", "商品删除入口占位", requiresConfirmation = true),
        OperationDefinition("product.edit", "快速编辑", "常用功能", "商品编辑入口占位"),
        OperationDefinition("product.republish", "编辑重发", "常用功能", "编辑重发入口占位", requiresConfirmation = true),
        OperationDefinition("orders.sync", "同步订单", "常用功能", "订单同步入口占位"),
        OperationDefinition("product.draft.publish", "草稿上架", "常用功能", "草稿发布入口占位", requiresConfirmation = true),
        OperationDefinition("product.info", "宝贝信息", "常用功能", "商品信息入口占位"),
        OperationDefinition("platform.open", "打开平台", "常用功能", "平台启动入口占位"),
        OperationDefinition("platform.bind", "绑定平台", "常用功能", "平台绑定入口占位", requiresConfirmation = true),
    )

    val marketplace = listOf(
        OperationDefinition("marketplace.refresh", "擦亮商品", "转转功能", "平台商品刷新入口占位"),
        OperationDefinition("marketplace.publish", "上架商品", "转转功能", "平台商品上架入口占位", requiresConfirmation = true),
        OperationDefinition("marketplace.unpublish", "下架商品", "转转功能", "平台商品下架入口占位", requiresConfirmation = true),
        OperationDefinition("marketplace.delete", "删除商品", "转转功能", "平台商品删除入口占位", requiresConfirmation = true),
        OperationDefinition("marketplace.account.bind", "转转养号", "转转功能", "账号养号入口占位"),
        OperationDefinition("marketplace.traffic", "流量模式", "转转功能", "流量模式入口占位"),
        OperationDefinition("marketplace.disabled", "暂无功能", "转转功能", "预留功能入口占位"),
        OperationDefinition("marketplace.start", "启动转转", "转转功能", "平台启动入口占位"),
        OperationDefinition("marketplace.edit", "快速编辑", "转转功能", "平台商品编辑入口占位"),
        OperationDefinition("marketplace.order.sync", "同步订单", "转转功能", "平台订单同步入口占位"),
    )

    val content = listOf(
        OperationDefinition("content.account.create", "红薯养号", "红薯功能", "账号养号入口占位"),
        OperationDefinition("content.account.search", "搜索养号", "红薯功能", "账号搜索入口占位"),
        OperationDefinition("content.note.delete", "删除笔记", "红薯功能", "笔记清理入口占位", requiresConfirmation = true),
        OperationDefinition("content.start", "启动红薯", "红薯功能", "平台启动入口占位"),
        OperationDefinition("content.draft.publish", "草稿上架", "红薯功能", "草稿上架入口占位", requiresConfirmation = true),
        OperationDefinition("content.info", "宝贝信息", "红薯功能", "商品信息入口占位"),
        OperationDefinition("content.search", "搜索任务", "红薯功能", "搜索入口占位"),
        OperationDefinition("content.good.review", "一键好评", "红薯功能", "评价入口占位", requiresConfirmation = true),
    )

    val other = listOf(
        OperationDefinition("platform.start", "启动平台", "其他环境", "目标平台启动入口占位"),
        OperationDefinition("platform.account.bind", "绑定账号", "其他环境", "账号绑定入口占位", requiresConfirmation = true),
        OperationDefinition("platform.search", "搜索任务", "其他环境", "搜索自动化入口占位"),
        OperationDefinition("assets.sync", "同步素材", "其他环境", "素材同步入口占位"),
        OperationDefinition("automation.test", "执行测试", "其他环境", "自动化测试入口占位"),
        OperationDefinition("platform.quick.edit", "快速编辑", "其他环境", "跨平台编辑入口占位"),
        OperationDefinition("platform.quick.unpublish", "快速下架", "其他环境", "跨平台下架入口占位", requiresConfirmation = true),
        OperationDefinition("platform.status", "平台状态", "其他环境", "平台状态检查入口占位"),
        OperationDefinition("evidence.screenshot", "截图测试", "其他环境", "截图证据入口占位"),
    )

    val toggles = listOf(
        OperationDefinition("runtime.background", "程序后台运行", "运行配置", "后台运行配置占位", OperationKind.Toggle),
        OperationDefinition("runtime.autoSync", "自动同步", "运行配置", "自动同步配置占位", OperationKind.Toggle),
        OperationDefinition("runtime.floatingLog", "悬浮运行日志", "运行配置", "悬浮日志配置占位", OperationKind.Toggle),
        OperationDefinition("runtime.autoUpdate", "内核自动更新", "运行配置", "内核更新配置占位", OperationKind.Toggle),
    )
}
