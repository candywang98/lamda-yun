# B14 输入通道升级：软件语义验收清单

日期：2026-09-22（Asia/Shanghai）

本清单冻结 C3 前的软件语义门。构建通过不能替代以下逐项检查；真机仍属于
`blocked_hardware`，不在本清单内。

- API 33–35：无障碍编辑连接未绑定时失败关闭，绝不临时切走搜狗/讯飞。
- API 30–32：CloudCtl Input 仅在一次写入或一次发送前只读复验期间临时选中；精确恢复原 IME；用户手工改选第三方 IME 时保留用户选择。
- API 29：CloudCtl Input 未被用户手工选为当前输入法时返回 `INPUT_IME_REQUIRED`。
- 聊天写入：空框最多 commit 一次；已等于期望只读验证；非空不同草稿返回 `FIELD_DIRTY_BY_USER`。
- 发送证明：绑定 taskId、授权 peer/会话、目标包、定位器、稳定字段锚点、编辑器字段身份、完整文本和单调 TTL。
- 发送顺序：发送动作前重新验证会话和完整字段文本，并先消费 proof；tap 成功、失败或结果未知都不能复用同一 proof。
- API 30–32 发送前复验：临时重绑定后的 generation 可以更新，但公开字段 fingerprint 必须一致，且新 generation 内两次完整读回稳定；随后恢复原 IME。
- 字段锚点：不得以 `AccessibilityNodeInfo` 包装对象 identity/hash 作为跨解析身份；同字段的新包装对象应通过，不同窗口/位置/字段应拒绝。
- API 33 完整读回：offset=0、未撞 10001 窗口、密码和组合态拒绝、IPC 返回后复核 generation/字段身份、两次稳定读。
- 描述：不使用剪贴板、长按粘贴或整页可见文本授权；数字描述仍走文本通道。
- 价格：只有 `xianyu_price` 走九键；仅目标价格表单金额 token 的数值等价可通过；`10199` 不能满足 `199`，页面其他位置的 `199` 不能授权价格成功。
- 既有评价流程：受保护语义改动仍存在，相关测试不回退。
- 软件门禁：聚焦测试、全量 JVM、lint、debug APK、androidTest APK、plan_guard、`git diff --check` 全部通过。

只有独立只读验收逐项确认且无软件阻断，才记录 C3“模块通过”；D 列仍不得写“验收通过”。
