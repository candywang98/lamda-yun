# 消息正文单屏读取交付记录（2026-10-11）

## 范围与限制

用户授权继续消息聚合优化，并说明手机基本固定闲鱼账号；这不等于运行时身份核验。账号始终为 UNVERIFIED，联系人仅为标题显示名称匹配，方向为几何启发式。
网页手动确认设备/联系人、账号未核验及打开聊天可能标记已读后，才允许发起独立 ui.collectImChat 单动作。快照与通知分开保存/展示；仅一屏无障碍可访问正文，保留方向与顺序，原消息时间为 null，数量/文字/总大小截断明确标记。不承诺完整历史或平台原始时间，不输入、不发送、不启用 duty、不滚动历史。

## 实现与交付版本

API 提供显式能力双门禁、冻结 target、租约/epoch/绑定复核、幂等创建、专用原子完成接口；通用完成不能绕过。Android 有限导航与唯一联系人点击、读前/读后/持久化前身份复核、漂移即停止、持久化 outbox 重启重放同一快照、替换租约安全失败；旧补正文和 duty 读取也增加边界。Web 覆盖能力降级、目标确认、幂等提交、轮询及身份切换隔离。
冻结协议 im-chat-collection/1 (20261011.1)：root maxRunSeconds=60 与云端 controlEpoch；step 仅 stepId/action/timeoutMs/target，不把动态 epoch 写入冻结 step。详见外部 FROZEN-CONTRACT.md。

| 分支 | 源码 SHA | 状态 |
| --- | --- | --- |
| integration/im-chat-collection-20261011 | 66e1ab475d4fd65b8afee78853ea65509aee5073 | main 已集成，分支远端读回一致 |
| release/api-im-chat-collection-20261011 | 82abeeee78bc746f8d41e05c3b47aded645740a1 | 实际旧 API 发布基线的兼容候选，未部署 |
| release/web-im-chat-collection-20261011 | 01877be2fb677196279ab2d21ffdcda34e8ddaef | 前端已上线并提交确认 |
| release/im-chat-collection-v10-20261011 | f3200593f6b9a1b2e217f4067b04a33639a39971 | 已签名本地产物，未安装 |

main 未推送；原 51 个文件、index/原差异和 tasks.json 保持。不可混用 main SHA、网页发布 SHA 与 APK SOURCE_REVISION。
v10 包名 com.company.cloudctl.companion，10 / 0.1.0-business-acceptance.10，SOURCE_REVISION=f320059；稳定本地产物 /Users/wangziheng/CloudCtlExternal/apk-delivery/cloudctl-companion-v10.apk，SHA256 c6ad2ec6f0adde0a971528a58682e9ba27f1337c686d37da7f987f0b2cef0dfb。
复用原 A→B lineage，SHA256 70b5ee0f728d651ec077161b5752a49648d629bb1dd80818953024b6b9595e05；API 29/34/支持范围验证通过，installedData=true、rollback=false，keystore/lineage 前后未变，签名产物 ZIP 内容与 Gradle APK 一致。v9 未变，v10 未复制到手机。

## 软件与浏览器验证

- API 候选基于实际旧发布 557f547：161 passed、2 skipped；4 mypy/4 ruff 为既有问题，0 新增。
- 共享 OpenAPI 455 行增量，兼容性检查 1 passed；手写 TS typecheck passed。
- Android Debug 121 tests；businessAcceptance 79 tests，含真实发布 HTTP fixture 经 claim adapter 与严格 parser；lint 0 errors/19 warnings，构建成功。
- Web 前轮 140 tests 与变更组件最终 32 tests（4 新增），types/lint/build 通过。模拟响应覆盖 1280/390 宽度下成功、协议不支持、离线、不可执行、404，0 真实采集 POST、0 发送。
- 公网 28 次 HTTPS 请求全部成功、14 文件哈希匹配。线上浏览器桌面 1280/手机 390 无横向溢出；新面板对旧 API 的 404 如实禁用，UNVERIFIED/receiveOnly 提示正确，0 被拦写入尝试、0 真实写入/发送。
- wrapper/CDP 截图均失败，无像素级验收；浏览器任务 38 已结束恰好一次、keep=[]，不得复用。

## 前端发布与后端停点

2026-10-11T09:09:48.068631Z（北京时间 17:09:48）激活，09:16:03.138214Z（17:16:03）提交确认。当前 /var/www/cloudctl-mobile-web-im-01877be2fb67；旧目标 /var/www/cloudctl-mobile-web-im-de8629edb5c4。备份 /home/ubuntu/cloudctl-mobile/backups/web-im-01877be2fb67，SHA256 dbbb194d4fb244d10c733449c29f6174caf05ab76c7cb605c0cf1aecce3fd746，保留 19 个旧哈希资源。
本轮不是零失败发布：首次 tar 含 AppleDouble，在激活前被拒绝；之后简单 stdin 启动方式触发自动回滚，API 未变。修正包 SHA256 04e7f99e9d512970558332fdd8a96732fb9b61f55298e15ce0d9c079aa59fc80；改用持续进程与 marker 重新激活，复用验证过的旧版备份，最终已提交。
API 前后仍为 order-delivery-557f547、MainPID 2790688、active；backendRestarted=false、databaseMigrated=false。前端上线不代表正文采集可用：线上旧 API 对新查询返回 404，新按钮禁用；v10 未安装，尚无硬件验收。
后端包、哈希、备份助手静态审查与 prepared-api-deploy.py 均仅准备待审，未执行。按 docs/runbooks/fleet-deploy.md §7，生产后端变更须获准时间窗、内容及回滚标准；兼容后端先部署，另行获准后才能安装会声明新能力的 v10，并开展设备锁保护下的真机验收。

## 恢复与证据

外部根 /Users/wangziheng/CloudCtlExternal/acceptance/20261011-im-body-collection/：api-executor/release/、mobile-executor/delivery.json、mobile-packaging/delivery.json、v10-delivery-manifest.json、web-executor/、github-sync.json、main-integration-check.json、public-verification.json、browser-online.json、screenshot-limitation.json。缺失外部文件应明确缺失，不扩展搜索或授权。
恢复先核对 HEAD、部署和保护差异，复用未变证据；软件通过不等于硬件接受。台账未改，未安装、操作手机、开启 duty 或真实发送。“产品介绍/更新日志”移除保留；AutoJS、Recipe 和其他模块重构仍仅讨论。
