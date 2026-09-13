# P09-XY-G3 闲鱼单件真实发布验收 — 2026-09-13

Contract: `p09-steps-commit/20260913.1`（`569fed1` + `37860d3`）。
**结论：P09-XY-G3 子项通过。** 仅覆盖闲鱼单件商品发布；不主张其他平台、删除、扣费或整个 P09 整包通过。

## 验收对象

- 设备 OnePlus 9R `b0644fb5`（binding `4aabc387`，tenant `…1111`），蜂窝网络直连首尔 API（release `p09-steps-569fed1`）。
- APK SHA-256 `47055f0948e14d9b51e18d0d7bfbc0de17db8ac8a2dfe63866a9739c633d5b6f`（HEAD `37860d3`）。
- 冻结内容（同 2026-09-12 任务 37376e69 与 precommit-20260913）：描述「Notion Business 兑换券，图示价值 $240。拍下后按说明发送兑换方式。支持当面交易。」、价格 199、媒体资产 `01a07ace`、保存地址第 1 项。
- 最终执行不依赖 USB/ADB/Edge：手机通过自身网络领任务、执行、回传；ADB 仅用于安装与观察。

## 门禁链路（本次新增并验证）

`569fed1` 把旧 steps 任务的 `xianyu_publish_button` 点击接入受控账本（此前仅探针/签名 Recipe 可用）：
steps 规范化哈希冻结身份 → 本地 INTENT → 服务器一次授权（201 AUTHORIZED）→ **恰好一次** tapOnce → 独立后置观测（`xianyu_publish_success` + 截图哈希变化）→ 不确定绝不重放 → 任务停在提交步 → 只有 revision>0 的云端解除才落终态。`37860d3` 修复服务端把领取时动态头部（controlEpoch）计入哈希导致的双端身份不一致。

## 执行记录

| 任务 | 结果 | 说明 |
|---|---|---|
| `97a2f566`（G3 第 1 次） | FAILED / CONFIRMED_NOT_SUBMITTED | 双端身份不匹配（头部哈希 bug）→ 意图被拒 → **未点击**，平台零副作用；本地 UNKNOWN 阻塞队列头，由权威 NOT_SUBMITTED 行（revision 1）解除——完整验证了失败路径的安全性与核对传播 |
| `3a715822`（G3 第 2 次） | **SUCCEEDED / APPLIED** | 22 步执行至 click-publish（step 20），门禁单击一次，后置条件观测成功，`mobile_action_commit` 记录 APPLIED + 前后截图哈希（`1010448b…` / `64eb25c5…`） |

## 真实商品核验（操作员）

- 「我发布的」→ 在卖 1 件；详情页逐字命中冻结文案（含「发送兑换方式」「支持当面交易」），价格 **199**，位置太原，「刚刚擦亮」。
- 详情截图（未入公开仓库，含账号信息）SHA-256 `69e8acce350b07cd7d62870b12c919965c685bff…`。
- 操作员解除：`CONFIRMED_APPLIED`，platformItemId `xianyu-listing-notion-voucher-199-20260913`，证据为上述核验。
- 解除后设备 `reconcilePending()` 同步：手机账本 APPLIED、task_inbox TERMINAL_CONFIRMED/SUCCEEDED，与服务器一致。

## 软件门禁

- 后端：`test_p09_action_ledger.py` 36 passed / 1 skipped（新增 steps 身份、头部不参与哈希、非发布 steps 拒绝、跨任务身份不同）。
- Android 单测：185 passed / 0 failed（新增：steps 身份金标准/键序无关/内容变更即新身份、发布点击路由门禁且停跑、非发布点击绕过门禁）。

## 未主张（Not claimed）

- 其他平台（小红书/抖音/公众号）与删除、扣费、推广类 G3。
- 服务表单分支（F08）、素材身份核验（F09）、Recipe 引擎真实动作语义（F01）——仍为后续工作。
- 表单分类仍按当前默认路径；本次商品表单发布成功。
- 多机/Note9（原计划明确推迟）。

## 运维记录

- 首尔部署 `p09-steps-569fed1`（systemd 切换 + 重启，docs 200、心跳正常）；旧 release `p09-ledger-ce823ad` 保留可回滚。
- 手机侧 ColorOs IME/无障碍均恢复原状（搜狗当前、CloudCtl 无障碍开启）。
