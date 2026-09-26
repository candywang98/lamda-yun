# 2026-09-24 生产只读复核

本记录只保存只读查询结果；没有执行迁移、重启、调度、任务创建、设备写入或真实公众号调用。

## 连接与版本

- 主机：`seoul`
- `cloudctl-mobile-api.service`：`active`
- PostgreSQL：`18.6`
- Alembic：`20260920_0032`
- 查询时间：`2026-09-24 14:58:42+00`

## 占用快照

- `device_lease`：`active_leases=0`、`expired_uncanceled_leases=0`、`total_leases=5`
- `task_schedule`：`enabled_schedules=0`、`total_schedules=0`
- `device_preview`：`active_previews=0`、`total_previews=0`
- `mobile_task` 当前分组：
  - `CANCELED / CANCELED`：1
  - `FAILED / CANCELLED`：7
  - `FAILED / FAILED`：140
  - `SUCCEEDED / QUEUED`：1（历史组合，未修改）
  - `SUCCEEDED / SUCCEEDED`：227

本次使用真实 schema 查询；`mobile_task` 没有 `kind` 列，之前按该列查询的命令已废弃。任务表没有观察到非终态任务或有效租约，但这只是本次只读时间点快照，任何写操作前仍需重新核对。

## 证据来源

- `$PI_SCRATCH_DIR/production-schema-readonly-20260924.log`
- `$PI_SCRATCH_DIR/production-occupancy-readonly-20260924.log`
- `$PI_SCRATCH_DIR/production-version-readonly-20260924.log`

## 边界

- 0 active lease 不等于手机物理空闲，也不替代设备锁 SOP、实际前台窗口核对或 Companion 无障碍健康检查。
- 本次没有获得真实公众号权限、素材、发布授权，也没有发送/发布任何内容。
- 不因该快照提升 F16、Q13、Q15、Q16 或 Z10 的验收状态。
