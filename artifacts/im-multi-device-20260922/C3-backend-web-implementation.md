# C3 后端 / Web 实施记录：pa-im-m3/20260922.1

日期：2026-09-23（Asia/Shanghai）

最新补记：C4已补共享Android/Python SHA夹具、最新消息窗口/稳定分页、UTC输出、完整SQLite/本地隔离PostgreSQL迁移回归（移除stamp跳过）。最终41项后端、304项Web及类型/格式/构建结果见 `C4-controller-verification.md`，下文C3测试数为历史。

结论（主会话接管后更新）：C3 后端与 Web 聚焦软件门通过。主会话修复轮询重叠、过期列表请求覆盖、列表错误被消息成功响应清除及会话切换时响应串线；按后端已有返回值补齐 Listing DTO 三个可选可空统计字段，解除 Web 全量类型检查阻塞。后端 34 项、Web 21 项通过，Web typecheck/build、后端 pyright/mypy、改动文件 lint 与 git diff --check 通过。db.py 全文件格式检查仍有既有格式差异，不宣称全仓格式门通过。不是 C4 全栈通过或真机验收；未部署或操作设备。下文旧执行记录保留，最新结果以文末主会话收口记录为准。

## 设计与修改

### 入站契约、canonical 与幂等

- `services/control-api/src/cloudctl_api/im_routes.py:34-40`：每条入站 `platform` 为必填 `Literal["xianyu"]`；缺失和其它值由 Pydantic 返回 422，服务端不补默认。
- `services/control-api/src/cloudctl_api/im_service.py:65-85`：canonical 与 C2 Android 一致，按 Python Unicode 码点先限 4000，再在超过 2000 时加 `TRUNCATED ` 并保留前 2000；恰好一个前缀加 2000 码点保持幂等。
- `services/control-api/src/cloudctl_api/im_service.py:78-85`：dedupe 原材料为 `device_id|platform|peer_key|epoch_second|canonicalText`；device id 只取 binding。历史键不重写。
- `services/control-api/src/cloudctl_api/im_service.py:221-288`：线程查找与创建带 tenant/device/platform/peer，正文和 dedupe 共用 canonical 值。

### 数据库迁移与线程摘要

- `services/control-api/migrations/versions/20260923_0033_im_thread_platform_key.py:17-39`：upgrade/downgrade 前查询同 tenant/device/peer 的多 platform 冲突；有冲突立即抛错并列出样例，不合并、不删除。
- `services/control-api/migrations/versions/20260923_0033_im_thread_platform_key.py:42-59`：新唯一键是 tenant+device+platform+peer；downgrade 仅在旧三元组无冲突时恢复。
- `services/control-api/src/cloudctl_api/db.py:891-905`：ORM 唯一键与迁移一致；`ImMonitorConfigRow.platforms` 修正为实际的 `list[str]` 类型。
- `services/control-api/src/cloudctl_api/im_service.py:291-341`：线程列表保持 tenant、可选 device、未读和 limit；分页在同时间戳时用 id 作稳定游标，逐线程返回最新消息 `lastMessageText`。

### Web

- `apps/web/src/api/im.ts:4-17`：`lastMessageText` 成为服务端线程 DTO 的明确字段，空白归一化为 null。
- `apps/web/src/views/ImInboxView.vue:36-51`、`:135-164`：默认不传 deviceId；筛选选项合并设备列表和线程设备，值为生产 device id，显示友好名与短 id。
- `apps/web/src/views/ImInboxView.vue:49-87`：刷新成功按 thread id 保持选中；失败不覆盖旧线程、旧选中或旧消息，只更新错误。
- `apps/web/src/views/ImInboxView.vue:287-330`：visible 时每 5 秒刷新线程和选中消息；hidden 停止；恢复 visible 立即刷新；卸载清理 timer 和 visibility listener。
- `apps/web/src/views/ImInboxView.vue:354-460`：列表展示未读、最近正文/“暂无正文”、时间、友好设备名/短 id。回复代码保留但 C3 没有调用或新增发送路径。

### 测试覆盖

- `tests/integration/test_im_aggregation.py:74-138`：platform 必填/仅 xianyu、2000/2001/>4000/补充平面字符、canonical 重投和确定性 SHA-256（不含 ADB serial）。
- `tests/integration/test_im_aggregation.py:524-642`：tenant/device 隔离、同秒稳定分页、摘要、迁移冲突中止、升级唯一键和降级保护。
- `tests/integration/test_im_fleet_ownership.py:32-48`：既有舰队测试载荷显式加入 xianyu，继续保护重投、设备所有权与回复边界。
- `apps/web/tests/im-inbox.spec.ts:128-217`：三机混排、生产 deviceId 筛选、5 秒 fake timers、选中保持、visibility 暂停/恢复、卸载清理、失败保留。
- `apps/web/tests/im-api.spec.ts:53-60`：服务端摘要空值归一化。

## 实际命令与结果

### 通过

1. `./.venv/bin/pytest -q tests/integration/test_im_aggregation.py tests/integration/test_im_fleet_ownership.py`
   - 最终退出码 0；`34 passed in 15.93s`。
2. `pnpm --dir apps/web exec vitest run tests/im-inbox.spec.ts`
   - 最终退出码 0；1 file、11 tests passed。
3. `pnpm --dir apps/web exec vitest run tests/im-api.spec.ts`
   - 因本轮也修改该规格而单独运行；退出码 0；1 file、9 tests passed。
4. `./.venv/bin/ruff format --check`（除保持既有格式的 `db.py` 外五个本轮 Python 文件）+ `ruff check`（同五文件）+ `ruff check --ignore E501 services/control-api/src/cloudctl_api/db.py`
   - 退出码 0；格式检查 5 files already formatted；lint 全部通过。`db.py` 的 E501 是本轮前既有行，未为格式门扩大非 IM diff。
5. `./.venv/bin/pyright services/control-api/src/cloudctl_api/im_routes.py services/control-api/src/cloudctl_api/im_service.py services/control-api/src/cloudctl_api/db.py services/control-api/migrations/versions/20260923_0033_im_thread_platform_key.py tests/integration/test_im_aggregation.py tests/integration/test_im_fleet_ownership.py`
   - 退出码 0；0 errors、0 warnings。
6. `./.venv/bin/mypy services/control-api/src/cloudctl_api/im_routes.py services/control-api/src/cloudctl_api/im_service.py services/control-api/src/cloudctl_api/db.py services/control-api/migrations/versions/20260923_0033_im_thread_platform_key.py`
   - 退出码 0；4 source files 无问题。把两个既有未完整注解的测试文件纳入 mypy 会经导入链报告大量旧测试注解错误，因此服务文件门单独通过，测试文件并未宣称 mypy 通过。
7. `python3 scripts/plan_guard.py docs/current/tasks.json`
   - 退出码 0；`valid: true`；仅静态计划图检查，不代表 C3 或真机通过。
8. `git diff --check`
   - 退出码 0，无输出。

### 失败 / 阻塞

1. 用户给出的原样 Web 命令 `pnpm exec vitest run tests/im-inbox.spec.ts` 在仓库根执行，退出码 254：`Command "vitest" not found`。按 workspace 实际入口改为 `pnpm --dir apps/web exec ...` 后通过。
2. `pnpm --dir apps/web typecheck` 退出码 1；`pnpm --dir apps/web build` 退出码 1。两者都在 `vue-tsc -b` 被 `src/views/ListingInfoCollectView.vue:176-178` 的 `exposureCount`、`viewsCount`、`wantsCount` 不存在错误阻塞；该文件不在 C3 允许范围，本轮未改，Vite 构建阶段未开始。
3. 首次 SQLite 迁移测试从 0032 升级时命中既有 `20260920_0032` 的 PostgreSQL-only `ALTER COLUMN` 语法。测试改为升级到 0031、stamp 0032，再只验证本轮 0033；生产迁移逻辑没有绕过 0032。

## 安全边界核对

- C3 diff 检索 `replyImThread`、`:reply`、OUT、DUTY、`settings put secure`、`pm uninstall`、`pm clear`、注入与 Root。命中仅为原有 reply / DUTY 回归测试与保留代码的上下文或格式变化；没有新增调用 reply、没有新建 OUT、没有自动回复或发送。
- 未连接设备、未使用 ADB serial 作业务身份、未修改 Android/B14/C2 文件、未 reset/checkout/restore/commit。
- 迁移不更新 `im_message.dedupe_key`，不合并或删除线程；冲突时 fail closed。

## 未覆盖

- Web 全项目 typecheck/build 尚未通过，阻塞点是 C3 范围外的既有 Listing 类型错误。
- 未执行全仓 pytest、全仓 mypy、Android 测试、部署、生产数据库迁移、服务重启、设备操作或三机真机验收。
- 未宣称 C4 质量门、C5 接入、C6 真机验收、整包或模块验收通过。

## 主会话直接收口（2026-09-23）

不再使用工作流或子智能体。保留暂停执行者已落盘的实现并直接审查修复。

- `ImInboxView.vue`：轮询单飞；线程请求序号拒绝过期响应；列表失败不再继续消息刷新覆盖其错误；卸载后拒绝列表结果；会话切换时拒绝旧会话消息结果。
- `im-inbox.spec.ts`：补慢请求不重叠测试；失败测试分别验证列表失败和后续消息失败，不删除失败断言。
- `features/fleet/listings-api.ts`：只补 `exposureCount/viewsCount/wantsCount?: number | null`；后端 fleet_listings.py 已返回这些字段，不修改业务实现。
- 仓库 `.venv/bin/python -m pytest -q tests/integration/test_im_aggregation.py tests/integration/test_im_fleet_ownership.py`：34 passed。
- Web 目录 `node node_modules/vitest/vitest.mjs run tests/im-inbox.spec.ts tests/im-api.spec.ts`：21 passed。
- Web 目录 `node node_modules/vue-tsc/bin/vue-tsc.js -b` 和 `node node_modules/vite/bin/vite.js build`：均通过；Vite 有 >500KB chunk 告警。
- Web 改动文件 ESLint：通过。
- 四个后端生产/迁移文件 pyright：0 errors；mypy：4 source files 无问题。
- 五个后端路由/服务/迁移/测试文件 Ruff lint：通过；db.py 全文件 format check 仍包含历史未格式化行，未擅自扩大格式改动。
- `git diff --check`：通过。

本轮没有运行生产数据库迁移；SQLite 0033 迁移测试仍沿用上述跳过 PostgreSQL-only 0032 的隔离测试口径，不能冒充生产完整迁移验证。C4 全仓门、部署和三机真实通知验收仍未完成。
