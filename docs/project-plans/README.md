# 项目计划快照

本目录保存项目外层目录的计划与交接文件，便于从 GitHub 获取完整的开发上下文。文件内容与源文件一致，SHA-256 见 `snapshot-manifest.json`。

## 当前计划（2026-09-16 更新）

**唯一活跃任务源是 [`docs/current/tasks.json`](../current/tasks.json)（fleet-first-20260916.1，R02 已激活）。**
调度与验收状态以该文件的 `dev_state` / `acceptance_state` 为准，校验用 `python scripts/plan_guard.py docs/current/tasks.json`。

本目录两份 Excel 不再是活动调度源：
- [lamda_yun_一期计划_多智能体版.xlsx](lamda_yun_一期计划_多智能体版.xlsx)：冻结历史基线（R02 已全表导入并完成 61 旧项/50 P 映射核对），只读。
- [lamda_yun_一期计划_智能体执行版.xlsx](lamda_yun_一期计划_智能体执行版.xlsx)：验收与范围基线，只读；其 `09_执行记录` 仍由控制器按用户要求持续追加进度行。

`docs/phase1/multi-agent-work-items.json` 已标记 HISTORICAL（supersededBy 指向 docs/current/tasks.json）。

## 历史资料

以下文件 2026-09-16 归档至 [docs/archive/2026-09-16/](../archive/2026-09-16/)：V1重审开发计划 xlsx、一期审阅与实施 xlsx、一期智能体实施手册 md、计划优化问题清单 md、项目交接说明 md、delivery/task-status md、yuyou 问答旧稿。旧文档中的完成比例、设备状态及待办事项可能已被新计划或较新的验收记录取代。

## 上传边界

源码、测试、迁移、依赖锁文件、开发文档和任务 Markdown 报告纳入版本管理。新增原始调试数据、设备数据库、APK、密钥、依赖目录和构建缓存不上传；任务报告中引用的原始证据可能仅在本地可用。本次不改写既有 Git 历史。
