# C5 用户重连后复查

2026-09-23（Asia/Shanghai）。主会话直接执行，无工作流/子智能体。

## 最新状态

- 用户已按此前要求完成USB重连。02:37检查三台get-state=device，读取机型约0.05秒，原先两台华为均超时的状态不再成立。
- VOG APH0219624006517：Companion 0.1.0已安装，bindingId=95d17bbe-5ea9-4471-963f-8da5a8467409，deviceId=050cdb78-c815-4989-8744-2a519d33079a；服务器确认该精确binding有效。无障碍enabled=null、Bound services={}，需要用户手工开启。
- ELE GBGDU19830002425：闲鱼已安装；Companion与acceptance均未安装；无Bound服务，需安装后注册绑定及手动授权。
- OnePlus b0644fb5：LE2100，生产Companion 0.1.0已安装；bindingId=202ff9cb-6b6d-4ccc-bbf7-31bd91edb51e，deviceId=4aabc387-6e4b-4b59-a525-b1c119ec7f5b，服务器确认精确binding有效；CloudCtl无障碍Bound，服务器IM模式NOTIFICATION、enabled=true；acceptance未安装。
- 两台已绑定机均指向 https://43.133.243.154.sslip.io。

原始只读取证：C5-reconnect-probe-20260923-023722.json、C5-reconnect-state-20260923-023811.json。

## VOG传输波动与处置

VOG读取APK时30秒超时，部分文件只有4,259,320字节，不能用作签名证据。随后小命令也超时；ADB日志有该设备USB read failure/pipe stalled记录，尚不能由此断定电缆或手机根因。未重启全局ADB、未重启手机。只执行 adb -s APH0219624006517 reconnect，短暂断开并重新枚举后，getprop与dumpsys accessibility再次成功。ELE和OnePlus连接未被重建，未驱动OnePlus Wi-Fi别名。VOG最终签名核对仍未完成，不能进行覆盖安装。

## 服务器只读检查

通过SSH seoul执行，不改服务/配置/库：
- active service: cloudctl-mobile-api.service，release /home/ubuntu/cloudctl-mobile/releases/p34-571ce32，uvicorn workers=1。
- /health/ready 返回ok、postgresql。
- 数据库版本20260920_0032；IM线程旧唯一键uq_im_thread_peer仍在，0033未部署。
- 两个精确binding均revoked_at IS NULL；没有两台设备的未到期device_lease。
- OnePlus有一条2026-09-01历史任务id=6cc8b9aa-9851-4410-a270-24f399285f99，status=SUCCEEDED但business_state=QUEUED；步骤只有ui.find/ui.assert/run.log，不含发送。此状态分歧需在部署准入时复核，不擅自修改/取消，也不能仅依business_state就称任务正在执行。

## 放行结论

仍未完成C5，但应由“华为连接全面超时”更新为“重连恢复/有VOG大传输波动；VOG待手工无障碍、ELE待安装绑定，服务器仍旧版”。未安装、卸载、清数据、触屏、静默授权或发送消息；未做生产迁移、重启或发布。

生产更新必须按docs/runbooks/fleet-deploy.md授权维护窗口、确认占用、备份/校验、兼容与回滚后实施。全仓类型门遗留亦须纳入放行决策。用户对USB重连的确认不代表生产重启或数据库变更授权。C6真实三机消息与30分钟观察未做，D保持进行中。
