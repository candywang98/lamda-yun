# 网页发布与 GitHub 同步记录

日期：2026-09-28。用户明确要求将网页修复上线，并及时同步 GitHub。

## 已完成交付

| 项目 | 实际结果 |
| --- | --- |
| 线上入口 | `https://43.133.243.154.sslip.io/cloudctl-mobile/` |
| 最终网页源码 | `e328929262e40f1333f9d274c340aafe0e36604b` |
| 最终静态版本 | `web-qa-e328929262e4` |
| 最终激活时间 | 2026-09-28 19:23:14 +08:00 / 11:23:14 UTC |
| 静态目录 | `/var/www/cloudctl-mobile-web-qa-e328929262e4` |
| 网页发布包 SHA256 | `84498ac0832c44289b106b8449c60b772e894fb268bc6ae0cad2f0ce9bc1232c` |
| 版本查询 | 同一认证下访问 `/cloudctl-mobile/version.json` |
| GitHub | `candywang98/lamda-yun`，分支 `main` |
| 后端版本 | 保持 `order-delivery-557f547`，PID 2790688，未重启 |
| 数据库版本 | 保持 `20260926_0035`，未迁移 |

此前 31 个仅保存在本地 `main` 的提交已补推。随后按顺序推送：

1. `097d4ac`：工作台会话/权限、商品批量编辑、消息分页与竞态、订单筛选、设备刷新和商品手机布局修复。
2. `390bfcc`：CI 在类型检查前构建共享契约包，并安装项目声明的 LAMDA 可选依赖。
3. `e328929`：线上真实长设备名、长订单号导致的页面溢出修复，以及相应合成数据回归。

本目录发布记录和线上测试断言的后续提交不改变上述已部署的网页源码。
原有未提交 Android 测试改动及无关临时材料未混入本轮提交。

## 发布与备份

- 使用服务器既有 `.deploy.lock` 独占锁串行发布。
- 两次发布均完成数据库快照备份、隔离库还原与 69 张表摘要一致性验证。
- 保留原网页、共享配置、对象存储和数据库备份；凭据和备份内容只留在服务器。
- 原子切换 `/var/www/cloudctl-mobile-current` 符号链接，保留旧哈希静态资源，兼容已打开页面。
- 正式构建使用 `/cloudctl-mobile/` base，关闭 Mock 和前端开发身份头，保留既有 HTTPS / Basic Auth。
- 每次切换前后校验 5 个页面入口、2 个入口静态资源和 5 类认证 API 读取。
  未认证页面/API 仍返回 401；认证后的 HTML、资源和版本文件与发布包逐字节一致。
- 后端进程、数据库 schema、通知模式及 receiveOnly=true 均未改变。
- 两次切换前后，mobile_task 数量均为 379，OUT 消息数量均为 23。
- 未执行真实发送、采集、发布商品、删除、手机触屏或 APK 更新。

首次发布 `097d4ac` 于 19:13:22 +08:00 激活，证据为
`activation-result.json`；最终发布证据为 `activation-final-result.json`。
第二次发布收口了真实线上数据检查中发现的订单/消息长内容溢出。

最终版本的直接回滚目标为 `/var/www/cloudctl-mobile-web-qa-097d4ac68088`，
更早的 `/var/www/cloudctl-mobile-order-delivery-557f547` 也完整保留。
回滚时持有同一部署锁，原子切回旧静态目录后重验认证与资源；不重启后端、不回滚或覆盖数据库。
最终备份目录：`/home/ubuntu/cloudctl-mobile/backups/web-qa-e328929262e4`。

## 验证

| 验证范围 | 结果 |
| --- | --- |
| Web 单元测试 | 45 个文件，519/519 通过 |
| 本地浏览器回归 | 桌面 Chromium + Pixel 7 模拟视口，18/18 通过 |
| 真实线上只读浏览器检查 | 订单、消息、设备、商品，桌面/手机共 8/8 通过 |
| 正式 Web 构建 | vue-tsc + Vite，通过 |
| 全工作区 TypeScript 检查 | `pnpm contracts` 后 `pnpm typecheck` 通过 |
| 本地 Python 类型检查 | `mypy`，162 个源文件通过 |
| 修改文件 lint / diff | 通过 |
| GitHub 已部署源码的 frontend CI | `e328929`，run `36415116794`，success |

长内容回归先复现 3 个失败，再验证修复。线上测试使用现有合法认证和真实 API，
不是 Mock；同时拦截所有非 GET/HEAD 的业务请求，结果中未出现写请求、API 错误或页面运行异常。
测试等待页面加载结束后再截图和检查视口宽度。
设备本身的离线原因提示是正常业务状态，不作为网页加载故障，也不代表设备已通过验收。

只读线上检查命令：

```bash
env CLOUDCTL_DEPLOY_SMOKE_URL=https://43.133.243.154.sslip.io/cloudctl-mobile \
  VITE_CONTROL_API_URL=http://127.0.0.1:9999 \
  VITE_CONTROL_API_DEV_AUTH=false VITE_OPERATIONS_MOCK_ENABLED=false \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  PLAYWRIGHT_ARTIFACTS_DIR=/tmp/cloudctl-web-online-verified-20260928 \
  pnpm --filter @cloudctl/web exec playwright test e2e/deployment-smoke.spec.ts --reporter=line
```

真实页面截图仅留在本地 `/tmp/cloudctl-web-online-verified-20260928/test-results/`，
未推送到公开 GitHub 仓库；认证凭据未写入测试文件、截图、版本文件或 trace。

## 仓库全量 CI 未全部通过

不能将网页验收通过表述为全仓库 CI 已绿。已部署源码 `e328929` 的
远端 run `36415116794` 已结束：frontend 成功，Python 在 `Run pytest -q`
步骤失败，Android 在 `Run cd mobile/companion && ./gradlew lint test` 步骤失败。

前一轮 run `36414289774`（源码 `390bfcc`）已确认的失败明细如下；
以下统计来自该轮日志，不冒充后续运行的统计：

- Python：1153 passed / 147 skipped / 20 failed / 42 errors。
  主要涉及 Linux 文件系统被识别为 `ext2/ext3` 后锁工具拒绝、Q02 历史冻结 SHA 祖先检查，
  另有一个负载测试完成数量不足。尚未完成这些问题的独立修复和验收。
- Android：执行到 `verifyReleaseUpdatePublicKey` 后因缺少
  `CLOUDCTL_APP_UPDATE_PUBLIC_KEY` 而失败。没有伪造公钥、绕过发布验证或发布 APK。
- 修复后的前端 CI 已通过。Python 和 Android 的失败不能用前端结果覆盖，
  也不能据此提高真机验收状态。后续新提交的 CI 状态以 GitHub 对应 run 为准。

上述失败不在本轮部署的网页静态代码中；本轮未升级线上后端或手机软件。
任务台账 `docs/current/tasks.json` 的开发/验收状态未在本轮擅自翻转。

## 后续交付约定

按用户本次明确要求，网页版修复的交付应完成：
本地验证、GitHub 同步、受控上线、真实线上回验和发布记录。
如存在阻断，明确说明阻断及已完成部分，不能仅把本地测试通过作为上线完成。
这一约定不扩大真实消息发送、商品发布/删除、设备操作或 APK 发布的授权范围。
