# C5 一加 9R API34 真机准入

日期：2026-09-22（Asia/Shanghai）
目标：USB `b0644fb5`；Wi-Fi `192.168.5.6:5555` 是同一实体，本轮不使用无线 alias。

用户已确认现场没有任何人使用设备，并授权本轮测试。控制者在首尔权威 `cloudctl-mobile-postgres` 内执行只读事务（`BEGIN READ ONLY`，5 秒 statement timeout，`ROLLBACK`），没有读取凭据文件、写数据库或重启服务。服务 `cloudctl-mobile-api` 为 active，数据库迁移版本 `20260920_0032`。

2026-09-22 20:25:32 Asia/Shanghai 的权威读数：

- 登记设备：`4aabc387-6e4b-4b59-a525-b1c119ec7f5b`，`oneplus-9r-b0644fb5`，`REGISTERED`，有近期 heartbeat。
- `device_lease`：仅一条旧 `AUTO` 记录，2026-09-20 已取消且过期；`active=false`。fencing token 303 只作为旧记录身份，不作锁密钥。
- `mobile_task`：`CLAIMED`/`RUNNING` 为 0 行。
- `device_preview`：0 行；活动 `debug_session`：0 行。
- 已登记的未撤销 mobile binding 存在，说明安装更新可能保留既有生产身份；本轮不 claim 新任务、不改生产租约。
- 本机未发现活跃 scrcpy、LAMDA、Appium 或其他 ADB 安装/驱动进程；USB 与无线两条 ADB alias 属同一物理设备。

控制者于 2026-09-22 20:25:46 Asia/Shanghai 取得本地 `DEVICE:b0644fb5` 锁，fencing=1，TTL=7200 秒。owner token 仅在本机 mode 0600 临时文件，未记录到本证据、命令参数、子代理任务书或权威进度表。锁释放前若接近到期必须由控制者续租。

结论：硬件准入检查点通过，但这只允许安全的 API34 真机字段验收，不能代表输入功能已在闲鱼 Flutter/ColorOS 验收通过；API 29–32 均未真机验收。硬停：不真实发送聊天、不发布商品、不提交评价、不删除、不收费、不推广。
