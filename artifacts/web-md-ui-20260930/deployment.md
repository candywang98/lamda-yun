# 文档对照网页优化上线记录

用户明确“授权上线”后，控制器持服务器既有 /home/ubuntu/cloudctl-mobile/.deploy.lock 独占锁，部署精确候选 0078c5c5ec35a02f34ac3f4aa0670fbb6c4d4159。

- 线上入口：https://43.133.243.154.sslip.io/cloudctl-mobile/
- 激活时间：2026-10-01T03:00:23Z；浏览器核对时间：2026-10-01T03:04:24.757Z。
- 静态目录：/var/www/cloudctl-mobile-web-md-0078c5c5ec35。
- 原目录及回滚目标：/var/www/cloudctl-mobile-web-qa-ec1b0cc95dfc。
- 包 SHA256：8714dc7dfce4fdeb9521162bd31b37ec7b3ac26018993e9bac631caaaadd6163。
- 静态备份：/home/ubuntu/cloudctl-mobile/backups/web-md-0078c5c5ec35/web.tar.gz，全部归档文件哈希核对通过。未操作业务数据库备份/恢复。
- 认证、mock=false、dev-auth=false、base=/cloudctl-mobile/ 保持原配置。

外部认证 HTTPS 核对：6 个网页入口、14 个包内文件、6 个 API 读取、2 个健康检查均为 200；HTML、资源、导入模板及 version.json 与发布包逐字节一致。receiveOnly=true、mode=NOTIFICATION 保持原配置。

线上 ego-browser 核对：旧 /orders 跳转到同步表单，表单不混入订单表格；商品管理已同步订单 14 条、当前标签正确；导入示例仅生成一行预览且不保存；目录 15 个模块、6 个快捷入口；任务详情显示真实状态，320/390/1440 像素下弹窗在视口内且无内容横向溢出，焦点位于弹窗，Escape 正常关闭。记录中 GET 请求全部为 200，无页面异常、失败 API 响应或业务写入。Space 1 已完成并关闭；此前 Space 18/36 未操作。未重新尝试已超时的截图接口，不声明截图视觉验收。

API 目录 /home/ubuntu/cloudctl-mobile/releases/order-delivery-557f547、PID 2790688、数据库版本 20260926_0035 保持不变，无后端重启或数据库迁移。切换前后 OUT 消息计数均为 23、mobile_task 计数均为 379。设备、发送、真实发布和任务台账未修改，原 fleet 工作区改动哈希保持不变。未 push；此次只激活已审查静态包。

第一次外部校验因中文模板 URL 未编码发生 UnicodeEncodeError，远端自动切回旧目录；外部 HTTPS 确认旧版本已恢复，服务未变化。修正校验 URL 编码后复用相同发布包和已核对静态备份，重新持锁切换并完成所有外部校验。线上浏览器验证最初的跨 CLI 回合临时认证未延续导致读取等待，随后在单个认证回合中完成验证；不将该临时工具状态记为应用错误。

回滚时持有同一部署锁，将 /var/www/cloudctl-mobile-current 原子切回原目录，随后做外部认证版本/资源/API 核对。保留旧哈希资源供已打开页面使用，无需数据库回滚或后端重启。

本次验收只确认网页交付及读取流程；不代表未接入后端能力已经实现，详见 REVIEW.md。
