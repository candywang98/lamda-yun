# 当前交接：正文读取网页已上线，后端与手机尚未启用

更新日期：2026-10-11。最近明确授权是继续消息聚合优化；本文件不授予自动续跑、生产后端重启、手机安装或真实发送权限。

## 恢复与授权边界

权威仓库：/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source。
明确恢复时先读 AGENTS.md 和本文件，核对分支、HEAD、暂存区及相对下列基线的新差异；不扫描兄弟仓库或历史聊天。父智能体规划、委派、评审；指定 GPT-6 Astra / Low 执行批准的代码、构建与测试，文档不选择模型。
原 51 个文件、原暂存区、原差异和任务台账保持；禁止 git add -A、清理未跟踪文件或覆盖用户修改。[tasks.json](tasks.json)仍是唯一状态权威，本轮未改、未升级设备验收；涉及计划语义先读 [README](README.md)。

## 当前结果与未完成边界

详见 [正文读取交付记录](im-body-collection-20261011.md)。独立 im-chat-collection/1 实现网页手动确认设备/联系人后读取一屏无障碍可见正文，单独展示快照，保留原始通知；不输入、不发送、不启用 duty、不滚动历史。
用户已说明手机基本固定闲鱼账号使用；这只是使用习惯，运行时账号仍为 UNVERIFIED，聊天标题仅是显示名称匹配，方向为几何启发式，不承诺完整历史或平台账号已核验。旧补正文及 duty 采集增加身份漂移防护；原回复流程和 receiveOnly 限制保留，真实回复未验收。
新版网页已上线，但现网 API 仍为旧版、v10 未安装，因此正文采集尚不可用。线上正确显示“云端尚不支持正文读取”，按钮禁用；前端上线不等于端到端启用。
“产品介绍/更新日志”移除继续保留；其他模块精简、AutoJS/APK 架构和 Recipe 改名/移动/隐藏仍为讨论，不自动实施。

## 版本与部署

- main 集成代码基线：66e1ab475d4fd65b8afee78853ea65509aee5073，其后可叠加文档提交；main 未推送。
- 网页发布源码：01877be2fb677196279ab2d21ffdcda34e8ddaef。2026-10-11 北京时间 17:09:48 激活，17:16:03 提交确认。
- 线上入口：https://43.133.243.154.sslip.io/cloudctl-mobile/im，需要认证。当前静态目标：/var/www/cloudctl-mobile-web-im-01877be2fb67。
- 上一目标：/var/www/cloudctl-mobile-web-im-de8629edb5c4；备份：/home/ubuntu/cloudctl-mobile/backups/web-im-01877be2fb67，SHA256 dbbb194d4fb244d10c733449c29f6174caf05ab76c7cb605c0cf1aecce3fd746；保留 19 个旧哈希资源。回滚须核对指针、锁与后续发布，不自动执行。
- API 候选：82abeeee78bc746f8d41e05c3b47aded645740a1，基于实际旧发布基线构建，未部署、重启或迁移。部署前后观测仍为 order-delivery-557f547、MainPID 2790688、active；不证明恢复时仍相同。
- v10 源码：f3200593f6b9a1b2e217f4067b04a33639a39971，SOURCE_REVISION=f320059；包名 com.company.cloudctl.companion，版本 10 / 0.1.0-business-acceptance.10。
- 稳定本地产物：/Users/wangziheng/CloudCtlExternal/apk-delivery/cloudctl-companion-v10.apk；SHA256 c6ad2ec6f0adde0a971528a58682e9ba27f1337c686d37da7f987f0b2cef0dfb。原 A→B 签名链通过；未安装、未复制到手机，属于受控验收候选。
- 四个隔离交付分支已推送并读回一致；具体 SHA 见交付记录与 github-sync.json。不得直接构建 main 全量上线、以 main HEAD 冒充发布源码，或顺带推送 main 既有提交。

## 验证与下一步

API 候选 161 passed、2 skipped；4 mypy/4 ruff 为既有问题、0 新增。共享 OpenAPI 455 行增量，兼容性检查 1 passed、手写 TS typecheck 通过。
Android Debug 121 项通过；businessAcceptance 79 项通过，lint 0 错误/19 警告，构建及签名验证通过。网页前轮 140 项与变更组件最终 32 项（4 新增）通过，typecheck/lint/build 通过。
公开 28 次 HTTPS 检查全部成功、14 文件哈希匹配；线上浏览器桌面 1280/手机 390 无横向溢出，404 降级、账号未核验及 receiveOnly 提示正确。模拟响应另覆盖成功/协议不支持/离线/不可执行。真实采集 POST、写操作、发送均为 0；线上被拦写入尝试为 0。
截图 wrapper/CDP 均失败，没有像素级验收。浏览器任务 38 已恰好结束一次、keep=[]，不得复用。软件证据不替代真机验收。

恢复后先核对部署、HEAD 与保护差异，复用未变证据，不自动重跑全套。后端包、哈希、备份助手静态审查及 prepared-api-deploy.py 仅准备待审，未执行。按 [fleet-deploy §7](../runbooks/fleet-deploy.md)须获准明确时间窗、变更内容和回滚标准，才能部署/重启生产后端。兼容后端必须先于任何获准的 v10 安装。之后的手机安装、设备操作、真实采集/回复、duty 仍需各自授权与设备锁；不可把“继续优化”视为业务权限。

## 证据与归档

外部根：/Users/wangziheng/CloudCtlExternal/acceptance/20261011-im-body-collection/。重点为 FROZEN-CONTRACT.md、api-executor/release/、mobile-executor/delivery.json、mobile-packaging/delivery.json、v10-delivery-manifest.json、web-executor/、github-sync.json、main-integration-check.json、public-verification.json、browser-online.json、screenshot-limitation.json。外部证据不在 fresh clone 中，缺失时说明限制，不扩大搜索或授权。
[上一版消息聚合交接](../archive/2026-10-11/HANDOFF-im-inbox-checkpoint-20261011.md)逐字节归档，SHA256 6e155bea0c1454d7697324fade16dd65907cc513e23eb99ea9ff213cf7cdb886。
tasks.json SHA256：3a1ae74049ba843bc66a77d4a0cb98be259130897ff324b17d106e5d6bb46fcb。
