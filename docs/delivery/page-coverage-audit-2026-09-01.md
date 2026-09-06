# 竞品页面与 Web/Studio 实现覆盖审计（2026-09-01）

## 结论

当前实现已经完成了“信息架构登记”和可访问的页面壳，但尚未达到“134 个竞品功能页均已真实复刻并完成前后端接线”。

- PDF 提取矩阵包含 15 个模块、134 个功能页、111 个原始唯一路由。
- Web 为全部 134 项生成了唯一 URL，但它们共用一个 `OperationsView.vue` 动态组件；这证明路由和字段元数据完整，不证明每项业务已实现。
- 134 项中只有 16 项拥有显式后端 operation key，118 项（88.1%）明确显示“暂无执行适配器”或只能保存配置草稿。
- 18 个核心 Web 页面中，9 个读取 `apps/web/src/data/mock.ts`，8 个为静态本地数组/本地状态页面，只有 Studio 会话入口接入 Control API。核心业务页面没有形成真实 CRUD 闭环。
- Studio 已能交换调试会话并连接受限 relay，但代码保存、运行、暂停、单步、回退和取消仍主要改变浏览器本地状态并写 heartbeat；UI 树、运行变量和证据条目仍含固定样例。

因此，当前更准确的交付状态是：**页面目录覆盖 134/134；页面级真实业务闭环远低于 134/134。**

## 审计口径与证据

来源：用户提供的《鱼游助手_全功能竞品调研报告.pdf》及已生成的 `tmp/pdfs/competitor-audit/entries.json`、联系表渲染图。矩阵统计为 134 条、15 个模块、111 个唯一原始路由。`apps/web/tests/operations-catalog.spec.ts` 也只验证条目、元数据、字段数量和路径回查，不验证 134 项真实后端行为。

实现判断采用四层证据：

1. 路由是否可达；
2. 是否存在页面专属组件和真实交互，而非共用模板或静态数组；
3. 是否调用真实 API，且提交页面参数；
4. 是否有状态回读、错误处理和持久化结果。

## 最高优先级缺口

### P0 - 134 条目录只有 16 条后端映射

证据：`apps/web/src/data/operations-catalog.ts:121-138` 只有 16 个 `backendOperationMappings`；`apps/web/src/views/OperationsView.vue:119-139` 对无映射项直接禁用执行并显示“暂无执行适配器”。

影响：118 个竞品入口虽有路径、标题、字段和说明，但无法形成真实任务。尤其缺少：

- 商品/帖子编辑、导入、媒体上传和规格管理；
- 订单同步、订单详情和物流处理；
- 聊天关键词/场景回复及图片、音频、视频素材管理；
- 个人资料、密码、积分、AI 设置；
- 大多数闲鱼/转转/小红书授权任务的执行适配器。

建议验收标准：每个允许实现的功能必须有显式 operation key、请求 schema、后端 handler、持久化状态、权限和端到端测试；策略禁止项应继续明确阻断，不以伪实现替代。

### P0 - 已映射操作也没有把页面字段作为操作参数提交

证据：`apps/web/src/views/OperationsView.vue:416-430` 将 `pageParameters` 放入通用 `context`，而 `createOperationTask/createBatchOperation` 的 `parameters` 固定传 `{}`。

影响：即使 16 个映射项能创建后端任务，水印参数、发布范围、验证选项等页面专属字段也可能不会进入 operation handler 的正式参数校验，当前接线更接近通用任务壳。

建议验收标准：为每个 operation key 建立强类型参数 schema；前端字段映射到 `parameters`；后端拒绝未知/缺失字段；测试验证参数确实影响预览或任务结果。

### P0 - Studio 的“运行器”并未执行编辑器代码

证据：

- `apps/studio/src/App.vue:60-118` 的 Python 源码是浏览器内字符串。
- `apps/studio/src/App.vue:351-365` 的单步和取消只更新本地 `stage/running` 并发送 heartbeat。
- `apps/studio/src/App.vue:400-406` 的保存、运行、暂停、回退按钮也只写日志/heartbeat，没有上传、编译、签名、启动 runner 或获取真实执行事件。

影响：Studio 当前可做受限远控 tap/evidence 请求，但还不是“APK 程序调配和手机自动化调试工具”的完整执行工作台。

建议验收标准：实现源文件草稿 API、静态检查/打包 API、受控 runner 启动、真实步骤事件流、安全取消和运行结果回读；浏览器不得自行推进 durable stage。

### P0 - Studio 证据登记使用固定摘要和对象地址

证据：`apps/studio/src/App.vue:276-289` 先请求 relay 截图，随后立即用固定 SHA256 `88a16e...` 和拼接出的 S3 地址登记证据，没有等待 Edge 返回的真实 `evidence` 消息及其摘要/大小。

影响：会生成无法由真实对象证明的证据元数据，不能作为真机验收或审计凭证。

建议验收标准：等待 relay `evidence` 回执，只接受 Edge/后端确认的 object reference、SHA256、size；服务端重新校验对象元数据后再写审计。

## 高优先级缺口

### P1 - 134 个 URL 共用单一通用页面，不等于页面复刻

证据：`apps/web/src/router.ts` 仅有 `/operations/:moduleId/:operationId` 一个详情路由组件；`apps/web/src/data/operations-catalog.ts:191-224` 用元数据生成 134 项；`OperationsView.vue` 使用六种 mode 的通用模板。

典型差距：

- PDF 的普通/拍卖/免费送编辑页包含多图上传、拖拽排序、视频、规格、AI 标题/描述、违禁词等；当前主要是文本/select/number/toggle 字段。
- PDF 的商品链接采集包含链接解析、平台差异、规格图、视频、去重、插件、库存和任务列表；当前这些页面被策略阻断或仅显示字段与说明。
- PDF 的聊天管理包含关键词、场景组和多媒体回复资产；当前没有消息会话、规则 CRUD、匹配测试或素材上传闭环。
- PDF 的订单模块包含同步、采购、取单号和订单列表；当前没有订单实体 API 与状态回读。

建议验收标准：按业务域拆成专属组件或专属子组件，至少覆盖 PDF 中可安全实现的关键控件、列表列、批量动作、详情抽屉和真实状态流。

### P1 - 核心 Web 页面大多为 Mock 或静态演示

证据：

- `apps/web/src/api/client.ts:1-44` 的设备、作品、计划、任务、APK、审计全部来自 `data/mock.ts`，所有 action 返回 `req-mock-*`。
- 使用该客户端的核心页包括 Dashboard、Devices、DeviceDetail、Works、PublishDetail、Tasks、TaskDetail、APK Repository、System。
- Accounts、Groups、Media、Watermarks、Automation、APK Rollout、Publish Create、Work Editor 使用组件内固定数组或本地 ref；按钮多数没有 API handler。

影响：页面看起来完整，但刷新后状态消失，无法证明 CRUD、审批、上传、安装、回滚或审计功能。

建议验收标准：逐页移除默认 Mock 数据路径；开发模式可保留显式 fixture，但生产构建必须在 API 未配置时 fail closed 或只读显示不可用。

### P1 - Studio 的 UI 树、Selector 和变量不是实时设备数据

证据：`apps/studio/src/App.vue:51-58` 固定定义 6 个节点；`apps/studio/src/App.vue:441-446` 直接渲染固定节点和固定 snapshot/current_app/证据条目。Relay 的 `onLayout` 目前只写“节点数量”日志，没有替换 UI 树。

影响：用户看到的 locator、bounds 和点击目标可能与真实设备画面无关；实际 tap 仍固定发送坐标 `885,2265`（`App.vue:323-325`）。

建议验收标准：用 relay layout 更新节点树、屏幕尺寸和坐标映射；点击从真实画面坐标换算；locator 来源必须绑定当前 layout sequence。

### P1 - Live API 失败会自动降级为 Mock

证据：`apps/web/src/views/OperationsView.vue:351-383` 在 Control API 不可达时自动切换 Mock；`createRun` 随后可生成 Mock 回执。

影响：操作员可能在后端故障时继续走“成功样式”的模拟流程。虽然界面有 Mock 标签，但生产验收不应把这种结果计为功能可用。

建议验收标准：生产构建 API 失败时禁止创建动作；Mock 仅由显式开发开关启用，并持续显示不可混淆的环境水印。

## 中优先级缺口

### P2 - 核心页面按钮缺少交互或只改变本地显示

实例：

- `AccountsView.vue` 的新增授权、解除绑定没有 handler。
- `GroupsView.vue` 的新建、管理没有 handler。
- `MediaView.vue` 的上传、搜索、类型筛选没有状态或 API。
- `WatermarksView.vue` 只有位置/透明度参与预览，保存按钮没有 handler，边距/宽度也未绑定 ref。
- `AutomationView.vue` 的发布候选包、回滚没有 handler。
- `ApkRolloutView.vue` 的暂停和回滚只改本地 ref/关闭弹窗。
- `PublishCreateView.vue` 最终只设置 `created=true`，明确是模拟计划。
- `WorkEditorView.vue` 保存只改一段时间文字，提交审批无 handler。

### P2 - 固定样例数据会造成“真实状态”错觉

`OperationsView.vue:78-101` 为所有功能生成同一组 8 条设备/负责人/状态记录；资产列表、趋势图、统计数字也为固定值。Studio 的设备、Edge、snapshot、调用耗时和证据摘要同样固定。应保留明确 fixture 标签，且不得用于验收证据。

### P2 - 当前测试主要证明目录完整，而非功能完整

`apps/web/tests/operations-catalog.spec.ts` 验证 134 条元数据、字段数、唯一路径和风险分类；路由测试验证 18 个核心路由与 2 个动态路由。缺少按竞品页验证真实上传、保存、任务创建、消息回复、订单同步、设备动作和回读结果的 E2E 测试。

## 覆盖判定摘要

| 范围 | 路由/页面壳 | 专属交互 | 真实 API | 当前判定 |
|---|---:|---:|---:|---|
| 竞品功能目录 | 134/134 | 以通用 profile 为主 | 16/134 有 operation key | 信息架构完成，业务未完成 |
| Web 核心页 | 18/18 | 部分 | 1 个 Studio 会话入口；其余 Mock/静态 | 原型级 |
| Studio relay 会话 | 已有 | frame/tap/evidence 请求部分接通 | 会话/heartbeat/revoke 已接 | 部分可用 |
| Studio 自动化运行器 | 有完整视觉界面 | 本地状态推进 | 无代码执行闭环 | 未实现 |
| 真机证据链 | 有展示 | 固定样例与请求入口 | 未等待真实证据回执 | 未完成 |

## 建议实施顺序

1. 修复 Studio 真实证据回执、实时 UI tree 和真实 runner 生命周期。
2. 将 Operations 的 16 个已映射功能改成强类型 `parameters`，完成端到端结果回读。
3. 优先实现竞品主链路：商品/帖子编辑与媒体、发布计划、任务队列、设备/账号、订单、聊天回复。
4. 把核心 18 页的 Mock/静态数据替换为真实 Control API CRUD。
5. 对其余允许实现的竞品页逐项增加 adapter；策略禁止项继续保留阻断说明。
6. 建立按页面验收矩阵：路由、组件、交互、API、持久化、权限、E2E、真机证据分别打勾，禁止只用“路由存在”判定完成。
