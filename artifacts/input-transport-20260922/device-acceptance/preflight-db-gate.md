# C4 一加 9R 真机准入：受阻

日期：2026-09-22（Asia/Shanghai）
设备：USB `b0644fb5`；Wi-Fi `192.168.5.6:5555` 为同一实体，不并发使用。

- 只读核验本机运行中的 Control API 数据库连接，事务以 `READ ONLY` 开启并以 `ROLLBACK` 结束。实际连接为本机 `127.0.0.1:5432/cloudctl`；`device` 表总计 0 行，目标 `4aabc387-6e4b-4b59-a525-b1c119ec7f5b` 及 serial 均无记录。因此该库里 lease、CLAIMED/RUNNING、preview、debug session 查询均为 0 行，**不能证明登记设备的生产 lease 空闲**。
- 本地 `scripts/device_lock.py status b0644fb5` 为 `initialized:false`、`FREE`，只表明本地锁库没有记录，不能证明设备外部空闲。
- 先前 ADB 只读预检确认 OnePlus 9R / Android 14 / API 34 / ColorOS，搜狗为当前输入法，CloudCtl IME 已启用且无障碍已启用；预检桌面截图见 `preflight-home.png`。但缺生产租约的权威读取以及现场人工空闲确认。
- 准入结论：`blocked_hardware`。未 acquire `DEVICE:b0644fb5`，未安装新 APK，未点击或写入闲鱼，未真实发送/发布/评价，也未启动 Grok 4.7 真机验收。
- 下一检查点：取得该已登记设备的权威生产 lease/任务/preview/debug 空闲证据和能看到手机的人对物理空闲的确认；随后由控制者持精确 serial 锁，再安排 Grok 4.7 执行仅限 API 34、停在业务副作用前的验收。
