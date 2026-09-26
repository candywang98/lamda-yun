# 通知用途分类交付记录

## 范围与版本

用户确认以通知用途分类为优先：用户消息、系统/营销、待确认及全部分区；
允许人工纠正、恢复自动及重新识别。完整聊天正文、长期后台稳定性不是本轮前置条件。
只收不发，不删除未知或系统消息，不启用 DUTY 导航，不扩展生产平台。

- 冻结合同：`im-notify/20260926.1`，共同基线 `207a97d`。
- 后端主分支：`b8130f2`，新增分类侧表迁移 `20260926_0034`。
- Android 子任务：`886d2d8`，集成提交 `0056d17`。
- Web 子任务：`eb4d689`，集成提交 `d2a6808`。
- 主分支 OpenAPI：`fb98602`。
- 聚焦云端发布：`bb19ad2`，仅在原线上 `3a1d306` 上应用通知分类后端、
  网页和对应测试/契约，不包含主分支无关微信、远控或 Android 运行行为。

## 实现边界

原始消息、去重键、时间及设备/平台/联系人隔离保持不变。分类独立存储：
保留 Jev 原始预测和置信度，0.95 阈值不降低；人工覆盖独立于异步模型结果。
消息行锁、版本号及识别代次分别保护首次分类、人工并发和过期模型返回。
分类筛选在 SQL 分页之前执行，会话摘要及排序使用当前分区匹配的最新消息。
分区计数是整个设备/未读过滤结果的会话数，不是当前页或未读消息数。

确定规则仅覆盖窄范围模板，例如有名字的“发来一条新消息”；明确官方来源与
订单/营销内容组合优先。频道或昵称单独不构成用途证明；普通疑难内容交给模型或待确认。
重识别使用该条通知原始标题，避免后来会话改名改变旧消息判断。

模型仍是有界、非持久队列。错误/满队列/正常关闭写入分类状态，消息保留；
异常杀进程可能留下 PENDING，待确认分区仍能找到，需显式重新分类。
不存在自动批量历史回放。HUMAN_MESSAGE 不证明发送者为真实自然人。

## 已执行验证

主分支与聚焦发布各自运行以下测试，均 exit 0、**118 passed**：

```sh
.venv/bin/pytest tests/unit/test_im_classifier.py tests/unit/test_im_observer.py \
  tests/unit/test_im_notification_rules.py tests/integration/test_im_notification_classification.py \
  tests/integration/test_im_aggregation.py tests/integration/test_control_api_migrations.py \
  -q --disable-warnings --maxfail=2
```

聚焦发布使用主工作树的 Python 测试运行器，但 pytest 路径指向聚焦发布代码。
包含 SQLite、独立 PostgreSQL、真实行锁并发、原始预测、元数据兼容、权限/租户隔离、
版本冲突、人工与模型竞态、原始标题、混合分区/分页及迁移历史行不变测试。

- 主分支 Web：42 文件、356 项通过；聚焦发布 Web：42 文件、349 项通过。
  两者非 IM 原有测试集不同，数字不能相加解释为独立覆盖。
- 两者 Vue 类型检查及生产构建通过；现有大 chunk 提示仍在，不影响构建退出码。
- 后端定向 Ruff、Mypy、`git diff --check` 通过。
- Android 子任务与主控集成复验均通过：Debug 全量 1,252 项、Acceptance IM 102 项，
  零失败/错误/跳过。主控另执行 `:app:assembleAcceptance`，exit 0。
  APK 为 `mobile/companion/app/build/outputs/apk/acceptance/app-acceptance.apk`，
  应用 ID `com.company.cloudctl.companion.acceptance`、0.1.0/versionCode 1，
  SHA256 `e0557249a19af8d7696c312f291cc9ad26b54ef7528cbb1674551e843d82de2a`。
  未安装 APK，不作为手机验收；安装前仍需核对现有包、签名及绑定兼容。
- 任务源 `plan_guard.py` 通过。

## 云端窗口

- 新发布候选：`/home/ubuntu/cloudctl-mobile/releases/im-notify-bb19ad2`。
- 私有备份：`/home/ubuntu/cloudctl-mobile/backups/im-notify-20260926`。
- 66 张表快照备份已隔离恢复并逐表计数/摘要一致。
- 隔离库：`cloudctl_imnotify_verify_20260926`，仅用于迁移演练。
  演练及发布完成后已移除，原始备份继续保留。
- 源码包 SHA256：`183eae043f0403ff79fae8d44ea135a796293a6439c90ebf9b429919d924403b`。
- 网页包 SHA256：`b62218273baff93884888b4632c727461e0fb53ba3975f6d8921339a4c1bef78`。
- 部署脚本：本机 `/private/tmp/cloudctl-im-notify-deploy-20260926/`，
  服务器 `incoming/im-notify-bb19ad2/`。不含内嵌凭据；
  使用 `.deploy.lock` 排他锁，既有受限环境文件及真实 Basic Auth，认证不放宽。
- 隔离库完成升级/降级/再升级，65 张原有业务表的计数及摘要不变，
  新分类表为空，没有历史消息回填。
- **2026-09-26 21:40:46 +0800 激活成功**，线上迁移为 `20260926_0034`。
  API 健康、认证、收件箱四分区接口及网页 HTML 摘要核验通过；
  匿名操作员/Companion/网页请求仍被拒绝，NOTIFICATION、receiveOnly 保持不变。
- 切换前后 128 条原始消息逐 ID 摘要一致；`OUT=23`、`mobile_task=376` 不变。
- 发布后 JS/CSS 实际 HTTPS 内容与构建文件哈希一致，均 HTTP 200；
  本轮启动后日志检查 0 traceback、0 HTTP 5xx，真实 Jev 调用 HTTP 200。

## 真实通知复核

使用普通工作台新 API，对既有真实消息
`8eeb6253-8769-448e-bf31-1e5e55a1ae72` 单条重新识别，没有伪造入站或直接改库。
2026-09-26 21:41 完成：

- 最终类别 `HUMAN_MESSAGE`，依据 `NAMED_PEER_MESSAGE_SUMMARY`，
  来源 `RULE`，状态 `RULE_CLASSIFIED`。
- Jev 原始预测 `HUMAN_MESSAGE`、置信度 **0.45**，模型状态 `NEEDS_REVIEW`；
  保留原始结果，没有把分数改高，也没有降低 0.95 阈值。
- VOG 查询结果：全部 1、用户 1、通知/营销 0、待确认 0，目标会话确实匹配用户分区。
- 普通人工纠正接口及恢复自动接口均通过，最后恢复为规则来源，
  不遗留人工覆盖；审计记录保留。本次不代表批量自动学习或分类精度验收。
- 原始 128 条消息仍逐 ID 摘要一致，OUT 和手机任务数量仍不变。
- API/HTML 验证不等于浏览器视觉验收，后者仍未完成。

## 回退

旧 API `im-3a1d306` 与旧网页 `/var/www/cloudctl-mobile-im-3a1d306` 保留。
新 systemd drop-in 为 `99-zzzzzzzzzzzz-im-notify.conf`。
激活脚本在健康/接口/网页校验失败时自动恢复旧应用与网页，保留兼容的 0034 分类侧表，
不恢复数据库快照、不删除消息。人工回退同样应先获取部署锁并核对占用。
若之后安装带元数据的新 APK，回退旧 API 前需处理旧接口拒收新增字段的兼容风险，
不能直接照搬本次尚未安装 APK 时的回退条件。

## 未完成

浏览器空间 18 仍交由用户登录，没有接管或替代真实页面视觉核验。
手机新 APK 安装需要重新确认空闲、云端占用及精确 serial 锁；
另一台 P30 和一加业务接入、三台聚合实机验收仍未完成。
单机及三机硬件验收不因软件测试而翻转。
