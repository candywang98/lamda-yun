# docs/current — 单一活跃任务源

**本目录是 fleet-first-20260916.1 计划激活后的唯一机器任务源。**

- `tasks.json`：50 条差额/验收任务（来自交付包 `lamda_yun_delivery_20260916/data/tasks.json`，
  原始 SHA256 `2e8636ec7443f837bfe4e6ad85e3ab9bc9dd77fec342dfdd34d0f281e5ad7acc`）。
- `baseline.json` / `evidence-index.json` / `scope-decisions.md`：R00 产出。
- 校验：`python scripts/plan_guard.py docs/current/tasks.json`（只读审计）。

## R02 激活记录（2026-09-16T22:59:24+08:00）

| 项 | 结果 |
|---|---|
| 多智能体版全表导出 | `/Users/wangziheng/Desktop/LAMDA云控系统/lamda_yun_delivery_20260916/evidence/local-active-all-sheets.json` SHA256 `4e6b2f6728abd56995cb8a0743cc47b41639198155d18108758d128a2dcc2489` |
| 执行版全表导出 | `/Users/wangziheng/Desktop/LAMDA云控系统/lamda_yun_delivery_20260916/evidence/local-acceptance-all-sheets.json` SHA256 `9071746140b1c984fa54c7a91e9ec4bdb76f6b85aea9339f67ac01430a704104` |
| 61 旧调度项映射 | 全部映射到新任务，无缺失、无空承接 |
| P00–P49 覆盖 | 50/50 全覆盖（验收卡50项 ↔ package_coverage.csv） |
| 范围冲突登记 | 仅 S03（抖音/公众号/XHS视频口径）与 P27（XHS视频），已在交付包登记，待逐项裁决 |
| 旧 P14 队列 | `docs/phase1/multi-agent-work-items.json` 标记 HISTORICAL，不再是全局 authority |

## R02 补记（2026-09-20）：状态翻转与 WAIT_CONTRACT 重算

- `tasks.json` 的 `authority` 由 `CANDIDATE_NOT_ACTIVATED` 翻转为 `ACTIVATED`（激活事实以 @bf6529b 为准，补记 `activated_at`）。
- 22 个 WAIT_CONTRACT 候选（多智能体版 01_任务总表：A01/A06/A07/A08/A12/B03/B04/B06/B07/B10/B13/C01/C02/C03/C04/C05/C06/C07/C10/D02/D03/D04）全部重算：
  22/22 映射到新任务（34 行承接，A06/A07/A08 各承接于 F10/F11/F13 等多任务），承接任务的 `owned_paths` 写域与
  `required_locks` 资源锁全部重新登记，**无一缺锁**。逐条裁决见
  `artifacts/tasks/R02/wait-contract-recompute.csv`：合同通过不自动放行，按新计划写域/资源检查重新执行。
- `plan_guard.py` 复验 exit 0：development DAG（53 节点/67 边）与 acceptance union DAG（53 节点/138 边）拓扑有效，
  61 旧项 / 50 P 包全覆盖。

## 状态口径

`dev_state`：NOT_STARTED / IN_PROGRESS / SOFTWARE_DONE。
`acceptance_state`：NOT_RUN / SOFTWARE_ACCEPTED / DEVICE_WAIT / DEVICE_ACCEPTED / BLOCKED。
调度 READY 由控制器按合同/依赖/写域/资源/证据入口计算；WAIT_CONTRACT 候选不得因合同通过跳过写域检查。
旧 Excel（docs/project-plans/*.xlsx）迁移验证完成前只读保留；进度文字不覆盖安全门。

当前进度：R00=SOFTWARE_DONE+SOFTWARE_ACCEPTED（本地审计交付）。下一步：R01 清理、K10/K11/K12 合同差额冻结。
