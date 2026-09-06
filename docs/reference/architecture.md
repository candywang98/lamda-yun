# LAMDA 云控系统技术架构报告与桌面智能体开发指南

**副标题：从网页对标样板收敛为“内容发布 + APK 管理 + 自动化调试 + 云控执行 + 服务器运维”的可落地系统**

- 文档版本：1.0
- 研究与设计基线：2026-08-30
- 目标读者：产品负责人、架构师、后端/前端/Android/运维工程师、桌面开发智能体
- 核心替换：停止采用 AutoJS 脚本运行器；设备自动化统一切换为 FIRERPA/LAMDA 客户端-服务端体系
- 使用边界：仅用于自有或明确授权的设备、账号、应用与内容；不实现规避平台风控、验证码绕过、指纹伪装、账号农场、虚假流量、未授权群发或私有接口逆向。

> 本报告不是对原网站后端的逆向说明，也不建议照搬其 114 个路由。它将对标样板中已确认的信息架构与操作闭环，重构为一套独立、可审计、可灰度、可恢复的现代云控系统。配套的 `AGENTS.md`、59 项机器可读任务清单与协议样例可直接作为桌面智能体的项目执行入口。

<!-- 此处在正式 DOCX 中分页 -->

# 目录

1. 执行摘要
2. 对标样板调研与范围收敛
3. LAMDA/FIRERPA 调研结论与采用边界
4. 建设目标、非目标与工程约束
5. 架构原则
6. 总体架构
7. 技术栈与版本策略
8. 核心领域模块
9. 边缘网关详细设计
10. LAMDA 驱动层与设备会话模型
11. Android 伴生 App 与企业设备管理
12. APK 管理、分析与自动部署
13. 自动化调试 Studio
14. 自动化包与 SDK 规范
15. 内容、媒体与作品发布
16. Temporal 工作流与状态机
17. 数据架构
18. API、WebSocket 与事件合同
19. 云控 Web 信息架构与页面规格
20. 安全、权限与合规
21. 部署拓扑与容量规划
22. 服务器与边缘脚本
23. 可观测性与 SLO
24. 测试、兼容性与验收
25. AutoJS 迁移方案
26. 代码仓库结构
27. 分阶段开发路线
28. 桌面智能体执行规则
29. 主要风险与缓解
30. 架构决策记录、资料与结论

<!-- 此处在正式 DOCX 中分页 -->

# 1. 执行摘要

## 1.1 最终建议

本项目应采用“云端控制平面 + 局域网边缘执行平面 + Android 设备平面”的三平面架构。浏览器负责管理与调试；云端负责身份、内容、任务、调度、审计和证据；边缘网关负责安全地连接手机、持有 LAMDA 服务证书、执行设备动作和缓存大文件；Android 设备上运行官方 FIRERPA/LAMDA Server，并安装一个独立自研 Kotlin 伴生 App。

第一版不要复刻对标系统所有功能。对标包共有 152 个菜单节点、114 个唯一路由，其中任务 40 页、商品 27 页、消息 11 页、设置 11 页、主页 8 页、订单 5 页、帖子 4 页、创意 4 页、统计 2 页、通知和反馈各 1 页。真正支撑本次目标的核心是约 18 个页面和一条可靠闭环：**内容/媒体 → 发布计划 → 审批 → 设备与账号租约 → LAMDA 执行 → 单次提交 → 结果对账 → 证据归档**。

## 1.2 架构结论表

| 决策域 | 推荐方案 | 关键原因 |
| --- | --- | --- |
| 自动化底座 | FIRERPA/LAMDA 10.x；10.8 候选，10.6 回滚基线 | 客户端-服务端、选择器/Watcher/虚拟屏/远控/APK API 统一；比设备内脚本运行器更适合集中调度。 |
| 业务后端 | Python 3.12 + FastAPI + SQLAlchemy 2 + Pydantic 2，模块化单体 | 与 LAMDA Python 客户端同语言，第一版降低分布式复杂度；领域边界清晰，后续可拆分。 |
| 持久工作流 | Temporal | 定时、重试、暂停、取消、补偿、人工审批和崩溃恢复均可持久化；适合长时间设备任务。 |
| 主数据库 | PostgreSQL 18.x | 事务、行锁、SKIP LOCKED、JSONB、审计与 outbox；可使用 UUIDv7。 |
| 前端 | Vue 3 + TypeScript + Vite + Pinia + TanStack Query；Studio 使用 Monaco | 后台表单/表格开发效率高，类型安全；Studio 可做断点、变量、脚本和 Selector 调试。 |
| 边缘连接 | Edge Gateway 主动出站 mTLS gRPC 双向流 | 不把设备端口暴露到公网；支持 NAT、断线续传、命令确认、事件回放与本地缓存。 |
| Android 二开 | 独立 Kotlin + Jetpack Compose 伴生 App；可选 Android Enterprise DPC | 不把业务代码动态塞进官方服务端；负责入网、状态、权限引导、人工确认和紧急停止。 |
| 对象存储 | S3 兼容存储 | 统一保存 APK、图片、视频、自动化包、截图、UI 树、日志和审计证据。 |
| 可观测性 | OpenTelemetry + Prometheus/Grafana/Loki/Tempo | 统一 trace_id/run_id/device_id，定位“云端—边缘—手机”跨平面问题。 |

## 1.3 必须保留的五条可靠性规则

1. **设备单写者**：同一设备同一时刻只能有一个生产 Runner。控制层使用数据库 fencing token，边缘层使用进程隔离，设备层再持有 LAMDA 60 秒 API Lock，并每 20 秒续租。
2. **不可逆提交只执行一次**：发布按钮之前写入 `commit_intent`；点击或确认提交后绝不因超时自动重试，只进入结果对账。
3. **配置快照不可变**：每次任务固定内容修订、媒体哈希、自动化包版本、目标 App 版本、发布参数和审批记录。
4. **云端不能直连手机**：设备 65000/tcp 只允许边缘网关访问，浏览器不持有 PEM，远程桌面必须经边缘代理。
5. **真实设备证据是完成条件**：模拟器和 Mock 可证明代码路径，但不能替代 Android/LAMDA/目标 App 的真机验收。

![三平面总体架构](assets/architecture.png){ width=95% }

# 2. 对标样板调研与范围收敛

## 2.1 样板证据概览

上传包是一套自包含的网页与教程证据：包含菜单清单、114 份页面模板、结构化页面矩阵、教程画面/转写、模块规格、路由任务和实施建议。对标包自身也明确建议独立实现，不复用原站 Cookie、令牌、私有 API 或后端。

| 一级路由 | 页面数 | 与本项目关系 | 处理意见 |
| --- | --- | --- | --- |
| task | 40 | 包含任务队列、发布、设备绑定、重启及大量外围运营任务 | 保留任务队列、发布、设备初始化/重启；其余按风险和需求延期。 |
| goods | 27 | 商品编辑、采集、导入、列表 | 第一版仅保留内容/作品通用模型；采集和跨站解析不做。 |
| im | 11 | 自动回复、快捷语、素材消息 | 延期；未来默认人工确认，不做未授权自动群发。 |
| set | 11 | 图片/视频/音频素材、水印、用户设置 | 保留媒体库、水印、安全与系统设置。 |
| home | 8 | 设备、授权、工具、更新日志 | 保留仪表盘、设备、工具/调试、版本状态。 |
| post | 4 | 内容编辑、列表、分组、发布入口 | 完整保留并升级为通用作品域。 |
| order/idea/count/app/system | 13 | 订单、采购、创意、统计、通知、反馈 | 除基础通知/审计外，全部延期。 |

![样板主页实拍](assets/benchmark_home.png){ width=88% }

## 2.2 第一版 18 个核心页面

| 序号 | 页面 | 第一版职责 | 样板来源 |
| --- | --- | --- | --- |
| 01 | 运营仪表盘 | 设备在线、任务、发布成功率、告警、版本分布 | home/main |
| 02 | 设备列表 | 在线状态、能力、Android/LAMDA/目标 App 版本、边缘节点 | home/device_info |
| 03 | 设备详情/远控 | 健康、日志、远程画面、UI 树、文件、当前租约 | home/tools + 新增 |
| 04 | 账号与授权 | 授权账号、设备绑定、状态检查、人工确认 | home/authorize + task/xy_task/xy_init |
| 05 | 作品列表 | 草稿、已审批、已发布、修订、分组、归档 | post/list |
| 06 | 作品编辑器 | 标题、正文、媒体排序、话题、地点、平台字段 | post/edit |
| 07 | 作品分组 | 分组、标签、归档策略 | post/group |
| 08 | 媒体素材库 | 图片、视频、音频、哈希去重、转码、引用 | set/material/image\|video\|audio |
| 09 | 水印与派生规则 | 不覆盖原件的派生图、位置/透明度/预览 | set/system/watermark |
| 10 | 发布计划创建 | 内容、账号、设备、时间、间隔、风控、审批 | task/*/post_add 与 goods_add2 |
| 11 | 发布计划详情 | 不可变快照、目标矩阵、幂等键、审批和取消 | 新增 |
| 12 | 任务队列 | 排队、运行、成功、部分成功、失败、取消 | task/run |
| 13 | 任务运行详情 | 步骤、日志、证据、错误分类、精确重试 | task/run + 新增 |
| 14 | 自动化包列表 | 版本、签名、兼容矩阵、灰度、回滚 | 新增 |
| 15 | 自动化调试 Studio | 远控、Selector、UI 树、单步、断点、变量、证据 | home/tools 升级 |
| 16 | APK 仓库 | 包名、版本、签名人、ABI、SDK、哈希、SBOM | 新增 |
| 17 | APK 灰度部署 | 设备批次、安装会话、验证、停止、回滚 | 新增 |
| 18 | 系统/安全/审计 | OIDC、RBAC、证书、密钥引用、审计、告警 | set/user + system/feedback 升级 |

## 2.3 明确不进入第一版的能力

- 跨平台页面/店铺/商品批量采集、私有接口调用、协议恢复。
- 养号、随机浏览、流量制造、批量点赞/留言/消息、风控规避、验证码绕过、设备指纹伪装。
- 自动采购、自动发货、订单关闭/退款等高风险交易动作。
- 在生产设备启用任意 shell、ADB、SSH、Frida、MITM、代理篡改或动态注入。实验室安全研究能力必须独立网络、独立权限、独立审计。
- 在浏览器直接暴露 FIRERPA/LAMDA 服务端或将设备证书下发给最终用户。

# 3. LAMDA/FIRERPA 调研结论与采用边界

## 3.1 当前版本与稳定策略

调研日 PyPI 最新版本为 `lamda 10.8`，发布日期为 2026-08-30，Python 要求为 3.6–3.14，源码包 SHA256 为 `b5f32ffebdb186b58cdf770f0d6caa4a5b515afb44bfa9c50386ea9a5bd17ea7`。上一版本 10.6 发布于 2026-08-16。由于 10.8 在调研当天刚发布，不能直接把“最新”理解为“已在本项目中稳定”：建议将 10.8 设为候选通道，完成 72 小时真机 soak、发布回归和远控回归后再提升；10.6 作为首个回滚基线。

| 通道 | LAMDA 版本 | 用途 | 进入条件 |
| --- | --- | --- | --- |
| stable | 10.6 或经验证的 10.8 | 生产设备默认 | 兼容矩阵通过；72 小时 soak；回滚验证完成。 |
| candidate | 10.8 | 5%–10% 灰度设备 | 安装、UI、发布、远控、锁和证书全部通过。 |
| lab | 最新 10.x | 实验室能力评估 | 隔离 VLAN；不可触达生产账号和内容。 |
| rollback | 10.6 | 紧急回退 | 镜像、包、证书和兼容自动化包已预置。 |

## 3.2 官方能力与本项目采用情况

| LAMDA/FIRERPA 能力 | 本项目采用 | 架构处理 |
| --- | --- | --- |
| 选择器、child/sibling、等待、截图、Unicode 输入、滑动 | 采用 | 只允许经签名自动化包通过 `lamda-driver` 调用。 |
| UI Watcher | 采用 | 用于处理授权弹窗、更新提示和明确允许的中断；Watcher 需要命名、计数和清理。 |
| 虚拟屏 | 条件采用 | 仅在机型/目标 App 兼容测试通过后启用；不把它当作默认并发机制。 |
| MJPEG/H.264/WebRTC 远程桌面、布局检查 | 采用 | MVP 反向代理官方 WebUI；后续可嵌入 WebSocket 流。 |
| APK 安装会话、单 APK/分包 APK | 采用 | 由 APK Rollout Workflow 调用，强制签名和版本校验。 |
| 文件、App 生命周期、设备状态 | 采用 | 按能力白名单暴露，不提供任意命令接口。 |
| Frida、MITM、代理、内置 ADB/SSH/终端 | 生产禁用 | 仅可在隔离实验室、书面授权和单独角色下开启；第一版不实现控制入口。 |
| MCP/Agent | 暂不直接接入生产 | 桌面智能体只调用本系统 API，不直连每台手机的 MCP。 |

## 3.3 Root 与非 Root

官方快速开始说明完整能力推荐 Root，但也支持 shell/非 Root，部分高权限能力会受限。工程上不能把“是否 Root”当作一个布尔标签，而应建立能力画像：`ui_automation`、`silent_install`、`virtual_display`、`file_privileged`、`service_autostart`、`remote_stream_h264` 等逐项探测。调度器只把任务分配给满足自动化包 `requiredCapabilities` 的设备。

## 3.4 服务证书与 API Lock

官方文档明确指出 FIRERPA Server 默认不启用认证：同网段知道 IP 和端口的人可连接远程桌面、调用 API 或使用 SSH。因此所有纳管设备必须启用服务证书，且设备端口只允许边缘节点访问。官方 API Lock 默认 60 秒自动释放，建议周期刷新；本架构采用 60 秒锁、20 秒刷新，严禁为了“方便”设置数十分钟的长锁。

## 3.5 许可与二开边界

GitHub 客户端仓库使用 MIT 许可证，但这不自动等同于“设备端官方服务 APK、品牌、许可服务和商业分发均可随意重打包”。建议：

1. Python 客户端依赖及对其适配代码按仓库许可证处理，并保留许可证文本。
2. 官方 FIRERPA Server 按官方安装、升级和许可方式管理；不要在未取得书面授权时做白标、ROM 预装或重新分发。
3. 自研 Kotlin 伴生 App 使用独立包名、签名、发布流水线和隐私声明，不动态加载自动化业务代码。
4. 在采购或规模部署前，向供应方确认设备数量、离线许可、商业用途、升级和支持条款。

# 4. 建设目标、非目标与工程约束

## 4.1 建设目标

- 在单一后台中管理租户、设备、授权账号、作品、媒体、APK、自动化包、发布计划和任务证据。
- 支持立即、定时、每日窗口和批次发布，进程或服务器重启后仍可恢复。
- 支持可视化远控、UI 树/Selector 调试、单步执行、断点、变量和截图差异。
- 支持 APK 入库、签名/版本/ABI/SDK 分析、分批安装、验证、停止和回滚。
- 任何不可逆动作可追溯到操作者、审批、内容修订、自动化包、设备、账号和证据。
- 桌面智能体可以根据机器可读任务 DAG 独立推进，并用命令和证据证明完成。

## 4.2 非目标

- 不追求绕过第三方平台的服务条款或技术保护。
- 不保证所有目标 App 的所有历史版本兼容；通过支持矩阵明确范围。
- 第一版不做复杂微服务和 Kubernetes 强依赖；先保证核心闭环和设备可靠性。
- 不把“远程控制成功”视为“业务发布成功”；必须执行结果对账。

## 4.3 约束

| 约束 | 设计响应 |
| --- | --- |
| 设备常在 NAT/局域网内 | 边缘网关主动出站连接；云端不入站扫描设备。 |
| 移动 UI 易变化 | 版本化 Locator 包、语义优先、截图/UI XML 证据、兼容矩阵和快速回滚。 |
| 任务可能持续数分钟至数小时 | Temporal 持久化工作流；Activity 心跳、取消和超时。 |
| 提交动作不可幂等 | commit intent + 单次提交 + 对账；提交步骤不自动重试。 |
| 设备只能单写 | 数据库 fencing lease + LAMDA API Lock + 边缘单 Runner。 |
| 媒体/APK 体积大 | 对象存储 + 预签名 URL + 边缘缓存 + SHA256 校验。 |
| 新 LAMDA 版本频繁 | stable/candidate/lab 通道；依赖锁定、镜像摘要、兼容测试和回滚。 |

# 5. 架构原则

| 编号 | 原则 | 落实方式 |
| --- | --- | --- |
| P1 | 控制与执行分离 | 云端保存意图和状态，边缘执行设备动作；任何设备调用都经受控适配器。 |
| P2 | 单一事实源 | PostgreSQL 是业务状态源；Temporal 是工作流执行历史；对象存储是证据源。 |
| P3 | 不可变快照 | 任务启动后不读取“当前作品”或“当前脚本”，而读取固定修订。 |
| P4 | 至少一次编排，业务侧幂等 | Activity 允许重试；每个外部动作有幂等键或明确的不可重试策略。 |
| P5 | 最小权限 | 角色、设备能力、自动化包能力、目标 App 和环境都按白名单授权。 |
| P6 | 可审计优先 | 每次审批、命令、锁、上传、提交、取消、回滚和人工接管都写审计。 |
| P7 | 生产/实验室隔离 | 高风险调试能力不与生产设备、账号和网络共用控制入口。 |
| P8 | 边缘自治但不独立决策 | 断网可安全完成已接受步骤并缓存证据，但不能自行创建新业务任务。 |
| P9 | 渐进复杂度 | 模块化单体 + Compose 起步；当吞吐和组织边界真实出现再拆服务/Kubernetes。 |
| P10 | 自动化可替换 | 业务层依赖 Driver Protocol，不依赖 LAMDA 具体对象，未来可接模拟器或其他合规驱动。 |

# 6. 总体架构

## 6.1 三平面职责

| 平面 | 部署位置 | 核心组件 | 禁止事项 |
| --- | --- | --- | --- |
| 控制平面 | 云端/VPC | Web、Control API、Temporal、PostgreSQL、对象存储、OIDC、可观测性 | 禁止直接持有设备网络可达性；禁止绕过边缘调用 LAMDA。 |
| 边缘执行平面 | 手机所在局域网/机房 | Edge Gateway、Runner Pool、LAMDA Driver、Remote Proxy、Artifact Cache、Local Spool | 禁止接受公网任意入站；禁止把 PEM 下发浏览器。 |
| Android 设备平面 | 真实手机/授权模拟环境 | 官方 FIRERPA/LAMDA Server、自研伴生 App、目标 App | 禁止动态加载未经签名的业务代码；禁止默认开启高风险研究能力。 |

## 6.2 主请求流

1. 用户在 Web 创建作品或上传 APK，文件进入对象存储，元数据和哈希进入 PostgreSQL。
2. 用户创建发布计划，Control API 做验证、风险检查和审批，生成不可变 `PublishSnapshot`。
3. API 以业务幂等键启动 Temporal Workflow；Workflow 选择设备并创建带 fencing token 的设备租约。
4. Temporal Activity 通过 Edge Hub 向目标 Edge Gateway 发命令；Gateway ACK 后由隔离 Runner 执行。
5. Runner 持有 LAMDA 服务证书，申请 60 秒 API Lock 并续租；媒体从边缘缓存推送到手机。
6. 自动化包按状态机运行，逐步上传截图、UI XML、日志、App/设备状态。
7. 提交前写 `commit_intent`；提交动作最多执行一次；之后通过 UI/本地记录/允许的官方结果渠道对账。
8. Workflow 汇总目标结果，写审计与 outbox，Web 通过 SSE/WebSocket 获取进度。

## 6.3 组件图解释

- **Caddy/WAF/OIDC**：TLS、反向代理、安全头、速率限制和身份接入。
- **Control API**：模块化单体，提供租户、设备、账号、作品、发布、APK、自动化包和审计模块。
- **Temporal**：只保存确定性编排；数据库访问、对象存储、LAMDA、审批通知均放入 Activity。
- **Edge Hub**：云端的双向流会话管理，不执行设备业务。
- **Edge Gateway**：出站连接、证书、设备发现、任务落盘、Runner 调度、缓存和远控代理。
- **Runner**：每个设备一个进程/容器，崩溃不影响同边缘其他设备。
- **Companion App**：展示状态并提供用户可见的授权/停止，不承担 Python 自动化解释器。

# 7. 技术栈与版本策略

## 7.1 推荐基线

| 层 | 推荐技术 | 版本原则 |
| --- | --- | --- |
| Web 管理台 | Vue 3.x、TypeScript 5.x、Vite、Vue Router、Pinia、TanStack Query、Zod、ECharts | 锁 major/minor；通过 Renovate/Dependabot 升级。 |
| 调试 Studio | 同一 Vue 工程或独立 package；Monaco Editor、xterm.js、Canvas/WebCodecs（H.264 可选） | MVP 可先代理官方 WebUI，减少协议实现风险。 |
| 桌面壳 | Tauri 2（可选） | 需要本地 USB/ADB 辅助或一体化桌面体验时启用；Web 仍是主产品。 |
| Control API | Python 3.12、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、httpx、structlog | 生产 Python 固定 3.12；LAMDA 10.8 虽支持至 3.14，也不在首版追新解释器。 |
| Workflow | Temporal Python SDK + Temporal Server/Cloud | 固定 SDK 和 Server 兼容版本；Workflow 变更使用 Worker Versioning。 |
| 数据库 | PostgreSQL 18.6 | 版本 18 为当前稳定大版本；生产固定镜像摘要与补丁升级窗口。 |
| 缓存/速率 | Valkey 或 Redis（可选） | 不作为任务事实源；只用于速率、短缓存、通知扇出。 |
| 对象存储 | S3 兼容：云厂商 S3/MinIO 等 | 启用版本、生命周期、SSE/KMS、对象锁按合规需要。 |
| Edge | Python 3.12、grpc.aio、SQLite/WAL 本地 spool、systemd 或 Docker | Edge 与 LAMDA 客户端版本一起发布。 |
| Android | Kotlin、Jetpack Compose、WorkManager、Room、Android Keystore | minSdk 29（Android 10）；targetSdk 依发布时最新要求。 |
| 入口 | Caddy | 自动 TLS/反代；生产 WAF/OIDC 可使用云服务或独立组件。 |
| 可观测性 | OpenTelemetry Collector、Prometheus、Grafana、Loki、Tempo | 应用只发 OTLP，后端可替换。 |
| 测试 | pytest、Hypothesis、Playwright、Testcontainers、k6、Android instrumentation | 真机矩阵测试为发布门禁。 |

## 7.2 为什么第一版采用模块化单体

设备自动化系统真正困难的部分是跨平面的状态一致性、设备锁、不可逆提交、证据和兼容性，而不是服务拆分。第一版将 Control API 作为模块化单体，使用独立 Python package、数据库 schema/表边界、领域事件和内部接口；Temporal Worker、Edge Hub 和 Edge Gateway 作为独立部署进程。只有当团队、吞吐或隔离要求真实出现时，再把媒体、APK、设备或通知模块拆成服务。

## 7.3 依赖锁定与升级

- Python：`uv.lock` 或 `poetry.lock`；容器中使用 hash 校验；LAMDA sdist/wheel 记录 SHA256。
- Node：`pnpm-lock.yaml`，CI 使用 `--frozen-lockfile`。
- 容器：引用不可变 digest，不只使用 `latest`。
- Android：Gradle version catalog + dependency verification。
- 自动化包：自身 SemVer、LAMDA 区间、目标 App 区间、Android 区间和签名。
- 每月常规升级，紧急安全升级单独通道；所有升级必须经过 candidate 设备。

# 8. 核心领域模块

| 模块 | 职责 | 关键边界 |
| --- | --- | --- |
| identity | 租户、用户、OIDC 映射、角色、权限、会话、MFA 状态 | 不保存 IdP 密码。 |
| device | 边缘节点、设备、能力、版本、心跳、标签、维护状态 | 设备地址和证书仅边缘可见。 |
| account | 平台账号授权记录、设备绑定、状态、人工确认 | 不收集不必要凭据；密钥只存 secret_ref。 |
| content | 作品、修订、平台字段、分组、审核状态 | 任务只引用不可变修订。 |
| media | 对象、哈希、元数据、派生、转码、水印、病毒扫描 | 原件不可覆盖。 |
| publish | 计划、快照、目标、审批、幂等键、结果、对账 | 提交步骤禁止自动重试。 |
| task | 任务定义、运行、步骤、租约、日志、取消、重试 | 设备租约必须带 fencing token。 |
| automation | 包、版本、manifest、签名、兼容矩阵、灰度 | 未签名包不能进入生产。 |
| apk | APK/splits、包信息、签名、SBOM、部署批次、安装会话 | 禁止降级/换签名，除非明确审批。 |
| studio | 调试会话、远控代理、断点、变量、Selector、录制证据 | 生产会话短时、只对授权设备。 |
| audit | 不可变审计、审批、命令、证据索引、安全事件 | 审计与业务删除策略分离。 |
| notification | 告警、审批通知、任务摘要 | 不参与业务事实判断。 |

## 8.1 模块通信

模块内优先同步调用；需要跨事务或异步传播的事件通过 PostgreSQL transactional outbox 写入。Outbox Dispatcher 将事件投递到 Temporal、通知或 Web 推送；处理方按 `event_id` 去重。不要在业务事务中直接调用 Edge、对象存储回调或第三方通知。

# 9. 边缘网关详细设计

## 9.1 Edge Gateway 进程模型

| 子组件 | 职责 | 持久化 |
| --- | --- | --- |
| Control Stream | 出站 mTLS gRPC；注册、心跳、命令 ACK、事件、取消、重放 | 会话序号与最后 ACK。 |
| Device Registry | 发现/配置设备、能力探测、版本采集、维护状态 | SQLite 设备镜像。 |
| Scheduler | 校验设备租约和 fencing token；把命令派发到对应 Runner | 本地命令队列。 |
| Runner Supervisor | 每设备单进程；超时、重启、资源限额、日志收集 | 运行状态和退出原因。 |
| Artifact Cache | APK/媒体/自动化包按 SHA256 缓存，支持 LRU 与预热 | 文件 + 索引。 |
| Evidence Spool | 断网缓存截图、UI XML、日志、结果，恢复后重传 | SQLite/WAL + 文件。 |
| Remote Proxy | 短期调试会话，代理 WebUI/视频/输入，不泄露设备证书 | 短期 session/token。 |
| Cert Store | 边缘身份私钥、设备服务证书引用 | OS secret/TPM/权限 0600。 |

## 9.2 入网与身份

1. 管理员在云端创建一次性 Enrollment Token，绑定租户、站点和有效期。
2. `edge-install.sh` 生成边缘密钥并用 Token 换取边缘客户端证书；Token 立即失效。
3. Edge 使用 mTLS 连接 Edge Hub，证书 Subject/SAN 映射 `edge_id`，云端校验吊销状态。
4. 设备通过 USB/LAN/静态清单进入 Edge Registry；为每台设备导入或生成 LAMDA 服务证书。
5. Edge 只上报设备逻辑 ID、能力、版本和健康，不上报私钥。

## 9.3 双向流与重放

- 云端每条命令含 `command_id`、`edge_id`、`device_id`、`lease_id`、`fencing_token`、`deadline`、`artifact_refs` 和 `payload`。
- Edge 先持久化再 ACK `RECEIVED`；Runner 接受后 ACK `STARTED`；步骤持续发 `EVENT`；最终 `SUCCEEDED/FAILED/CANCELED`。
- 命令和事件各自使用单调 sequence；重连时双方声明最后确认序号并回放缺口。
- Edge 发现 fencing token 低于本地已见最大值时必须拒绝，防止旧 Worker 复活后继续控制设备。
- 云端取消是协作式：Runner 在安全检查点停止；已写 commit intent 的提交阶段只能停止后续动作，不能重复或“撤回”点击。

## 9.4 本地数据与断网策略

Edge 不成为第二套业务数据库。允许持久化的仅包括已接收命令、ACK/事件、租约镜像、缓存索引、证据上传队列和设备健康。断网时：

- 未开始命令不自行启动，除非命令明确包含离线可执行窗口且租约仍有效。
- 已开始且未到提交点的任务可在安全策略允许时完成当前幂等步骤。
- 到达不可逆提交点但无法联系云端时，默认等待；超时后进入人工确认，不擅自提交。
- 所有证据落盘并校验哈希；恢复连接后按优先级上传最终状态、commit evidence、日志和大文件。

## 9.5 资源隔离

- 每台设备一个 Runner 进程；使用 cgroup/systemd 限制 CPU、内存、打开文件和进程数。
- Runner 只可访问对应设备地址、缓存目录和一次性 secret handle。
- 自动化包在只读虚拟环境中运行，写入临时工作目录；完成后销毁。
- Edge Gateway 主进程不导入目标自动化包，避免包崩溃拖垮控制流。

# 10. LAMDA 驱动层与设备会话模型

## 10.1 包边界

所有对 `lamda` 包的 import 必须只出现在 `packages/lamda-driver`。Control API、Workflow、Web、内容模块不得直接依赖 LAMDA 类型。自动化包依赖本系统定义的 `DeviceDriver` Protocol，从而可用 `MockDriver` 做测试，并在未来替换底层。

```python
from typing import Protocol, BinaryIO, Mapping, Sequence

class DeviceDriver(Protocol):
    def get_capabilities(self) -> Mapping[str, object]: ...
    def start_app(self, package: str) -> None: ...
    def stop_app(self, package: str) -> None: ...
    def selector(self, locator: "Locator") -> "Element": ...
    def screenshot(self) -> bytes: ...
    def dump_ui(self) -> str: ...
    def push_file(self, source: BinaryIO, remote_path: str, sha256: str) -> None: ...
    def install_apk_session(self, artifacts: Sequence["ApkPart"], options: "InstallOptions") -> "InstallResult": ...
    def create_virtual_display(self, spec: "DisplaySpec") -> "DeviceDriver": ...
```

## 10.2 设备会话封装

> 下列代码是架构伪代码。`Device` 构造参数和个别私有锁方法以项目锁定的 LAMDA 版本为准；适配层必须用集成测试固定真实签名，不允许业务代码复制这些细节。

```python
class LamdaSession:
    LOCK_SECONDS = 60
    REFRESH_SECONDS = 20

    def __enter__(self):
        self._verify_fencing_token()
        self.device = self._connect_with_service_certificate()
        self.device._acquire_lock(leaseTime=self.LOCK_SECONDS)
        self._refresh_task = start_periodic(
            every=self.REFRESH_SECONDS,
            fn=lambda: self.device._refresh_lock(leaseTime=self.LOCK_SECONDS),
        )
        self._assert_expected_device_identity()
        return LamdaDriver(self.device)

    def __exit__(self, exc_type, exc, tb):
        stop_periodic(self._refresh_task)
        try:
            self.device._release_lock()
        finally:
            self._close_channel()
```

## 10.3 锁顺序

锁必须按固定顺序获取，避免死锁和旧实例继续操作：

1. Temporal Workflow 保证同业务目标只启动一个活动链。
2. PostgreSQL `device_lease` 原子更新并返回递增 `fencing_token`。
3. Edge Gateway 校验 token，并确认本设备无活跃 Runner。
4. Runner 连接 LAMDA，获取 60 秒 API Lock。
5. 执行前再次检查云端 lease 未取消/过期。
6. 释放顺序相反；即使 LAMDA 连接异常，也必须在数据库租约到期前停止 Runner。

## 10.4 Locator 策略

| 优先级 | 定位方式 | 说明 |
| --- | --- | --- |
| 1 | resourceId + packageName | 最稳定；允许版本化候选列表。 |
| 2 | text/description + className | 需考虑本地化、动态文案和可访问性。 |
| 3 | child/sibling/层级关系 | 处理重复节点；避免依赖绝对深度。 |
| 4 | OCR 文本区域 | 仅在无标准节点时使用，记录置信度和截图。 |
| 5 | 图像匹配 | 模板需版本化；受主题、分辨率和缩放影响。 |
| 6 | 相对/绝对坐标 | 最后手段；必须绑定分辨率、方向和截图证据。 |

每个 Locator 定义 `primary`、`fallbacks`、`timeout`、`assertions` 和 `diagnostics`。如果使用低优先级方式成功，要产生 `locator_degraded_total` 指标，促使维护者修复语义定位。

## 10.5 Watcher 生命周期

- Watcher 只能处理已知且合法的中断，如权限提示、明确的更新提示、网络错误提示。
- 每次任务前注册，任务后无条件清理；名称包含包版本和自动化包版本。
- Watcher 触发计数进入证据；超过阈值认为 UI 异常并熔断。
- 禁止使用 Watcher 自动处理验证码、账号异常核验、交易确认或不可逆提交。

# 11. Android 伴生 App 与企业设备管理

## 11.1 伴生 App 职责

- 扫码/输入 Enrollment Code，将设备逻辑 ID 与租户/边缘站点绑定。
- 展示 FIRERPA/LAMDA 服务状态、边缘连接、目标 App 版本、权限和当前任务。
- 引导用户完成 Root/Shizuku/系统权限配置，但不伪装或绕过系统提示。
- 对高风险步骤展示用户确认；提供始终可见的“停止自动化”按钮。
- 接收受签名保护的自身更新信息，做版本检查和升级引导。
- 将设备健康、充电、网络、温度、存储等可公开状态发给 Edge；不采集无关联系人、短信或位置。

## 11.2 不承担的职责

- 不作为 AutoJS 替代脚本解释器，不动态下载并执行 Python/JS 业务脚本。
- 不保存 LAMDA 服务私钥；证书由 Edge 管理。
- 不直接接收云端任意命令；只与本机/边缘的受控 API 交互。
- 不实现隐藏图标、静默常驻、反卸载或其他对用户不透明行为。

## 11.3 可选 Android Enterprise DPC

对于公司自有、专用且可重置的设备，可增设 DPC/device-owner 变体，用于 kiosk、允许列表、受控安装和配置。Android 官方说明专用设备应是由管理员组件完全托管的公司设备；因此 DPC 不能用于员工私人设备，也不能默认加入普通伴生 App。

| 设备类型 | 建议模式 | 安装/权限策略 |
| --- | --- | --- |
| 普通授权手机 | 标准伴生 App + FIRERPA Root/Shizuku/非 Root | 用户可见授权；安装 APK 可能需要用户确认。 |
| 公司专用设备 | 可选 DPC/device owner + 伴生 UI | 可按 Android Enterprise 能力做受控安装、kiosk 和策略。 |
| 实验室设备 | 隔离的 lab profile | 可启用额外诊断，但不能连接生产账号与内容。 |

## 11.4 包与签名

- `com.company.cloudctl.companion`：普通伴生 App。
- `com.company.cloudctl.dpc`：可选企业 DPC，单独签名/发布/审计。
- 官方 FIRERPA Server 保持官方包与更新渠道；与自研包不合并。
- Release 签名密钥放在 HSM/KMS 或受控 CI，开发者本地不能取得生产私钥。

# 12. APK 管理、分析与自动部署

## 12.1 APK 入库流水线

1. 上传单 APK、`.apks`/split 集合或从受控构建流水线推送。
2. 计算 SHA256，进行恶意文件扫描和 MIME/ZIP 结构校验。
3. 使用 `apkanalyzer`/`aapt2`/`apksigner` 提取包名、versionCode/versionName、min/target SDK、ABI、权限、签名证书摘要和 split 关系。
4. 生成 CycloneDX/SPDX SBOM；记录构建来源、Git commit、CI run 和签名主体。
5. 与现有版本比较：是否降级、是否换签名、是否权限新增、是否 ABI 不兼容。
6. 只有通过策略且被批准的 Artifact 才可进入 rollout。

## 12.2 数据对象

| 对象 | 关键字段 |
| --- | --- |
| ApkArtifact | id, sha256, size, package_name, version_code, version_name, signer_sha256, min_sdk, target_sdk, source, state |
| ApkPart | artifact_id, split_name, abi, density, language, object_key, sha256 |
| ApkPolicyResult | permission_diff, signer_match, downgrade, sbom_ref, scan_ref, decision |
| Rollout | artifact_id, cohort_query, batch_size, pause_between_batches, failure_threshold, approval_id |
| InstallSession | device_id, rollout_id, lamda_session_id, state, progress, previous_version, evidence_ref |

## 12.3 安装与验证

LAMDA 官方 App Operations 支持创建安装会话、写入并提交，也支持单 APK 和 split APK。实现时每个设备执行：

1. Preflight：设备在线、存储、电量、Android/ABI、签名和版本策略。
2. 下载：Edge 从对象存储下载并验证每个 part 的 SHA256。
3. 安装会话：按 part 写入，提交后轮询状态；安装提示只能由允许的 Watcher 或用户处理。
4. 验证：枚举已安装 App，确认包名、版本、签名；启动应用并做健康探针。
5. 观察窗口：收集崩溃、启动时间、心跳和关键自动化 smoke。
6. 达到失败阈值自动暂停后续批次，不自动“强推”。

## 12.4 回滚

- 回滚并不总能无损保留数据；发布前必须声明 `rollback_strategy`：覆盖安装、卸载重装、备份恢复或不可回滚。
- 目标 App 若禁止降级，不能通过高权限强行绕过；应恢复上一个受支持构建或人工处理。
- 每个 rollout 预先选择回滚 Artifact，并在 Edge 缓存。
- 换签名、数据迁移或数据库 schema 不兼容的 APK 必须单独变更流程。

# 13. 自动化调试 Studio

![自动化调试 Studio 组件关系](assets/debug_studio.png){ width=92% }

## 13.1 核心工作区

| 区域 | 第一版能力 |
| --- | --- |
| 设备/会话栏 | 选择边缘与设备、创建 15–30 分钟短期调试会话、查看租约与占用者。 |
| 远程画面 | MVP 代理官方 WebUI；后续 MJPEG/H.264 Canvas，支持点击、滑动、按键和旋转。 |
| 布局与 Selector | UI XML 树、节点属性、屏幕高亮、生成 resource/text/child-sibling locator。 |
| 脚本编辑器 | Monaco、类型提示、manifest/schema 校验、只编辑自动化包源。 |
| 步骤执行 | 运行到光标、单步、暂停、安全取消；提交步骤前强制提示。 |
| 变量/日志 | 结构化变量、RPC 时间、重试、Watcher、当前 App、屏幕、异常栈。 |
| 证据 | 手工截图、自动截图、UI XML、locator 诊断、步骤时间线、导出调试包。 |
| 兼容测试 | 同一脚本对多设备/多 App 版本运行只读 smoke，不默认执行发布。 |

## 13.2 会话安全

- Studio 请求云端签发一次性 `debug_session_id`，关联用户、设备、用途、有效期和允许能力。
- Edge 通过既有 mTLS 流收到会话授权，在本地开临时反向代理；浏览器只得到云端同源的短 token。
- 调试会话不能抢占生产 Runner；需要管理员显式“进入维护”，等待当前安全点后释放租约。
- 生产环境隐藏 terminal/shell/Frida/MITM 等入口；lab 环境也必须单独权限和完整审计。
- 远控输入、截图和导出均写审计；敏感屏幕可按租户策略打码。

## 13.3 录制与生成代码

Recorder 只记录高层动作：点击的节点属性、输入目标、滚动容器、App 状态和前后截图。生成代码时优先语义 Locator，不保存原始绝对坐标；生成的脚本必须经过人工审阅和测试，不能直接从录制一键进入生产。

## 13.4 断点限制

- 普通幂等步骤可暂停和重新执行。
- 一旦进入 `COMMIT_INTENT_WRITTEN`，Studio 禁止“回退并重放”提交。
- 断点超过会话有效期时，Runner 安全退出并释放 LAMDA 锁。
- 设备断线后恢复必须重新读取 UI 状态，不能假定停在原界面。

# 14. 自动化包与 SDK 规范

## 14.1 包结构

```text
automation-package/
├── manifest.yaml
├── src/
│   ├── entrypoint.py
│   ├── workflows/publish.py
│   └── pages/editor.py
├── locators/
│   ├── app-12.4.yaml
│   └── app-12.5.yaml
├── schemas/
│   └── parameters.schema.json
├── tests/
│   ├── unit/
│   ├── replay/
│   └── fixtures/
├── assets/
└── SIGNATURE.ed25519
```

## 14.2 Manifest 必备字段

```yaml
apiVersion: cloudctl.example/v1
kind: AutomationPackage
metadata:
  name: authorized-content-publisher
  version: 1.4.2
spec:
  entrypoint: src.entrypoint:run
  runtime:
    python: ">=3.12,<3.13"
    lamda: ">=10.6,<11"
    android: ">=10,<=17"
  targets:
    - packageName: com.example.target
      versions: ">=12.4,<13"
  capabilities:
    required: [ui.selectors, app.lifecycle, file.push, screenshot, ui.dump]
    optional: [ui.watcher, virtual_display]
    forbidden: [shell.arbitrary, frida, mitm, proxy.mutate, adb.remote]
  parametersSchema: schemas/parameters.schema.json
  locators: [locators/app-12.4.yaml, locators/app-12.5.yaml]
  timeouts:
    runSeconds: 900
    stepSeconds: 60
  evidence:
    screenshot: [preflight, before_commit, after_commit, failure]
    uiDumpOnFailure: true
  submitPolicy:
    mode: commit-intent-single-shot
  signature:
    algorithm: Ed25519
    keyId: automation-prod-2026-01
```

## 14.3 能力模型

自动化包不能获得“整个 Device 对象”。Runner 按 manifest 生成 Capability Token，并把受限 Driver 暴露给包。包请求超出能力时在边缘直接拒绝。能力既用于安全，也用于调度兼容性。

## 14.4 生命周期钩子

- `validate(context)`：纯校验，无设备副作用。
- `preflight(driver, context)`：设备/App/账号/权限检查，只读或可逆。
- `prepare(driver, context)`：推送媒体、打开 App、导航和填表。
- `before_commit(driver, context)`：保存截图/UI XML，校验所有字段并请求确认。
- `commit_once(driver, context)`：不可重试提交；必须先存在 commit intent。
- `reconcile(driver, context)`：识别成功/失败/未知，不点击提交。
- `cleanup(driver, context)`：清理 Watcher、临时文件和 App 状态。

## 14.5 签名与发布

自动化包构建产出规范化 tar/zip、SHA256、SBOM、测试报告和 Ed25519 签名。Control API 校验签名后进入 registry；生产设备只信任生产公钥。撤销 key 时，Edge 同步撤销列表并拒绝新任务。旧任务是否继续由安全策略决定。

# 15. 内容、媒体与作品发布

![作品发布可靠工作流](assets/publish_workflow.png){ width=100% }

## 15.1 内容模型

- `ContentItem` 是逻辑作品；每次编辑生成 `ContentRevision`。
- `MediaAsset` 保存原件；水印、裁剪、转码生成 `MediaDerivative`，通过 `source_asset_id` 追溯。
- `PlatformPayload` 保存平台特定字段和验证结果，不污染通用内容。
- `PublishPlan` 是用户意图；`PublishSnapshot` 是批准后的不可变执行输入。
- 同一计划的每个账号/设备/时段形成 `PublishTarget`，结果独立。

## 15.2 发布创建步骤

1. 选择已冻结的内容修订及媒体派生版本。
2. 选择平台、授权账号、设备池或显式设备。
3. 选择立即/定时/窗口，配置目标间隔、最大并发和失败策略。
4. 平台适配器验证字段长度、媒体类型/尺寸、必要授权和目标 App 版本。
5. 生成预览，显示“将在哪台设备、哪个账号、何时、使用哪个自动化包发布什么”。
6. 按风险规则审批；保存 snapshot、幂等键和审批。
7. 启动 Temporal Workflow。

## 15.3 幂等键

```text
idempotency_key = SHA256(
  tenant_id + platform + account_id + content_revision_id +
  schedule_slot_utc + automation_package_version + target_policy_hash
)
```

同一个幂等键重复提交 API 返回原计划/Workflow，不创建第二份任务。`schedule_slot_utc` 是归一化后的执行窗口，而不是 API 请求时间。

## 15.4 可靠提交协议

普通 UI 步骤可通过观察状态决定是否重试，但“点击发布/确认”通常缺乏天然幂等性。必须使用：

1. `before_commit` 截图/UI XML，确认内容摘要和提交控件。
2. 在 PostgreSQL 事务中插入唯一 `commit_intent(target_id, attempt_no=1)`。
3. 将 intent 已持久化的 ACK 发给 Runner。
4. Runner 执行一次提交动作，随后立即生成屏幕和时间证据。
5. 无论 RPC 超时、Edge 断线还是客户端异常，均禁止再次执行提交动作。
6. 进入 `RECONCILING`：检查成功页、作品列表、草稿状态或允许的官方结果；结果为成功、失败或未知。
7. `UNKNOWN` 进入人工对账；人工可以标记结果或创建新的、显式批准的重试计划。

## 15.5 目标状态

| 状态 | 含义 | 允许操作 |
| --- | --- | --- |
| DRAFT | 计划编辑中 | 修改、删除。 |
| AWAITING_APPROVAL | 等待审批 | 批准、拒绝、撤回。 |
| SCHEDULED | 已持久化等待时间 | 取消、调整未来窗口需生成新 snapshot。 |
| QUEUED | 等待设备/账号租约 | 取消。 |
| RUNNING | 执行可逆步骤 | 协作取消、查看证据。 |
| WAITING_CONFIRMATION | 提交前人工确认 | 批准一次、拒绝。 |
| COMMITTING | 单次提交进行中 | 不允许重试/抢占。 |
| RECONCILING | 只读结果对账 | 等待、人工辅助。 |
| SUCCEEDED | 确认成功 | 查看证据。 |
| FAILED | 确认失败且未发布 | 按错误策略创建精确重试。 |
| UNKNOWN | 无法确认是否发布 | 人工对账，禁止自动重发。 |
| CANCELED | 在安全点取消 | 查看已执行步骤。 |

## 15.6 频控与公平调度

- 限制维度：租户、平台、账号、设备、自动化包和目标 App。
- 配额只用于合规和稳定，不用于规避平台检测。
- 调度优先级：人工调试/恢复 > 定时窗口 > 批量常规；同租户使用加权公平。
- 账号或设备连续出现授权异常、验证码、异常核验、未知提交结果时自动熔断并要求人工处理。

# 16. Temporal 工作流与状态机

## 16.1 为什么采用 Temporal

Temporal 将 Workflow Event History 持久化，Worker 崩溃后可重放恢复；Activity 默认具备重试，而 Workflow 必须保持确定性。此模型适合跨分钟/小时的设备任务和人工审批。外部 API、数据库、对象存储、LAMDA 和随机性都必须放在 Activity 中，Workflow 只做确定性决策。

## 16.2 Workflow 划分

| Workflow | 业务标识 | 职责 |
| --- | --- | --- |
| PublishPlanWorkflow | publish-plan/{plan_id} | 管理计划、定时、批次、审批、取消和总体结果。 |
| PublishTargetWorkflow | publish-target/{target_id} | 管理单账号/设备目标、租约、LAMDA 执行和对账。 |
| ApkRolloutWorkflow | apk-rollout/{rollout_id} | 分批安装、观察、阈值暂停、回滚。 |
| DeviceMaintenanceWorkflow | device-maint/{device_id}/{change_id} | 维护模式、服务更新、重启和健康验证。 |
| AutomationQualificationWorkflow | automation-qual/{package_version} | 在兼容矩阵执行只读/沙箱测试。 |

## 16.3 Publish Workflow 伪代码

```python
@workflow.defn
class PublishTargetWorkflow:
    @workflow.run
    async def run(self, snapshot: PublishTargetSnapshot) -> TargetResult:
        await workflow.execute_activity(validate_snapshot, snapshot)
        lease = await workflow.execute_activity(acquire_device_lease, snapshot)
        try:
            await workflow.execute_activity(edge_preflight, snapshot, lease)
            await workflow.execute_activity(stage_media, snapshot, lease)
            await workflow.execute_activity(run_prepare_steps, snapshot, lease)

            if snapshot.requires_human_confirmation:
                await self._wait_for_approval_signal()

            intent = await workflow.execute_activity(write_commit_intent, snapshot, lease)
            # 非幂等 Activity：maximum_attempts=1
            await workflow.execute_activity(
                commit_once,
                intent,
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            return await workflow.execute_activity(reconcile_result, snapshot, lease)
        finally:
            await workflow.execute_activity(release_device_lease, lease)
```

## 16.4 Activity 重试矩阵

| Activity 类型 | 示例 | 重试策略 |
| --- | --- | --- |
| 纯读取/校验 | 读取对象、查询设备、拉健康 | 指数退避；有 deadline。 |
| 幂等写入 | 写日志、上传按哈希命名证据、upsert 状态 | 可重试；唯一键去重。 |
| 可观察 UI 动作 | 打开 App、导航、填表 | 先观察当前状态，再有限重试。 |
| 不可逆提交 | 点击发布/确认安装的不可幂等阶段 | maximum_attempts=1；失败后对账。 |
| 租约/锁 | 获取设备 lease | 短重试；冲突进入排队，不强抢。 |
| 人工审批 | 等待 Signal/Update | 不重试；带过期和取消。 |

## 16.5 历史大小与版本

- 大批次由 Parent Workflow 分页启动 Child Workflow，避免单个 Event History 膨胀。
- 长期计划使用 Continue-As-New，但不要让 Parent 在仍有未管理 Child 时直接继续。
- Workflow 代码变更使用 Worker Versioning；不能直接改动会改变历史命令序列的代码。
- Workflow ID 不包含账号名、手机号等敏感信息，只使用内部 UUID。

# 17. 数据架构

![核心数据模型](assets/data_model.png){ width=98% }

## 17.1 数据分层

| 存储 | 保存内容 | 不保存内容 |
| --- | --- | --- |
| PostgreSQL | 业务状态、修订、租约、幂等、审批、审计索引、outbox | 大图片/视频/APK 二进制。 |
| S3 对象存储 | 媒体、APK、自动化包、SBOM、截图、UI XML、日志归档 | 可查询业务状态。 |
| Temporal | Workflow Event History、Timers、Signals/Updates、Activity 结果 | 权威业务表和大证据。 |
| Edge SQLite/WAL | 命令镜像、ACK、spool、缓存索引、设备镜像 | 全局用户/作品/计划事实。 |
| Valkey/Redis | 短期速率、缓存、推送扇出 | 设备租约或任务最终状态。 |

## 17.2 核心表建议

```sql
create table device (
  id uuid primary key default uuidv7(),
  tenant_id uuid not null,
  edge_id uuid not null,
  logical_name text not null,
  android_version text,
  lamda_version text,
  target_app_versions jsonb not null default '{}',
  capabilities jsonb not null default '{}',
  state text not null,
  last_seen_at timestamptz,
  version bigint not null default 0,
  unique (tenant_id, logical_name)
);

create table device_lease (
  device_id uuid primary key references device(id),
  lease_id uuid not null,
  owner_workflow_id text not null,
  fencing_token bigint not null,
  expires_at timestamptz not null,
  canceled_at timestamptz
);

create table publish_snapshot (
  id uuid primary key default uuidv7(),
  tenant_id uuid not null,
  plan_id uuid not null,
  content_revision_id uuid not null,
  automation_package_version_id uuid not null,
  payload jsonb not null,
  payload_sha256 char(64) not null,
  approved_by uuid,
  approved_at timestamptz,
  created_at timestamptz not null default now()
);

create table commit_intent (
  id uuid primary key default uuidv7(),
  target_id uuid not null,
  attempt_no integer not null check (attempt_no = 1),
  fencing_token bigint not null,
  before_commit_evidence_id uuid not null,
  created_at timestamptz not null default now(),
  unique (target_id, attempt_no)
);

create table outbox_event (
  id uuid primary key default uuidv7(),
  aggregate_type text not null,
  aggregate_id uuid not null,
  event_type text not null,
  payload jsonb not null,
  occurred_at timestamptz not null default now(),
  published_at timestamptz
);
```

## 17.3 多租户策略

- 所有业务表含 `tenant_id`；服务层强制上下文，数据库可加 Row Level Security 作为纵深防御。
- 对象 key 使用不可猜测 ID 和租户前缀；预签名 URL 短时有效。
- Temporal namespace 可按环境隔离；大客户是否独立 namespace 在规模化后决定。
- 审计导出和数据删除以租户为单位，但安全审计按法务保留策略处理。

## 17.4 审计事件

审计事件至少包含：`event_id`、`tenant_id`、`actor_type/user_id/service_id`、`action`、`resource_type/id`、`request_id`、`workflow_id`、`device_id`、`edge_id`、`before_hash`、`after_hash`、`ip/user_agent`、`occurred_at` 和结果。敏感字段只记录摘要或掩码。

# 18. API、WebSocket 与事件合同

## 18.1 REST 资源

| 端点 | 职责 |
| --- | --- |
| POST /api/v1/media/uploads | 创建分片/预签名上传；完成后校验 SHA256。 |
| GET/POST /api/v1/content | 作品列表与创建。 |
| POST /api/v1/content/{id}/revisions | 生成新修订。 |
| POST /api/v1/publish-plans | 创建计划，要求 Idempotency-Key。 |
| POST /api/v1/publish-plans/{id}:submit | 冻结快照并进入审批/调度。 |
| POST /api/v1/publish-plans/{id}:cancel | 协作取消。 |
| GET /api/v1/task-runs/{id} | 运行与步骤/证据。 |
| POST /api/v1/task-runs/{id}:retry | 仅允许可重试目标，生成新运行。 |
| GET /api/v1/devices | 设备与能力。 |
| POST /api/v1/devices/{id}:maintenance | 进入/退出维护。 |
| POST /api/v1/debug-sessions | 创建短期调试会话。 |
| POST /api/v1/apk-artifacts | APK 元数据与上传。 |
| POST /api/v1/apk-rollouts | 创建灰度。 |
| POST /api/v1/automation-packages | 上传并校验签名。 |

## 18.2 API 约定

- 所有写请求使用 `X-Request-Id`；产生外部副作用的创建请求还必须有 `Idempotency-Key`。
- 使用 Problem Details 风格错误：`type, title, status, code, detail, correlation_id, retryable, fields`。
- 乐观并发使用 `ETag/If-Match` 或显式 `version`。
- 分页使用稳定 cursor；列表不可依赖 offset 跨大量实时数据。
- 时间一律 RFC3339 UTC；展示层本地化。
- OpenAPI 是前后端合同，客户端由生成器产生；禁止手写重复 DTO。

## 18.3 创建发布计划示例

```json
{
  "contentRevisionId": "018f...",
  "platform": "authorized-platform-adapter",
  "targets": [
    {"accountId": "018a...", "deviceSelector": {"labels": ["site-a", "stable"]}}
  ],
  "schedule": {"mode": "AT", "at": "2026-09-01T02:30:00Z"},
  "execution": {"maxConcurrency": 2, "minIntervalSeconds": 90},
  "approvalPolicy": "BEFORE_COMMIT",
  "automationPackage": {"name": "authorized-content-publisher", "version": "1.4.2"}
}
```

## 18.4 Web 进度事件

浏览器订阅 `/api/v1/events` 的 SSE 或 WebSocket。事件仅是展示加速，不是事实源；断线后按 `last_event_id` 补拉，必要时重新 GET 资源。事件示例：`task.run.updated`、`task.step.appended`、`device.health.updated`、`publish.target.needs_confirmation`、`apk.rollout.paused`。

## 18.5 Edge gRPC

配套 `specs/edge-control.proto` 给出消息骨架。协议要求：双向流、mTLS、序列号、ACK、deadline、fencing token、能力校验、证据引用和错误分类；不得设计任意 shell 字符串命令。

# 19. 云控 Web 信息架构与页面规格

## 19.1 导航

```text
总览
设备中心
  ├─ 设备列表
  ├─ 设备详情 / 远控
  ├─ 边缘节点
  └─ 账号与授权
内容中心
  ├─ 作品列表
  ├─ 作品编辑
  ├─ 分组/标签
  ├─ 媒体素材
  └─ 水印/派生规则
发布中心
  ├─ 新建发布计划
  ├─ 发布计划
  ├─ 任务队列
  └─ 运行详情 / 证据
自动化
  ├─ 自动化包
  ├─ 调试 Studio
  └─ 兼容性测试
APK
  ├─ APK 仓库
  └─ 灰度部署
系统
  ├─ 用户/角色
  ├─ 安全/证书
  ├─ 审计
  └─ 告警/设置
```

## 19.2 通用组件

| 组件 | 规范 |
| --- | --- |
| DataTable | 服务端 cursor 分页、列配置、批量选择、空/加载/错误状态、导出审计。 |
| FilterBar | URL 可分享筛选、保存视图、时间范围、标签、状态。 |
| DevicePicker | 能力、版本、在线、维护、账号绑定过滤；显示为何不兼容。 |
| TaskStatus | 统一状态色/图标、可取消性、是否可重试、当前步骤。 |
| RiskConfirm | 显示目标范围、不可逆影响、审批人、确认短语。 |
| AuditTimeline | 按 request/workflow/device 聚合，不展示敏感明文。 |
| EvidenceViewer | 截图、UI XML、日志、哈希、时间和下载授权。 |
| VersionBadge | LAMDA/App/自动化包/APK 通道与是否受支持。 |

## 19.3 任务队列页面

- 列：状态、计划、平台适配器、目标数、成功/失败/未知、计划时间、开始/耗时、发起人、版本、操作。
- 过滤：状态、设备、账号、内容、时间、自动化包、错误类别、是否需人工。
- 操作：查看、协作取消、导出证据、对可重试失败创建新运行；运行中不提供“删除”。
- 未知提交结果必须用高优先级醒目标识，不能混入普通失败。

## 19.4 设备详情页面

- 顶部：在线/维护/租约、Android/LAMDA/目标 App、Edge、网络、电量、温度、存储。
- Tabs：概览、当前任务、远控、App、APK、日志、证书状态、历史。
- 操作：进入维护、创建调试会话、刷新能力、重启官方服务/设备（高风险确认）、隔离。
- 不显示设备 PEM 或 Edge 私钥；证书只显示指纹、有效期和轮换状态。

# 20. 安全、权限与合规

![安全边界](assets/security.png){ width=70% }

## 20.1 威胁模型

| 威胁 | 主要控制 |
| --- | --- |
| 公网发现设备端口 | 设备 VLAN ACL；65000 仅 Edge；云端无设备路由；服务证书。 |
| 浏览器窃取设备证书 | Remote Proxy；PEM 不离开 Edge；短期 debug token。 |
| 旧 Worker/网络分区重复控制 | fencing token + Edge 最大 token + LAMDA 60 秒锁。 |
| 恶意/误签自动化包 | Ed25519 签名、能力白名单、SBOM、审核、隔离 Runner。 |
| 重复发布 | API 幂等、snapshot、commit intent、单次提交、对账。 |
| 越权批量操作 | OIDC MFA、RBAC、目标范围、审批、速率、审计。 |
| APK 换签名/降级/恶意权限 | 签名校验、权限 diff、SBOM/扫描、灰度和停止阈值。 |
| 证据泄露 | 对象存储加密、短预签名 URL、租户隔离、保留期、敏感打码。 |
| 高风险研究功能误入生产 | prod/lab 构建和网络隔离；feature policy 默认 deny。 |

## 20.2 RBAC 角色

| 角色 | 权限摘要 |
| --- | --- |
| Viewer | 查看设备、计划和非敏感证据。 |
| ContentEditor | 编辑作品/媒体，不可调度或控制设备。 |
| Publisher | 创建计划；是否可批准由策略决定。 |
| Approver | 审批发布、APK 灰度和高风险设备动作；不能审批自己创建的高风险变更。 |
| AutomationDeveloper | 开发/测试自动化包；不能直接提升到生产。 |
| DeviceOperator | 维护设备、调试、查看日志；不能编辑内容。 |
| SecurityAdmin | 用户、角色、证书、密钥引用、审计和 lab 权限。 |
| SystemService | 机器身份，权限最小化到特定 API/队列。 |

## 20.3 Secret 与证书

- 云端密钥放 KMS/Vault/Secret Manager，数据库只存 `secret_ref`。
- Edge 身份证书 90 天或更短自动轮换；吊销后流立即断开。
- LAMDA 服务证书每设备独立或按小范围站点分组；禁止整个设备群共用长期同一 PEM。
- Edge 上私钥权限 0600，使用 OS keyring/TPM 时优先；备份不包含可直接使用的明文私钥。
- 审计中只保存证书指纹与 key_id。

## 20.4 生产与实验室能力表

| 能力 | 生产 | 实验室 |
| --- | --- | --- |
| UI 自动化/截图/UI 树 | 允许，按包能力 | 允许。 |
| App 生命周期/文件推送/APK 安装 | 允许，按审批 | 允许。 |
| 远控输入 | 短期授权 | 允许，仍审计。 |
| 任意 shell/ADB/SSH | 默认禁止 | 单独授权和隔离网络。 |
| Frida/Hook | 禁止 | 仅书面授权研究。 |
| MITM/流量篡改/代理 | 禁止 | 仅书面授权、隔离数据。 |
| 反检测/隐藏/验证码绕过 | 禁止 | 禁止。 |

## 20.5 合规与透明

- 记录设备和账号授权依据，允许随时解除绑定。
- 用户可见自动化状态和停止入口；公司专用设备需有明确管理告知。
- 数据最小化、用途限定、保留期和删除流程写入产品设置。
- 平台适配器在上线前由业务/法务确认平台条款和发布权限；不以技术能力替代授权。

# 21. 部署拓扑与容量规划

## 21.1 MVP 拓扑

- 1 个控制平面环境：Caddy、Web、Control API、Temporal Worker、Edge Hub、PostgreSQL、对象存储、OTel Collector。
- PostgreSQL 和对象存储优先使用托管服务；Temporal 可使用 Cloud 或自托管。
- 每个设备站点 1–2 台 Edge 节点；每台 Edge 根据 CPU/内存/网络承载 20–100 台设备，需用 soak 测定。
- 设备与 Edge 位于同 VLAN 或有明确 ACL；Edge 到云端仅需 443/tcp 出站。

## 21.2 生产拓扑演进

| 阶段 | 控制平面 | 边缘 |
| --- | --- | --- |
| 开发 | Docker Compose；单 PostgreSQL/MinIO/Temporal dev | 本机 MockEdge + 1 台真机。 |
| 试点 | 2 个 API/Worker 实例；托管数据库；对象存储 | 每站点 1 Edge；10–30 台设备。 |
| 生产 | 多可用区 API/Worker/Hub；数据库 HA；对象存储跨区策略 | 每站点主备 Edge 或快速重装；分批设备。 |
| 大规模 | 按租户/区域拆 Edge Hub 与 Worker Task Queue | 站点容量模型和自动扩容；独立网络。 |

## 21.3 Compose 骨架

```yaml
services:
  caddy:
    image: caddy@sha256:<pinned>
    ports: ["443:443"]
    depends_on: [web, control-api]

  web:
    image: registry.example/cloudctl-web@sha256:<pinned>

  control-api:
    image: registry.example/cloudctl-api@sha256:<pinned>
    environment:
      DATABASE_URL: postgresql+psycopg://...
      TEMPORAL_ADDRESS: temporal:7233
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4317

  temporal-worker:
    image: registry.example/cloudctl-worker@sha256:<pinned>

  edge-hub:
    image: registry.example/cloudctl-edge-hub@sha256:<pinned>

  otel-collector:
    image: otel/opentelemetry-collector-contrib@sha256:<pinned>
```

数据库、对象存储、OIDC 和密钥不应以示例中的明文方式进入仓库；Compose 仅作为开发/小规模试点模板。

## 21.4 容量估算维度

- 心跳：设备数 × 15–30 秒；上报内容为增量，避免每次大 JSON。
- 任务事件：每步骤而非每帧上报；远控视频走单独临时通道。
- 证据：按任务风险决定截图频度；视频录屏不默认开启。
- 媒体/APK：Edge 缓存命中率和站点带宽是关键，按 SHA256 去重。
- 并发：真实并发受设备/App 限制，不应简单追求云端高 QPS。

# 22. 服务器与边缘脚本

## 22.1 必须交付的脚本

| 脚本 | 职责 |
| --- | --- |
| scripts/bootstrap-control.sh | 安装/检查 Docker、创建目录、验证内核与时钟、生成非密钥配置。 |
| scripts/deploy.sh | 拉取固定 digest、数据库迁移预检、滚动更新、健康检查。 |
| scripts/rollback.sh | 回到上一个 release manifest；数据库只执行已设计的向后兼容路径。 |
| scripts/backup.sh | PostgreSQL 备份、对象清单、配置/版本清单；不导出明文密钥。 |
| scripts/restore.sh | 在隔离环境恢复并执行校验，再按审批切换。 |
| scripts/edge-install.sh | 创建系统用户、目录、证书入网、systemd 服务、ACL 检查。 |
| scripts/edge-upgrade.sh | 预拉镜像/包、停止接受新任务、排空、升级、回归、恢复。 |
| scripts/rotate-lamda-cert.sh | 生成/导入新服务证书、双证书窗口、探测、撤销旧证书。 |
| scripts/smoke-test.sh | API、Temporal、DB、S3、Edge 流、Mock/真机只读探针。 |
| scripts/dr-test.sh | 定期验证备份可恢复、RPO/RTO 与证据完整性。 |

## 22.2 脚本规范

- `set -euo pipefail`，所有参数显式，支持 `--dry-run`。
- 输出结构化日志和最终摘要；错误码稳定并记录 run_id。
- 不在命令行参数中传 Secret，使用文件描述符、secret store 或临时 0600 文件。
- 重复执行安全；每一步有前置检查和后置验证。
- 部署脚本不自动执行破坏性数据库回滚。
- Edge 升级先排空设备任务，不能直接 kill 正在提交的 Runner。

## 22.3 部署门禁顺序

1. 校验 release manifest、镜像签名、SBOM、数据库迁移和 LAMDA 兼容。
2. 在 staging 执行完整 smoke。
3. 部署控制平面 canary，确认 API/Workflow replay。
4. 升级 candidate Edge 和设备，观察。
5. 分批扩大；超过阈值自动暂停。
6. 发布完成后生成部署审计与可恢复点。

# 23. 可观测性与 SLO

## 23.1 统一上下文

每个日志、trace 和指标至少关联可用的：`tenant_id`（必要时哈希/低基数）、`request_id`、`workflow_id`、`run_id`、`task_run_id`、`target_id`、`edge_id`、`device_id`、`automation_version`、`lamda_version`、`target_app_version`。不要把账号名、手机号等 PII 放入高基数指标 label。

## 23.2 指标

| 类别 | 示例指标 |
| --- | --- |
| 控制平面 | http_request_duration_seconds, workflow_start_total, outbox_lag_seconds, db_pool_wait_seconds |
| 边缘 | edge_stream_connected, command_ack_latency_seconds, spool_bytes, runner_restarts_total, artifact_cache_hit_ratio |
| 设备 | device_heartbeat_age_seconds, lamda_rpc_duration_seconds, lamda_lock_refresh_failures_total, device_temperature_celsius |
| 自动化 | automation_step_duration_seconds, locator_fallback_total, watcher_trigger_total, ui_state_unknown_total |
| 发布 | publish_target_total{result}, publish_commit_unknown_total, reconciliation_duration_seconds, evidence_completeness_ratio |
| APK | apk_install_total{result}, rollout_failure_ratio, app_start_probe_duration_seconds |

## 23.3 建议 SLO

| SLO | 目标 | 说明 |
| --- | --- | --- |
| Control API 可用性 | 月度 99.9% | 不含计划维护。 |
| 已在线 Edge 的命令 ACK | p95 < 2 秒 | 不含设备执行。 |
| 计划调度偏差 | p95 < 30 秒 | 在资源和审批就绪时。 |
| 设备心跳新鲜度 | 99% < 60 秒 | 在线设备。 |
| 证据完整率 | 高风险任务 100% | before/after/failure/commit。 |
| 未知提交结果 | < 0.1%，且全部人工闭环 | 不能用重试掩盖。 |
| 备份 RPO/RTO | RPO ≤ 15 分钟；RTO ≤ 4 小时 | 以演练结果为准。 |

## 23.4 告警

- LAMDA 锁续租失败、同设备多 Runner、fencing token 被拒绝：P1。
- commit intent 已写但 5 分钟无结果/证据：P1。
- 未知提交结果、连续授权异常、验证码/异常核验：立即熔断目标账号并通知。
- Edge spool 持续增长、磁盘将满、证书将过期、时间偏移：P1/P2。
- candidate 版本失败率超过 stable 2 倍：自动暂停推广。

# 24. 测试、兼容性与验收

## 24.1 测试金字塔

| 层级 | 内容 | 是否需真机 |
| --- | --- | --- |
| Unit | 领域规则、状态机、幂等、Locator 选择、manifest/schema | 否。 |
| Contract | OpenAPI、gRPC、事件、自动化 SDK、错误目录 | 否。 |
| Integration | PostgreSQL、Temporal、S3、outbox、Edge spool、Mock LAMDA | 否。 |
| Replay | Temporal 历史重放和 Worker 版本兼容 | 否。 |
| Web E2E | 18 页面主流程、审批、取消、证据、APK 灰度 | Mock 可先验收。 |
| Device Integration | LAMDA 连接/证书/锁、选择器、Watcher、文件、APK、远控 | 是。 |
| Publish Sandbox | 授权测试账号的草稿/沙箱发布、单次提交和对账 | 是。 |
| Soak/Chaos | 断网、Edge 重启、Worker 重启、锁超时、磁盘压力 | 是，至少部分。 |
| Security | RBAC、租户隔离、证书吊销、恶意包、路径/对象授权 | 混合。 |

## 24.2 支持矩阵

首个目标矩阵建议：Android 10–17；arm64 为主；LAMDA 10.6 stable 和 10.8 candidate；目标 App 当前受支持版本 N 与 N-1；Root 与非 Root 各至少一套 profile。具体机型从实际设备池中选择，不用“一个模拟器通过”代表全部。

| 维度 | 最小覆盖 |
| --- | --- |
| Android | 10/12/14/16/17（有真实需求的中间版本补齐）。 |
| LAMDA | 10.6、10.8；升级/降级路径。 |
| 权限 | Root、Shizuku/shell、普通非 Root 能力画像。 |
| 屏幕 | 至少 1080×1920、不同 DPI、横竖屏。 |
| 目标 App | N、N-1；冷启动、已登录、弹窗、异常登录。 |
| 网络 | 稳定 Wi-Fi、弱网、断网重连、Edge 重启。 |
| APK | 单 APK、split APK、升级、失败、签名不匹配。 |

## 24.3 真机证据清单

- 测试用例 ID、设备/Android/LAMDA/目标 App/自动化包版本。
- 开始/结束时间、Edge/Workflow/Task Run ID。
- Preflight、before commit、after commit 或 failure 截图。
- UI XML/Locator 诊断、Watcher 触发、结构化日志。
- commit intent ID 和结果对账依据。
- APK 安装前后版本/签名、会话状态和启动探针。
- 人工验收人和结论。

## 24.4 发布门禁

G0 静态检查 → G1 单元/合同 → G2 集成/Temporal Replay → G3 Mock E2E → G4 candidate 真机矩阵 → G5 72 小时 soak → 生产 5% 灰度 → 逐批扩展。任何阶段出现未知提交、同设备双写、证书暴露或审计缺失，直接阻断。

# 25. AutoJS 迁移方案

## 25.1 迁移不是语法翻译

AutoJS 通常把 UI 操作、业务流程、调度、配置和日志混在设备脚本中。迁移到 LAMDA 时应拆成：业务快照在控制平面；持久流程在 Temporal；设备动作在自动化包；底层 API 在 `lamda-driver`；证据和审计独立。不要把旧脚本逐行改写后继续在手机端运行。

| 旧 AutoJS 概念 | 新架构对应 |
| --- | --- |
| 设备内定时器/线程 | Temporal Timer + Workflow/Activity。 |
| accessibility selector | LAMDA Selector + Locator Registry。 |
| 悬浮窗调试 | Web/Studio + Companion 状态/停止。 |
| 脚本下载执行 | 签名 Automation Package + Edge 隔离 Runner。 |
| 全局变量/本地存储 | PublishSnapshot + Task Context + Edge 短期 spool。 |
| 截图日志 | 结构化 Evidence Artifact。 |
| 多脚本抢设备 | device lease + fencing + LAMDA Lock。 |
| 失败后 while 重试 | Activity 重试矩阵 + UI 状态判断 + 熔断。 |
| 点击发布后重跑 | commit intent + 单次提交 + reconcile。 |

## 25.2 迁移步骤

1. 盘点旧脚本：输入、目标 App、权限、选择器、不可逆点、依赖文件、定时和错误。
2. 删除与业务目标无关或高风险的反检测、抓包、代理、群发逻辑。
3. 把配置抽成 JSON Schema，把页面对象抽成 Locator/Page Object。
4. 把流程拆成 validate/preflight/prepare/before_commit/commit/reconcile/cleanup。
5. 为每个外部动作定义幂等与重试策略。
6. 先用 Mock Driver 和录制 fixture 测试，再进入只读真机测试。
7. 在授权测试账号做沙箱发布，对比旧系统结果。
8. 以小批设备双轨运行；新系统稳定后关闭旧 AutoJS 调度。

## 25.3 迁移完成标准

- 旧脚本不再持有生产调度或账号/设备密钥。
- 每个流程都有 Automation Manifest、测试、兼容矩阵、签名和回滚版本。
- 所有发布可关联 snapshot、commit intent、对账和证据。
- 设备不再依赖 AutoJS 常驻/悬浮窗/动态脚本更新。

# 26. 代码仓库结构

```text
cloudctl/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── pnpm-workspace.yaml
├── apps/
│   ├── web/                       # Vue 管理台
│   └── studio/                    # 可与 web 合并部署
├── services/
│   ├── control-api/               # FastAPI 模块化单体
│   ├── temporal-worker/           # Workflows/Activities
│   ├── edge-hub/                  # 云端 gRPC 双向流
│   └── outbox-dispatcher/
├── edge/
│   └── gateway/                   # Edge 主进程/Runner/缓存/spool/remote proxy
├── packages/
│   ├── domain/                    # 共享领域类型
│   ├── api-contracts/             # OpenAPI 生成物/JSON Schema
│   ├── edge-protocol/             # protobuf
│   ├── lamda-driver/              # 唯一可 import lamda 的包
│   ├── automation-sdk/
│   └── observability/
├── mobile/
│   ├── companion/
│   └── dpc/                       # 可选，独立应用
├── automation/
│   ├── packages/
│   └── fixtures/
├── infra/
│   ├── compose/
│   ├── terraform/
│   ├── caddy/
│   └── otel/
├── scripts/
├── tests/
│   ├── contract/
│   ├── integration/
│   ├── replay/
│   ├── e2e/
│   └── device/
└── docs/
    ├── adr/
    ├── runbooks/
    └── compatibility/
```

## 26.1 Python package 规则

- 每个服务使用清晰入口和依赖注入；领域层不得 import FastAPI、SQLAlchemy 模型或 LAMDA。
- 数据库事务在 application service 管理；Repository 不隐式 commit。
- Temporal Workflow 代码与 Activity 实现分开，Workflow 禁止系统时间、随机、网络和数据库。
- `lamda-driver` 对所有 LAMDA 异常映射到稳定错误目录。
- 类型检查使用 mypy/pyright，lint/format 使用 ruff。

## 26.2 前端规则

- 页面不直接拼 URL；只使用生成 API client。
- Server State 由 TanStack Query 管，Pinia 只管 UI/会话状态。
- 权限不仅隐藏按钮，后端必须再次校验。
- 发布/安装表单以 schema 驱动，提交前展示归一化预览。
- 所有异步状态有 loading/empty/error/stale/offline。

# 27. 分阶段开发路线

## 27.1 阶段总览

| 阶段 | 主要交付 | 退出条件 |
| --- | --- | --- |
| Phase 0：基础骨架 | 仓库、环境、数据库、OIDC/RBAC、Web 壳、OpenAPI、CI、Mock Device | 可登录并看到 18 个路由骨架；所有检查通过。 |
| Phase 1：控制平面闭环 | 设备/账号、内容/媒体、发布计划、任务 UI、审批、outbox | 无手机也可走完整 Mock 发布流程。 |
| Phase 2：Edge + LAMDA | 入网、gRPC、spool/cache、driver、锁、Runner、远控代理 | 一台真机安全纳管，设备 65000 不公网暴露。 |
| Phase 3：发布/Studio/APK | 自动化包、Studio、Temporal 发布、单次提交、APK 灰度 | 授权测试账号完成真机发布；APK 可灰度和回滚。 |
| Phase 4：伴生/安全/运维 | Kotlin App、可选 DPC、prod/lab 隔离、备份/证书轮换 | 操作透明、可停止、可恢复，安全评审通过。 |
| Phase 5：加固上线 | 负载/soak/chaos、兼容矩阵、SLO、runbook、AutoJS 试点迁移 | 5% 灰度稳定后逐批上线。 |

配套 JSON 已拆为 59 个有依赖关系的任务。桌面智能体应先读取 `AGENTS.md` 和任务清单，按 `dependencies` 拓扑顺序执行，而不是按文件顺序盲目生成代码。

## 27.2 时间与团队参考

若由 4–6 人（后端/工作流、Edge/LAMDA、Web/Studio、Android/DevOps）并行，核心试点通常需要约 12–16 周；桌面智能体可以提高代码产出速度，但真机调试、目标 App 兼容、安全评审和授权流程仍是关键路径。估算应以任务清单的点数、真实设备数量和目标平台数量重新校准。

# 28. 桌面智能体执行规则

## 28.1 每项任务的固定循环

1. 读取任务、依赖、相关 ADR/规范和现有代码。
2. 写短实施计划，列出会修改的包、迁移、API、测试和风险。
3. 先补失败测试/合同，再实现最小闭环。
4. 执行格式、lint、类型、单元、合同、集成和必要 E2E。
5. 若任务标记 `hardware_required=true`，必须在真机执行验收；无法执行时状态只能是 `blocked_hardware`，不能标 done。
6. 保存命令输出、截图、日志和变更摘要到任务证据目录。
7. 更新任务 JSON 状态和 `evidence`，再提交。

## 28.2 禁止智能体自行作出的决定

- 不得把 65000 暴露公网或把 PEM 写入前端/日志。
- 不得为解决测试失败而关闭证书、RBAC、租户隔离、签名或审计。
- 不得把不可逆提交 Activity 改为自动重试。
- 不得在生产能力列表加入 shell/Frida/MITM/代理篡改/验证码处理。
- 不得静默改变目标 App、LAMDA、APK 或自动化包支持范围。
- 不得把 Mock 测试结果描述为真机通过。

## 28.3 Definition of Done

- 代码、迁移、合同和文档齐全；无 TODO 伪实现。
- 单元、类型、lint、合同、集成通过；相关 Temporal 历史可 replay。
- 失败路径、取消、超时、重试和审计已覆盖。
- 安全边界无回退，Secrets 未进入仓库/日志。
- 真机任务附设备矩阵与证据；Web 任务附 Playwright 截图/视频。
- 对用户可见的状态、错误和恢复动作完整。

## 28.4 证据目录约定

```text
artifacts/tasks/<task-id>/
├── summary.md
├── commands.log
├── test-results/
├── screenshots/
├── device-evidence/
├── openapi-diff.txt
├── migration-plan.md
└── checksums.sha256
```

# 29. 主要风险与缓解

| 风险 | 级别 | 缓解 |
| --- | --- | --- |
| 目标 App UI 频繁变化 | 高 | Locator Registry、版本探测、N/N-1、视觉证据、candidate 包和快速回滚。 |
| LAMDA 新版本回归 | 高 | 10.8 candidate；10.6 stable/rollback；固定 hash；真机 soak。 |
| 提交结果未知导致重复发布 | 极高 | commit intent、单次提交、对账、UNKNOWN 人工闭环。 |
| 设备双写/旧 Worker 复活 | 极高 | fencing lease + Edge token + LAMDA lock + 单 Runner。 |
| 默认无认证导致设备暴露 | 极高 | 服务证书、VLAN ACL、Edge-only 65000、扫描告警。 |
| 官方服务端商业分发边界不清 | 高 | 客户端与服务端/伴生 App 分包；规模部署前取得书面条款。 |
| Root/机型差异 | 中高 | 能力画像与调度；不承诺统一能力；分 profile。 |
| 远控带宽和兼容 | 中 | MVP 官方 WebUI 代理；MJPEG fallback；H.264 按机型探测。 |
| 边缘断网/磁盘满 | 高 | spool 上限、优先级上传、磁盘告警、离线提交默认禁止。 |
| 自动化包供应链 | 高 | 签名、SBOM、能力白名单、隔离 Runner、审计和撤销。 |
| 平台条款或账号授权变化 | 高 | 平台适配器开关、法务/业务复核、熔断、人工确认。 |
| 智能体过度声称完成 | 中高 | 任务证据、hardware_required、真实命令和 DoD 门禁。 |

# 30. 架构决策记录、资料与结论

## 30.1 关键 ADR

| ADR | 决策 | 结果 |
| --- | --- | --- |
| ADR-001 | 用 LAMDA/FIRERPA 替代 AutoJS | 设备采用客户端-服务端统一 API；不再运行设备内业务脚本。 |
| ADR-002 | 三平面架构 | 云端控制、边缘执行、Android 设备分离。 |
| ADR-003 | 控制 API 先做模块化单体 | 降低分布式复杂度，边界可拆。 |
| ADR-004 | Temporal 负责持久工作流 | 定时/恢复/审批/取消/补偿有事件历史。 |
| ADR-005 | 数据库 fencing + LAMDA Lock | 解决跨进程和设备端双写。 |
| ADR-006 | commit intent + 单次提交 + 对账 | 避免不可逆动作因重试重复。 |
| ADR-007 | 官方 Server 与自研 Companion 分包 | 许可、升级、安全边界清晰。 |
| ADR-008 | 生产/实验室能力隔离 | 高风险研究能力不进入生产。 |
| ADR-009 | 远控经 Edge Proxy | 浏览器和云端不持有设备 PEM。 |
| ADR-010 | 脚本/APK/镜像均签名和可追溯 | 建立供应链和回滚。 |

## 30.2 官方资料（访问基线 2026-08-30）

| 编号 | 资料 | 地址 |
| --- | --- | --- |
| R1 | FIRERPA/LAMDA GitHub README | https://github.com/firerpa/lamda |
| R2 | LAMDA PyPI | https://pypi.org/project/lamda/ |
| R3 | FIRERPA Quick Start | https://device-farm.com/docs/en/quick-start |
| R4 | FIRERPA Service Certificate | https://device-farm.com/docs/en/server-certificate |
| R5 | FIRERPA API Lock | https://device-farm.com/docs/en/api-lock |
| R6 | FIRERPA App Operations | https://device-farm.com/docs/en/app-ops |
| R7 | FIRERPA Virtual Display | https://device-farm.com/docs/en/virtual-display |
| R8 | FIRERPA Capability Integration | https://device-farm.com/docs/en/capability-integration |
| R9 | Temporal Workflow Execution | https://docs.temporal.io/workflow-execution |
| R10 | Temporal Retry Policies | https://docs.temporal.io/encyclopedia/retry-policies |
| R11 | Temporal Workflow Definition | https://docs.temporal.io/workflow-definition |
| R12 | PostgreSQL 18 Documentation | https://www.postgresql.org/docs/current/ |
| R13 | OpenTelemetry Collector | https://opentelemetry.io/docs/collector/ |
| R14 | Android Enterprise Dedicated Devices | https://developer.android.com/work/dpc/dedicated-devices |

## 30.3 交付物使用顺序

1. 桌面智能体读取 `AGENTS.md`。
2. 读取本报告的第 1、6、9、10、15、16、20、24、28 节。
3. 加载 `LAMDA云控系统_桌面智能体开发任务清单_20260830.json`，按依赖拓扑执行。
4. 用 `specs/` 中的 manifest、发布计划、gRPC 和错误目录作为初始合同。
5. 每完成一阶段，依据本报告退出条件和真机证据做人工门禁。

## 30.4 结论

最可靠的实现路径不是把原网页的所有运营功能复刻出来，也不是把 AutoJS 脚本换一个运行器继续堆叠，而是建立一个把“业务意图、持久编排、安全边缘执行、设备单写、不可逆提交、结果对账和证据”全部纳入模型的系统。LAMDA 适合作为新的设备控制底座，但必须放在受证书、租约、能力和审计约束的 Edge Driver 后面。第一版围绕 18 个页面和发布/APK/Studio 三条主链交付，随后再根据合法业务价值逐项扩展。

---

文档生成基线：2026-08-30。LAMDA、目标 App、Android、依赖库和平台规则均可能变化；实施时必须重新锁定版本并执行兼容测试。
