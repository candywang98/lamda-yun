# 当前交接：正文读取网页与 API 已上线，手机尚未升级

更新日期：2026-10-11。用户已明确授权并完成本次 API 变更窗口（09:38:49Z–09:48:49Z）；该窗口不是后续重启或业务操作的常设授权。本文件不授予自动续跑、手机安装或真实发送权限。

## 恢复与授权边界

权威仓库：/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source。
明确恢复时先读 AGENTS.md 和本文件，核对分支、HEAD、暂存区及相对下列基线的新差异；不扫描兄弟仓库或历史聊天。父智能体规划、委派、评审；指定 GPT-6 Astra / Low 执行批准的代码、构建与测试，文档不选择模型。
原 51 个文件、原暂存区、原差异和任务台账保持；禁止 git add -A、清理未跟踪文件或覆盖用户修改。[tasks.json](tasks.json)仍是唯一状态权威，本轮未改、未升级设备验收；涉及计划语义先读 [README](README.md)。

## 当前结果与未完成边界

详见 [正文读取交付记录](im-body-collection-20261011.md)。独立 im-chat-collection/1 实现网页手动确认设备/联系人后读取一屏无障碍可见正文，单独展示快照，保留原始通知；不输入、不发送、不启用 duty、不滚动历史。
用户已说明手机基本固定闲鱼账号使用；这只是使用习惯，运行时账号仍为 UNVERIFIED，聊天标题仅是显示名称匹配，方向为几何启发式，不承诺完整历史或平台账号已核验。旧补正文及 duty 采集增加身份漂移防护；原回复流程和 receiveOnly 限制保留，真实回复未验收。
新版网页与 API 已上线，正文查询接口已返回 200；因手机仍是旧 APK，capability 为 supported=false、available=false、reason=IM_COLLECTION_UNSUPPORTED，v10 未安装，正文采集仍不可用。云端发布不等于端到端或真机验收通过。
“产品介绍/更新日志”移除继续保留；其他模块精简、AutoJS/APK 架构和 Recipe 改名/移动/隐藏仍为讨论，不自动实施。

## 版本与部署

- main 集成代码基线：66e1ab475d4fd65b8afee78853ea65509aee5073，其后可叠加文档提交；main 未推送。
- 网页发布源码：01877be2fb677196279ab2d21ffdcda34e8ddaef。2026-10-11 北京时间 17:09:48 激活，17:16:03 提交确认。
- 线上入口：https://43.133.243.154.sslip.io/cloudctl-mobile/im，需要认证。当前静态目标：/var/www/cloudctl-mobile-web-im-01877be2fb67。
- 上一目标：/var/www/cloudctl-mobile-web-im-de8629edb5c4；备份：/home/ubuntu/cloudctl-mobile/backups/web-im-01877be2fb67，SHA256 dbbb194d4fb244d10c733449c29f6174caf05ab76c7cb605c0cf1aecce3fd746；保留 19 个旧哈希资源。回滚须核对指针、锁与后续发布，不自动执行。
- API 已发布：82abeeee78bc746f8d41e05c3b47aded645740a1；运行目录 /home/ubuntu/cloudctl-mobile/releases/im-chat-82abeeee，MainPID 935215、active，2026-10-11 北京时间 17:44:39 重启。17:45:42 回验 PASS，未迁移数据库、未改前端；这是当时观测，不证明恢复时状态。
- v10 源码：f3200593f6b9a1b2e217f4067b04a33639a39971，SOURCE_REVISION=f320059；包名 com.company.cloudctl.companion，版本 10 / 0.1.0-business-acceptance.10。
- 稳定本地产物：/Users/wangziheng/CloudCtlExternal/apk-delivery/cloudctl-companion-v10.apk；SHA256 c6ad2ec6f0adde0a971528a58682e9ba27f1337c686d37da7f987f0b2cef0dfb。原 A→B 签名链通过；未安装、未复制到手机，属于受控验收候选。
- 四个隔离交付分支已推送并读回一致；具体 SHA 见交付记录与 github-sync.json。不得直接构建 main 全量上线、以 main HEAD 冒充发布源码，或顺带推送 main 既有提交。

## 验证与下一步

API 候选 161 passed、2 skipped；4 mypy/4 ruff 为既有问题、0 新增。共享 OpenAPI 455 行增量，兼容性检查 1 passed、手写 TS typecheck 通过。
Android Debug 121 项通过；businessAcceptance 79 项通过，lint 0 错误/19 警告，构建及签名验证通过。网页前轮 140 项与变更组件最终 32 项（4 新增）通过，typecheck/lint/build 通过。
前端阶段公开 28 次 HTTPS 检查全部成功、14 文件哈希匹配；当时线上浏览器桌面 1280/手机 390 无横向溢出，旧 API 的 404 降级、账号未核验及 receiveOnly 提示正确。模拟响应另覆盖成功/协议不支持/离线/不可执行。真实采集 POST、写操作、发送均为 0；线上被拦写入尝试为 0。
截图 wrapper/CDP 均失败，没有像素级验收。浏览器任务 38 已恰好结束一次、keep=[]，不得复用。API 发布后公网 live/ready 200、匿名及无效 Bearer 401、认证 threads/bodyCollections 200，OpenAPI 规范化哈希与候选一致、246 个运行文件哈希通过，通知配置及 receiveOnly 保留；realTaskPost=0、realSend=0。发布后浏览器桌面 1280/手机 390 的列明 DOM 检查通过：正文面板可见、旧“云端不支持”提示消失、设备升级提示可见、读取按钮禁用、账号未核验提示可见、无横向溢出。任务 39 已恰好结束一次、keep=[]，临时凭据已移除，不复用会话。最终会话未持续注入 GET-only fetch guard，不能声称存在受监控的拦写计数；所选会话无未读徽标，unreadCount=0 的源码路径跳过 markRead POST，未触发回复/采集/配置动作。receiveOnly 由控制器 API 配置检查另行验证，未列入本次最终浏览器文字断言。软件证据不替代真机验收。

恢复后先核对部署、HEAD 与保护差异，复用未变证据，不自动重跑全套。本次获准 API 窗口已经执行完成，不再列为待申请事项；未来生产变更仍按 [fleet-deploy §7](../runbooks/fleet-deploy.md)另行明确授权。
本次首次切换前 smoke 因缺少 fleet_live_transport 失败，备份恢复验证 PASS、旧服务未改变。候选补齐 4 个文件（与 82abeeee/557f547 来源一致）后严格隔离 smoke PASS，经 prepared-api-resume.py 在原窗口内续跑成功，无切换后回滚。
当前只待另行授权的 v10 安装与真实屏幕正文采集验收；安装须核对包哈希/签名/当前手机版本并持设备锁。真实回复、发送或 duty 仍需各自授权，不能借安装/采集验收扩大业务权限。

## 证据与归档

外部根：/Users/wangziheng/CloudCtlExternal/acceptance/20261011-im-body-collection/。重点为 FROZEN-CONTRACT.md、api-executor/release/、mobile-executor/delivery.json、mobile-packaging/delivery.json、v10-delivery-manifest.json、web-executor/、github-sync.json、main-integration-check.json、public-verification.json、browser-online.json、screenshot-limitation.json、api-deployment-result.json、api-executor/release/supplement-smoke.json、api-executor/release/prepared-api-resume.py、api-window-resume-status.json、browser-api-online.json、browser-api-get.json、browser-api-task-finished.json。外部证据不在 fresh clone 中，缺失时说明限制，不扩大搜索或授权。
[上一版消息聚合交接](../archive/2026-10-11/HANDOFF-im-inbox-checkpoint-20261011.md)逐字节归档，SHA256 6e155bea0c1454d7697324fade16dd65907cc513e23eb99ea9ff213cf7cdb886。
tasks.json SHA256：3a1ae74049ba843bc66a77d4a0cb98be259130897ff324b17d106e5d6bb46fcb。

[API 发布前交接](../archive/2026-10-11/HANDOFF-im-body-pre-api-20261011.md)逐字节归档，SHA256 89eca0690923ee18ec967a5198220bec1b877f65262cb456b7e80143f1a110ad。
