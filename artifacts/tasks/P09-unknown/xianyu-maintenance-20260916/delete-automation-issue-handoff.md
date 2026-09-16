# 问题交接：闲鱼自动删除 happy path 未达成（安全机制已全部验证）— 2026-09-16

> 面向后续接手此问题的模型/智能体。自包含，无需翻会话历史。裁决人：用户（2026-09-16 拍板挂起，转问题清单）。

## 问题一句话

闲鱼已下架商品的**自动化永久删除**三次授权真机尝试均未走通 happy path（目标《如果历史是一群喵4》至今未删），但三道安全机制（对账/单发校验/新鲜度仲裁）各自兑现、全程零误删零副作用。剩余工作是真机参数调优，非架构问题。

## 环境与入口

- 仓库：`/Users/wangziheng/Desktop/LAMDA云控系统/cloudctl-source`，分支 `integration/p14-20260909`（相关提交见下）
- 设备：OnePlus 9R `b0644fb5`（1080x2400, Android 14），闲鱼=com.taobao.idlefish（Flutter）
- API：`https://43.133.243.154.sslip.io`（首尔，已部署 81e24ec）；dev 头 X-Tenant-Id=00000000-0000-7000-8000-000000001111 / X-User-Id=…2206 / X-Roles=device_operator / X-MFA=true
- 删除入口：`POST /api/v1/xianyu/maintenance:run` body `{"deviceId":"4aabc387-6e4b-4b59-a525-b1c119ec7f5b","action":"delete","path":"v2","targets":{"titles":["…"]}}` + Idempotency-Key
- 对账：`POST /api/v1/platform-tasks/{id}:reconcile`（CONFIRMED_APPLIED/CONFIRMED_NOT_SUBMITTED/KEEP_WAITING）
- 红线：真实删除须用户**逐件授权**；UNKNOWN 任务不得重试；GATED/单发语义不可 weakening

## 三次尝试史（证据全在 artifacts/tasks/P09-unknown/xianyu-maintenance-20260916/）

| # | 任务 | 结果 | 根因 | 证据 |
|---|---|---|---|---|
| 1 | a25549e5（昨晚） | UNKNOWN→已结案 NOT_SUBMITTED | 确认击已派发但取证缺失，效果不可证 | final-delete/ + unknown-root-cause-review.md |
| 2 | 16c9c527（今晨） | UNKNOWN→已结案 NOT_SUBMITTED | 滚动后节点 bounds 过期点错卡；单发窗口校验拒发 | final-delete-v2/（含错误商品弹窗铁证 png） |
| 3 | 1ebd70fd（今晨） | FAILED / CARD_BOUNDS_UNVERIFIED（干净终态，门控未开） | **目标卡片完全可见且居首**仍被新鲜度仲裁判 UNVERIFIED——参数过严或 wrapper/卡片节点解析摇摆 | final-delete-v3/（含 ui-after-v3.xml：目标在 [0,345][1080,764] 首位） |

## 已落的修复（都在主线，含单测）

- 单发手势守卫+提交屏障（fc236a2）：at-most-one dispatchGesture、弹窗稳定校验、关联取证落 `files/automation-evidence/`（设备端 run-as 可取）
- 错卡双防线（a322266 / W-A）：
  - 防线1 详情页标题二次校验（DETAIL_TITLE_MISMATCH/DETAIL_TITLE_UNVERIFIED → fail-closed）
  - 防线2 tap 前 bounds 新鲜度仲裁：`BoundsFreshnessArbiter`（150ms settle、40px Chebyshev、2 轮重匹配 → CARD_BOUNDS_UNSTABLE/UNVERIFIED）
  - 代码：`mobile/companion/.../automation/PublishedCardLocator.kt`、`CloudCtlAccessibilityService.kt`（tapCardByTitle 内复核）、`LocalAutomationExecutor.kt`（executeTapCardByTitle）
  - 测试：PublishedCardLocatorTest / TapCardByTitleExecutorTest（417 用例全绿，JVM 层无法复现真机 Flutter 时序）

## 诊断方向（下一步模型从这里开始）

1. **真机日志驱动调参**：settle 150→400ms、容差 40→80px、双读窗口放宽；或卡片节点优先解析（拒绝 wrapper [0,345][1080,2337] vs 卡片 [0,345][1080,764] 的解析摇摆）
2. **用已捕获 XML 做离线回放测试**：final-delete-v3/ui-after-v3.xml、final-delete-v2/*.xml、readonly-preflight/*.xml 都是真实 Flutter 树快照，可直接喂给匹配器做回归——比真机逐次试错便宜
3. **批量调参建议**：请用户一次性授权一批已下架测试商品（已下架 tab 现有喵4/喵13/喵9/喵7/万历五十五年等多件），一轮内多目标试错，避免逐件授权
4. 复验口径：删除成功 ⇔ 已下架 tab 目标消失 + 角标 N-1 + 台账 APPLIED + 操作员 CONFIRMED_APPLIED

## 相关纪律

- repo AGENTS.md（GATED/单发/零重试/逐件授权）；维护锚点契约 contracts/phase1/xianyu-maintenance-anchors-20260915.md
- 每轮真机验收后回写 lamda_yun_一期计划_多智能体版.xlsx 11_执行记录
