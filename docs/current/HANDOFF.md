# 当前交接：菜单精简已上线，后续范围待用户选择

更新日期：2026-10-11。此次用户只要求整理交接给外部智能体继续；本文件不是自动续跑指令。

## 恢复入口与边界

权威仓库：/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source。
用户明确恢复时，先读根目录 AGENTS.md 和本文件，再核对实际分支、HEAD、暂存区和差异。
不要扫描兄弟工作树、历史目录或聊天寻找新任务；交接缺失时直接报告。
下一步先与用户对齐：继续模块精简、处理消息正文/设备区分，还是讨论 APK 架构。
其余菜单隐藏建议、9 月 30 日硬件事项均不能自动执行。

父智能体负责规划、委派、评审；仓库规定 GPT-6 Astra / Low 执行批准的代码、构建与测试。
文档不能设置或暗改运行模型；指定执行者不可用时需披露，不得静默替代。
用户既有前端交付要求包括本地预览、云端部署回验、GitHub 同步/读回，见 [README](README.md)。
这不授予手机安装、重绑、ADB、设备领取任务或发送/发布/删除等业务写操作权限。
设备、部署、发布、副作用锁仍按 AGENTS.md，没有新的设备验收授权。

## 本次已完成内容

用户要求暂时去掉“产品介绍”和“更新日志”，并梳理其余模块。
仅移除 system-home-01、system-home-06 的侧栏、目录、搜索、显示设置及残留页签。
两项旧 URL 重定向到 /operations；热更新保留的旧页签与当前旧页面也能清理/跳转。
目录在生成稳定编号和竞品来源映射后过滤，其他 ID、来源索引与元数据不变。
原四个 retired ID 语义保留：xy-tasks-02、xy-tasks-07、post-management-06、post-management-07。
没有删除其他模块、重设计导航、更新后端、数据库或手机。

完整盘点见 [当前模块梳理](module-review-20261011.md)。
仍有 15 个运营分组、132 项目录；原四项停用，默认显示 128 项。
静态分类为 53 项专用页面、41 项配置预览、12 项说明、26 项未接入；这不是业务完成率或真机验收。
设备工作台、消息聚合、Recipe、显示设置等独立入口不计入 132 项。
系统主页剩余：设备列表、系统授权、常见问题、常用工具、超级擦亮、建议反馈、公告通知、视频教程。

## Git 与已部署版本：两条版本线必须区分

| 对象 | 已核验值 | 限定 |
|---|---|---|
| 发布基线 | 48b787ea248031262ffaa050935808de8ef50933 | 上一次已部署前端 |
| 本次前端发布 | 87fade44bbc2ee03f945b3eab20db1a09ad123db | 独立发布工作树构建，已上线 |
| 发布分支 | release/web-module-pruning-20261011 | 已推送 GitHub，SHA 读回一致 |
| 权威 main 文档交接前 HEAD | 7a282a6aaf353b44c2ff3ce97d7600b683177c8e | cherry-pick 菜单修改；交接提交可在其后 |
| 本地 main 与缓存 origin/main | 当时 ahead 22 | 本轮父智能体未推送 main；不是新鲜远端查询结论 |

不能直接把 main 全量构建上线：main 的闲鱼队列前端还依赖后端原子派发/串行化配套更新。
已上线 release 基于此前实际部署版本，仅纳入获准前端差异；不要以 main HEAD 冒充线上源码版本。
文档提交不改变线上前端、APK 或后端版本；后续同步不能顺带推送 main 既有提交。

权威源目录原有脏文件必须保留：

- 已跟踪：apps/web/src/features/fleet/FleetDeviceCardView.vue、FleetWorkbenchView.vue、model.ts，以及 apps/web/tests/fleet.spec.ts。
- 新文件：apps/web/src/features/fleet/presentation.ts、apps/web/tests/fleet-presentation.spec.ts。
- 未跟踪预览文件：docs/runbooks/local-web-preview.md、scripts/start-web-preview.mjs、scripts/tests/start-web-preview.test.mjs。
- 多个历史 artifacts 仍未跟踪；不能混入本次提交。

外部 baseline.json 记录原 51 个文件哈希；本轮集成确认全部保留，原 tracked diff 和 index 未变。
禁止 git add -A、清理未跟踪文件或 reset 覆盖用户修改。独立干净工作树不代表权威 main 干净。

## 预览与云端现状

本地同一权威源预览：http://127.0.0.1:5173/operations 与 /fleet。
父智能体刚确认 readOnly=true；启动入口为 node scripts/start-web-preview.mjs，桌面有 CloudCtl实时预览.command。
预览通过服务端凭据读取云端真实数据，预览不允许写；不得在输出中泄露凭据。
本地后端代码修改不会自动影响这个云端后端。预览脚本尚未跟踪，fresh clone 不包含这些辅助文件。
恢复时先检查既有服务，不要盲目重复启动或关闭只读限制。
云端：https://43.133.243.154.sslip.io/cloudctl-mobile/operations，需要登录认证。
父智能体浏览器 Space 36 任务已完成，不复用已关闭任务；更早 Space 18 也不是现行会话或权限。

2026-10-11 15:31:46 北京时间切换上线，15:34:32 确认完成：

- 当前静态目标：/var/www/cloudctl-mobile-web-menu-87fade44bbc2。
- 上一目标：/var/www/cloudctl-mobile-web-fleet-48b787ea2480。
- 原站点备份：/home/ubuntu/cloudctl-mobile/backups/web-menu-87fade44bbc2/web.tar.gz，27 文件哈希核验。
- 备份包 SHA256：00496b5caf1c1c8e48eaec10b0b36861ba5a54dbc39f71e88cd0c3fc5d12e63e。
- 保留 15 个旧哈希资源以兼容已经打开的页面。
- 云端 API 部署前后均为 order-delivery-557f547，采样 PID 2790688，active；没有重启或迁移。

这些是发布时观测，不证明现在 PID、指针、手机或业务状态仍相同。
部署使用 /home/ubuntu/cloudctl-mobile/.deploy.lock 非阻塞排他锁。
核验原指针和版本后原子切换；确认期间持续持锁，失败自动回滚。
如以后获准回滚，必须持同一锁且确认当前指针仍是本次版本，才原子恢复上一目标并回验公开入口。
不能覆盖其他后续发布；此交接不要求现在执行回滚或部署。

## 已有验证证据与限制

发布执行者完成 9 个相关测试文件、53 项测试，全部通过；typecheck、lint、生产构建退出码均为 0。
Lint 为 0 errors / 218 warnings，构建保留包体积警告，不应描述为“零告警”。
父智能体核对 11 个变更文件、14 个生产文件哈希；外部 26 个 HTTPS GET 均为 200，14 文件线上哈希匹配。
本地浏览器 HMR 验证移除两旧页签、保留设备列表页签，菜单 8 项，旧链接/搜索/设置检查通过。
云端浏览器 9 项功能/DOM 检查成功，包含目录 128 项、搜索、旧链接、设置、设备列表及 390/1440 宽度。
截图工具两次 Page.captureScreenshot 超时，未获截图；不能声称像素级视觉验收。
5 条 modal 异常来自 chrome-extension 堆栈，已单独保留；该次没有观察到本站应用异常。
没有新增真机验收、设备状态认定或业务发送测试。

精确命令见外部 executor/commands.json，相关测试文件为：
operations-catalog.spec.ts、operations-shell.spec.ts、operations-catalog-navigation.spec.ts、router.spec.ts、
display-settings.spec.ts、operation-page-availability.spec.ts、operation-workbenches.spec.ts、generic-workbench.spec.ts、field-map.spec.ts。
发布工作树执行 pnpm --filter @cloudctl/web test 后接上述 tests/ 路径；另执行 typecheck、lint。
生产构建命令：

    VITE_BASE_PATH=/cloudctl-mobile/ VITE_CONTROL_API_URL=https://43.133.243.154.sslip.io VITE_OPERATIONS_MOCK_ENABLED=false VITE_CONTROL_API_DEV_AUTH=false pnpm --filter @cloudctl/web exec vite build --base=/cloudctl-mobile/

依赖按 pnpm install --offline --frozen-lockfile --ignore-scripts 安装，先构建 @cloudctl/api-contracts。
这些是已完成验证的记录，不是恢复时自动全量重跑的清单。本次交接仅文档，不重跑软件测试。

## 尚未实施的讨论

- 用户讨论“现有 APK + Auto.js 第二 APK”；没有架构定案或开发授权。共享控制平面仅为建议。
- Recipe 同时包含 APK 内置/native 与可下载流程，不是所有流程都能热更新；不能承诺零 APK 更新。
- 用户希望消息聚合显示真实正文、区分设备。已有设备标签/筛选，服务端按设备 + 平台 + 对端分组。
- 通知占位文字不等于完整聊天正文。DutyController 通过无障碍读取聊天，但实际可靠性尚未验收。
- 进入聊天读取会占用手机界面，可能改变已读标记；不能当作无副作用后台读取。
- 手动“读取正文”按钮、更清晰设备/账号标签只是建议，未实现。
- 仅 device + peerName 不能可靠隔离同一设备切换账号后的会话，账号隔离需要单独设计和验证。
- 建议六个主分组：设备、消息、商品、订单、任务、素材，另设设置/高级；尚未实施。
- 盘点中的隐藏/合并建议全部待用户选择；不得自动删除转转、聊天配置或其他推荐隐藏项。

## 快速恢复核对与任务台账

先运行只读本地检查，比较本次文档前代码基线和实际新增差异：

    git branch --show-current
    git rev-parse HEAD
    git status --short
    git diff --cached --stat
    git diff --stat 7a282a6aaf353b44c2ff3ce97d7600b683177c8e
    shasum -a 256 docs/current/tasks.json

[任务台账](tasks.json)仍是唯一任务状态权威；此次未更新其任何状态。
其 SHA256：3a1ae74049ba843bc66a77d4a0cb98be259130897ff324b17d106e5d6bb46fcb。
涉及计划语义或任务状态修改时再读 [README](README.md)；复用与当前版本一致的证据，针对新差异验证。
9 月 30 日 v9 键盘与双机真实入站待验收细节见 [原交接归档](../archive/2026-10-11/HANDOFF-v9-checkpoint-20260930.md)。
归档逐字节 SHA256：c6db3ebbac2fb4b994536571aed5662d6c21f5a3f8052b1bb2cf366d7c18f796。
旧观测、旧会话和待办不能解释成新的硬件操作许可。

## 证据位置

外部本机证据根：/Users/wangziheng/CloudCtlExternal/acceptance/20261011-module-pruning/。
DEPLOYMENT.md、integration-check.json、github-sync.json、deployment-result.json、browser-online.json、handoff-baseline.json 记录上述发布事实。
baseline.json 是原 51 文件哈希账本；MODULES.md 已复制为仓库内盘点，调整了源码路径前缀。
executor/commands.json 与各日志记录精确命令、退出码；executor/prod-dist/version.json 记录发布 SHA。
executor/payload.sha256 记录生产文件哈希；其自身 SHA256 为 2598592cad15059a4a825f029de173d928990978c81736ec3b3a49acd019487b。
外部证据不是 fresh clone 的一部分；找不到时应报告限制，不据此重新宣称验收或扫描其他仓库。
