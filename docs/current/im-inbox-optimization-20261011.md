# 消息聚合优化记录（2026-10-11）

本轮用户明确要求优化消息聚合。网页展示和交互第一轮已上线；完整正文采集、平台账号隔离及真实回复仍未验收。本记录不授予后续设备或业务操作权限。

## 已实现

- 汇总设备会话，显示设备名称和目标联系人；搜索仅覆盖已加载会话及最近消息。
- 常见通知占位文案显示“通知提示 · 正文待采集”，保留原始文字及换行。文字匹配仅为提示，不证明消息来源。
- 显示“账号：未核验”；设备名称不作为平台登录账号。用户尚未回答固定账号还是切换账号的问题。
- 明确区分回复任务提交、等待手机确认、手机报告发送完成、任务失败和未知状态；不声称买家收到或已读。
- 回复前核对设备、平台、联系人及正文；草稿和回执按会话保存在内存。用户或租户变化清理数据并丢弃旧请求结果，同身份登录态刷新保留草稿。
- “查看正文采集设置”打开现有设备监控面板并选择当前设备，不修改模式、不保存、不创建任务。
- 回复只有权限、支持平台和明确 receiveOnly=false 同时满足才能提交；未知配置保持禁用。

## 能力边界

只读 API 预检采样设备为 receiveOnly=true、NOTIFICATION。本轮没有开启值班模式或发送消息。
现有值班采集会进入手机聊天、占用界面，可能改变已读状态；正文读取完整性和稳定性待验证。
当前通知及会话没有平台登录账号身份，不能据此可靠隔离同设备换号后的历史。
原生回复后补正文路径存在采集身份复核缺口，不能直接包装成独立读取接口。
独立“读取正文”路由、第二 APK、账号隔离均未实现。相关依据见外部 CAPABILITY-NOTES.md。
APK 架构及 Recipe 改名、移动或隐藏仍属讨论方案，未实施。

## 版本与验证

发布源码：de8629edb5c4d95332e9b60b3c30b12694a9e684，分支 release/web-im-inbox-20261011 已推送并读回核验。
main 集成代码基线：98644c02feba863c28a8b3a9fc53e2213e6ac46b；本轮没有推送 main。
发布以此前线上菜单精简版为基线，不将 main 其他未获准内容一并发布。
原 51 个文件哈希、原暂存区与 tasks.json 保持不变。

- 1a6d150：5 个 IM 测试文件、106 项通过。
- de8629e：新增同身份刷新回归后，IM inbox 61 项通过；其余未变的 46 项复用前轮证据，不称最终提交重跑了全部 107 项。
- 最终 typecheck、生产构建退出 0；前轮 lint 为 0 errors / 218 warnings。最后变更为 watcher 修复及回归测试，未重新运行 lint。
- 本地浏览器 7 项断言通过，包含 390 宽度无横向溢出；不是像素级或真机验收。
- 测试保留 Node localStorage 实验警告；构建保留包体积警告。

## 上线结果

2026-10-11 16:09:23 北京时间切换上线，16:12:45 提交确认。deployment-result.json 为 committed=true；未执行回滚，无部署失败。
线上：https://43.133.243.154.sslip.io/cloudctl-mobile/im；本地只读预览：http://127.0.0.1:5173/im，源目录未换，HMR 已更新，readOnly=true。
当前目标：/var/www/cloudctl-mobile-web-im-de8629edb5c4；上一目标：/var/www/cloudctl-mobile-web-menu-87fade44bbc2。
备份：/home/ubuntu/cloudctl-mobile/backups/web-im-de8629edb5c4/web.tar.gz，29 个文件哈希核验；包 SHA256：76841d990c2c37399a8f769ce2af8a840d9e4fe77cfa1aaca825317661c9d4ee。
保留 17 个旧哈希资源以兼容已打开页面。部署持现有排他锁原子切换；以后回滚需授权、持锁并核对当前指针。
后端发布前后 MainPID 2790688、WorkingDirectory 指向 order-delivery-557f547、active，没有重启或迁移。

公开核验 28 次 HTTPS GET 均为 200，14 个产物哈希一致。线上浏览器 8 项功能/DOM 检查通过，覆盖版本、搜索、上下文、通知提示和原文、仅接收、当前设备设置入口及 390 宽度无横向溢出。
blockedWriteRequests=[]，没有真实发送或设备操作。初始认证失败及重载后临时 CDP 认证丢失已通过现有站点认证解决，未记录凭据，源码不受影响。
Page.captureScreenshot 一次超时，保留 screenshot-limitation.json；无截图，不声称像素级视觉验收。浏览器任务 37 已结束一次，见 browser-task-finished.json。
这些是发布时观测，不替代完整正文、账号身份或真实回复验收，也不证明未来运行状态。

## 证据

外部证据根：/Users/wangziheng/CloudCtlExternal/acceptance/20261011-im-inbox-optimization/。
web-executor/delivery.json 记录精确命令、退出码、源码哈希；prod-dist/version.json 与 payload.sha256 记录产物。
readonly-api-preflight.json、CAPABILITY-NOTES.md、controller-review.json、integration-check.json、github-sync.json、browser-local.json 分别记录预检、能力边界、评审、集成、同步及本地浏览器结果。
deployment-result.json、public-verification.json、browser-online.json 记录已完成部署与回验；screenshot-limitation.json 和 browser-task-finished.json 记录截图限制与任务结束。
外部证据不随 fresh clone 提供，缺失时应报告限制，不能据此重做设备操作。
