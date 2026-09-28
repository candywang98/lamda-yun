# 网页云控平台检查与修复

日期：2026-09-28。范围：`apps/web`，本地代码、组件测试和浏览器回归。
本文记录首次本地验收阶段；用户随后要求部署并同步 GitHub，后续结果另记于本目录发布记录。

## 结论与边界

- 本轮发现的问题已在本地修复，最终 Web 单元测试 519/519、浏览器回归 14/14 通过。
- 浏览器使用桌面 Chromium 和 Pixel 7 模拟视口，业务接口全部由测试 fixture 拦截；这不是手机真机或线上后端验收。
- 首次本地验收结束时未部署、未推送、未创建 Git 提交，未更改任务台账的开发或验收状态。
- 未操作实体手机，未触发真实消息发送、发布、删除或采集任务。
- 线上入口访问返回 `ERR_INVALID_AUTH_CREDENTIALS`；未绕过认证，本轮不证明线上业务链路可用。
- 本轮没有修改工作区原有的 Android 测试改动或既有验收材料。

## 项目进度

来源：检查时的 `docs/current/tasks.json`，口径依据 `docs/current/README.md`。

| 维度 | 状态 | 数量 |
| --- | --- | ---: |
| 开发 | SOFTWARE_DONE | 44 |
| 开发 | IN_PROGRESS | 5 |
| 开发 | NOT_STARTED | 5 |
| 验收 | SOFTWARE_ACCEPTED | 41 |
| 验收 | DEVICE_WAIT | 4 |
| 验收 | DEVICE_ACCEPTED | 1 |
| 验收 | NOT_RUN | 8 |

共 54 条任务。这些是台账记录，不是本轮重新完成了所有验收。
`docs/current/workflow-progress-20260926.md` 仍记录发布/下架专用页面接线、现有三台手机业务链路及最终脱离 ADB 验收的缺口。
软件测试通过不能替代真实设备验收，也不能据此宣称全部业务已经可用。

## 已修复问题

| 范围 | 原问题 | 本轮处理 |
| --- | --- | --- |
| 会话与入口 | 直接进入订单、消息或设备页面时未初始化权限；会话重新验证失败可能保留旧身份；配置了 URL 就显示已连接 | 工作台统一初始化登录态，合并并发加载，验证中禁用授权操作，失败清除身份及权限，提供重试，连接提示改为会话验证结果 |
| 权限按钮 | `PermissionButton` 未使用传入的 permission | 同时约束 disabled 状态和 click 事件 |
| 商品筛选 | 在后续页输入筛选条件后仍停留在原页，结果显示为空 | 实时筛选和每页数量变化时回到第一页 |
| 商品批量编辑 | 服务器拒绝更新时，界面已提前修改；部分成功后重试可能重复插入标题前缀；额外 metadata 可能丢失 | 在副本上修改，仅应用服务器确认结果；移除已成功目标，只重试剩余目标；保留未知属性；防重复提交 |
| 订单列表 | 筛选切换失败后，旧列表可能与新筛选的后续页混合 | 为列表关联筛选快照，切换时清空旧数据，失败后禁止错误追加 |
| 设备工作台 | 详情对应设备消失或刷新失败时传入 undefined；迟到刷新覆盖新状态；多设备取消共用 busy 标记 | 使用安全详情引用和请求序号，按设备隔离取消状态；空列表也保留刷新入口 |
| 消息监控设置 | 切换设备后旧保存响应覆盖新设备；加载失败提示不可见；只读身份无法切换设备查看配置 | 按设备及请求代次隔离响应，错误提示独立显示并提供重试，保留只读切换能力 |
| 消息会话分页 | 只能访问服务端返回的前 50 条会话 | 接入现有 after 游标，保留已加载页数，隔离筛选变化后的迟到响应，加载失败不再误报为空列表 |
| 手机网页商品列表 | 表格撑宽整页，浏览器自动缩放，分页点击被错误拦截 | 表格独立横向滚动，限制网格列宽，分页和筛选保留在屏幕内 |

主要源码：
`src/stores/session.ts`、`src/components/OperationsShell.vue`、
`src/components/PermissionButton.vue`、`src/views/ProductManagementView.vue`、
`src/views/OrdersView.vue`、`src/features/fleet/FleetWorkbenchView.vue`、
`src/views/ImInboxView.vue`、`src/api/im.ts`，均位于 `apps/web` 下。

## 验证结果

| 命令或检查 | 最终结果 |
| --- | --- |
| `pnpm --filter @cloudctl/web test` | exit 0，45 个文件、519 项测试通过；在最后一次商品布局修改后重跑 |
| `pnpm --filter @cloudctl/web build` | exit 0，包含 vue-tsc 类型检查与 Vite 生产构建 |
| `pnpm --filter @cloudctl/web lint --quiet` | exit 0，0 errors；quiet 不表示没有原有 warnings |
| `git diff --check` | exit 0 |
| 指定桌面/手机浏览器回归 | exit 0，14/14 通过 |
| 截图复核 | 已检查商品桌面/手机布局、手机设备失败恢复、桌面监控配置恢复、手机第 51 条会话及正文 |

浏览器回归命令：

```bash
env VITE_CONTROL_API_URL=http://127.0.0.1:9999 \
  VITE_CONTROL_API_DEV_AUTH=false VITE_OPERATIONS_MOCK_ENABLED=false \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  PLAYWRIGHT_ARTIFACTS_DIR=/tmp/cloudctl-web-qa-final-20260928 \
  pnpm --filter @cloudctl/web exec playwright test \
  e2e/console-regressions.spec.ts e2e/product.spec.ts --reporter=line
```

新增 `tests/permission-button.spec.ts`、`tests/product-management.spec.ts`、
`e2e/console-regressions.spec.ts`；扩充会话、工作台、订单、消息及设备测试。
回归覆盖正常权限和只读权限、接口失败恢复、分页、商品更新被拒绝、
设备详情消失及并发请求等场景。

测试过程也修正了测试本身的问题：接口拦截收窄到 `/api/v1/`，避免拦截 Vite 源码；
选择器不再误匹配隐藏 option 或包含子标签的完整文本；窄屏溢出检查使用配置视口宽度，
避免自动缩放后的 `window.innerWidth` 掩盖页面超宽。未使用 force click 绕过交互故障。

最终截图目录：`/tmp/cloudctl-web-qa-final-20260928/test-results/`。
手机分页修复前的失败截图及 trace：
`/tmp/cloudctl-web-qa-layout-20260928/test-results/`。
这些临时目录可能被系统清理；测试文件保留在仓库中，可按上述命令重新生成。

## 仍未验证与已知告警

- 线上认证后的实际后端、真实数据和三台实体手机业务链路未在本轮验证。
- 浏览器回归只覆盖上述两个 spec，不是全站所有菜单和全部 E2E 测试。
- 保留 Vite 主 bundle 大于 500 kB 的构建告警，没有为消除告警做无关打包重构。
- 单元测试仍有 Node localStorage 实验性提示和测试用路由缺少路径的既有 warning，测试结果为通过。
- 本地预览为显式 Mock，不是线上平台。启动时覆盖开发代理目标为本机不可用端口，
  防止仓库 `.env.development` 中的线上代理地址被预览继承。

置信度：上述本地修复与已执行回归为高；线上效果及真机验收未知，等待相应环境验证。
