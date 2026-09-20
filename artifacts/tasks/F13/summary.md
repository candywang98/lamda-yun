# F13 evidence summary

- Task: 业务表单薄层与真正端到端UI
- Audited: 2026-09-20 (Asia/Shanghai)
- Software status: `SOFTWARE_DONE`
- Acceptance status: `SOFTWARE_ACCEPTED`
- Device acceptance: not applicable; software verification only
- Staging status: `NOT_TESTED_AGAINST_STAGING`（无可用 staging：BLK-001 未解除，Control API 无公网部署）

## Delivered behavior

- `/business-operations` 薄表单工作台：功能下拉直接来自 operation catalog（15 模块 / 130+ 条目），按 `pageProfile.fields` 生成表单控件（text/number/select/toggle），不复制业务状态机，不改 1331 行 OperationsView。
- 平台/模块、资源目标、执行应用、设备范围、业务字段、预算/价格、定时在快照中明确可见并冻结；六字段（operationKey/featureId/resourceIds/parameters/context/batch）规范化哈希与后端 `canonical_hash` 逐字节一致（测试内嵌后端预计算常量）。
- 提交走真实 `/api/v1/operations/tasks` 与 `/operations:batch`（Idempotency-Key），返回 `requestSha256` 与页面哈希比对并显示一致/不一致；部分失败按目标逐行显示资源、状态、错误码与说明。
- 可用性四态（ENABLED/PENDING/POLICY_BLOCKED/OUT_OF_SCOPE）透出后端 reason；后端 `[STATE]` 前缀优先；未映射入口 OUT_OF_SCOPE 不回退示例操作；mock 模式只读展示、绝不铸造。
- 铸造后的模型层修复：`business-operation.ts` 此前是无任何引用的死代码且无法通过 typecheck，本切片修复其类型缺陷并正式接线。

## Proven evidence

- Feature implementation: `apps/web/src/features/operations/`（api.ts、OperationFormWorkbenchView.vue、routes.ts、index.ts、business-operation.ts 修复、BusinessOperationSnapshot.vue 接线）
- Router registration: `apps/web/src/router.ts`（新增 `/business-operations`，不改既有路由）
- Unit/view coverage: `apps/web/tests/business-operation.spec.ts`（11 项：四态优先级、mock 不铸造、OUT_OF_SCOPE 不回退、六字段哈希常数一致、freeze 去重/批量守卫、单/批端点、视图三态、部分失败明细、目录真实性）
- E2E coverage: `apps/web/e2e/fleet-business.spec.ts`（2 项，chromium，退出码 0：目录渲染 + fail-closed 不铸造；选择功能后显式原因）
- GUI evidence: `artifacts/tasks/F13/evidence/desktop-workbench.png`、`mobile-workbench.png`（窄屏 scrollWidth=clientWidth，无溢出）

## Verification

- F13 Web tests: 11 passed.
- Full Web suite: 39 files, 284 tests passed; production build passed.
- vue-tsc typecheck: passed（含修复后的 business-operation.ts）.
- F13 scoped ESLint: passed.
- Playwright E2E (chromium, local vite 4173, no staging): 2 passed, exit code 0.
- GUI desktop 1440x1000 + mobile 390x844: no overlap, no horizontal overflow.
- 后端无改动：复用既有 operations API 与 X12 可用性目录，OpenAPI 无变更。

## Honest boundaries

- 未连接真实 staging（任务卡要求"定向E2E仅连接staging"）：当前不存在可用 staging，E2E 连接本地 Vite 实例验证 fail-closed 呈现；staging 实测记 NOT_TESTED_AGAINST_STAGING。
- ENABLED 真实铸造仅在单测中用 mock client 验证哈希一致与部分失败明细；真实后端铸造已在 F10 之前波次的 operations API 测试覆盖（1051 后端全量含 operations 套件）。
- F13 的 17 个 lineage 包不在本切片逐包背书：薄层提供统一表单入口与冻结快照，各业务能力仍按自身包状态推进。
- 全仓 web eslint 既有债务（19 错/219 警，非 F13 文件）未动。

## Remaining acceptance gap

按钮可点 ≠ 功能验收通过；未做任何真实业务侧效果。软件验收不声明 staging/设备/整包验收。
