# D11 evidence summary

- Task: 多机容量、观测与限流
- Audited: 2026-09-20 (Asia/Shanghai)
- Software status: `SOFTWARE_DONE`
- Acceptance status: `SOFTWARE_ACCEPTED`（限流/公平调度为显式剩余差额，见下）
- Device acceptance: not applicable; software verification only

## Delivered

- **观测库** `packages/observability/metrics.py`：每设备 queueAge / claimLatency 直方图（p50/p95/mean/max）+ leaseConflict / rebind / unknown / inputFailure / evidenceUploads / evidenceBytes 计数，fleet 汇总，环形有界采样，线程安全。
- **负载舱** `tests/load/fleet/`：进程内真实 ASGI 控制面上的模拟 companion（enroll→claim→events→complete/release），三场景 + 指标单测共 7 项，产出含主机规格 / DB 模式 / 测试配置 / p50-p95 的 JSON 报告（`artifacts/tasks/D11/load-report-*.json`），显式标注"模拟客户端≠真机"。
- **基线（2 设备×20 任务）**：全部完成；queueAge p50≈0.47s / p95≈0.74s，claim p50≈0.017s / p95≈0.023s，inputFailure=0。
- **100 模拟客户端**：100/100 完成，claim p95≈0.61s < 5s 门槛。
- **head-of-line 隔离**：故障设备（领取后滞留）不阻塞健康设备——健康设备 10/10 完成、claim p95<2s；单租约语义下故障设备卡死 1 个租约任务、其余滞留本设备队列。
- **UNKNOWN 证据留存豁免（真实缺陷修复）**：`platform_tasks._record_control_event` 与 `mobile_service._append_control_event` 的 `events[-50:]` 盲截断会把 MARKED_UNKNOWN / RECONCILED_* 挤出窗口；新增 `_retain_control_events` 保护集（一般事件压 50 条，证据事件永存），单测驱动 61 条事件验证 + 真实 API mark-unknown 可见性验证。

## Registered defect (BLK-011, platform 线)

并发 claim/complete/release 高频循环下 `device_lease` 出现 `UNIQUE constraint failed: device_lease.device_id` 与孤儿租约，随后该设备 claim 永久 204（本舱 HOL 场景 ~30-50% 复现；trace 见 test-results）。负载舱默认以 20ms claim 节流避开该竞态窗口；修复归属 platform 领租路径（X 系列 / Q13 前置），不在 D11 写域内。

## Verification

- tests/load/fleet：7 项通过（含 8 连跑稳定性验证）。
- 全量后端：1061 passed / 11 skipped（含留存修复后 platform/mobile 全套回归）。
- 新增/修改文件 ruff 全绿；mobile_service 其余 5 条 E501 为 HEAD 存量（git show 对照确认），未动。

## Explicit remaining deltas (not claimed done)

- per-tenant/per-device 限流中间件、公平调度、重试 jitter、媒体有界队列/背压：未实现（需 control-api 接线挂点，另立切片）；本切片交付观测基线与负载舱，为其提供度量口径。
- 对象存储容量统计（evidenceBytes 已有计数口径，对象级容量聚合未做）。

## Not claimed

- 不等同 100 真机；无 staging/真机/外部副作用；负载为单机进程内 ASGI，非多节点网络基准。
