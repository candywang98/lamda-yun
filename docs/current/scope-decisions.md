# 范围与决策记录（scope-decisions）

由 R00 建立，2026-09-16。后续决策只追加条目并注明任务ID，不改写历史条目。

## 已冻结主线决策（沿用交付包 00 指令，用户已批准）

| 决策 | 内容 | 状态 |
|---|---|---|
| D-1 | 保留 CloudCtl 云端 + Kotlin Companion（`mobile/companion`），生产不换 Auto.js；E10 仅可选对照实验，默认不启动 | 冻结 |
| D-2 | 自有 IME（CloudCtl Input）；签名 Recipe；持久动作台账（action ledger） | 冻结 |
| D-3 | 不重写整套工程、不引入第二业务队列、不为了多智能体重建已有工作树 | 冻结 |
| D-4 | PostgreSQL 为业务事实源；Temporal 为执行历史；Edge SQLite 仅 spool（仓库 AGENTS 不变量5） | 冻结 |
| D-5 | V1 平台范围恰为四个：闲鱼商品、小红书图文、抖音视频、微信公众号文章 | 冻结 |

## 本机核对新增事实（R00）

- HEAD `4af3698` 与交付包审计基线完全一致，无差额重放问题；脏文件仅 2 个未跟踪项（yuyou-assistant-qa.md 待 R01 登记、.gradle 构建缓存）。
- 首尔 mobile-api 实际运行 `a11-9c53cc7`，与 HEAD 的 3 个落后提交均非后端功能差额。
- 设备 b0644fb5 安装的 APK 与本地构建哈希一致（2391f380…），versionCode=1 / 0.1.0。
- 旧表所记 23 棵工作树：现存活树 6 棵，其余已归档于 `Desktop/LAMDA云控系统/worktree-遗物归档-20260916/`；后续任务不得重建等价树。

## 冲突登记（源材料优先级）

1. 规范规则冲突 → 以当前已批准契约（contracts/）为准。
2. 代码说明实际实现；验收报告只说明特定环境的测试结果。
3. 旧 APK 仅提供静态参考，不作为行为权威。
4. Excel 进度文字不得覆盖安全门（删除/发布/发送/消耗仍走独立授权门）。

## 待决事项（不阻塞 W0/W1）

- 抖音 / 公众号 / 小红书视频范围的旧表冲突细节：R02 导入两份旧 Excel 全表后逐条登记到 01 报告附录，再逐项裁决。
- P09 三条未合入硬化分支（agent/p09-*）与 HEAD 的 diff 差额：由对应 P09 续做任务核对，不在本轮重写。
- 第 3 次删除 UNKNOWN/KEEP_WAITING 挂起：按 `delete-automation-issue-handoff.md` 独立通道处理，未授权不重试。

## 专家评审采纳记录（2026-09-17，用户提供外部专家全文）

| 决策 | 内容 | 状态 |
|---|---|---|
| D-6 | P0=生产身份D路径(nginx BasicAuth→服务端principal映射) + 控制面独立于claim；P1=禁force-stop入SOP+能力探测；P2=EMUI注入按provisioning兼容处理+语义能力矩阵 | 已采纳@c55da0d |
| D-7 | 死锁修复协议：heartbeat watermark + /control 游标 + reconcile-snapshot 兜底 + 服务器 humanConfirmDeadline 权威解除；**放弃本地超时自动跳过PAUSED**；SUSPECT_ORPHANED 仅告警 | 已采纳（K14/A14/B17） |
| D-8 | force-stop 禁用无障碍为 **AOSP 通用行为**（AccessibilityManagerService force-stop handler），非 ColorOS 特有 → 生产 SOP 禁止 `am force-stop` Companion；升级用 install -r 后验证绑定 | 已采纳，SOP 修订随 B17 |
| D-9 | Flutter 无障碍树**不按 Android API level 分档**；测试矩阵主键 = OEM/build × API × 目标App versionCode × 语义能力指纹；resource-id 为 capability-discovered selector | 已采纳（K11 后续增补 geometryEpoch） |
| D-10 | 身份切换顺序：服务端映射→uvicorn 仅 loopback（现状已满足）→production+bypass 启动 fatal（settings.py:80 已存在）→切 env→BasicAuth+映射跑稳→Authelia/Dex OIDC→Vue BFF 会话；静态 JWT 仅 break-glass | 已采纳（A14 落地 D 路径） |

核查记录：OnePlus 7 的 permission_monitor 相关 settings 键均为 null（该开关需 UI 操作，保留 P2 待办）；settings.py:80 已含 production+bypass fatal 校验；uvicorn 已仅监听 127.0.0.1。
