# R02 evidence summary

- Task: 单一任务源与调度校验落地
- Audited: 2026-09-20 (Asia/Shanghai)
- Software status: `SOFTWARE_DONE`
- Acceptance status: `SOFTWARE_ACCEPTED`
- Device acceptance: not applicable; software verification only

## What already existed (activated 2026-09-16 @bf6529b, merged)

- Both legacy workbooks exported sheet-by-sheet with SHA256 (`lamda_yun_delivery_20260916/evidence/local-active-all-sheets.json`, `local-acceptance-all-sheets.json`).
- 61 legacy scheduling IDs and 50 packages (P00–P49) fully mapped.
- Old P14 queue marked HISTORICAL in `docs/phase1/multi-agent-work-items.json`.
- `scripts/plan_guard.py` with dual-DAG topological validation.

## Delta closed by this slice (2026-09-20)

- 22 WAIT_CONTRACT candidates (multi-agent workbook `01_任务总表`) recomputed: 22/22 mapped (34 carrying rows; several old IDs carried by multiple new tasks), every carrying task re-registers `owned_paths` write-domain and `required_locks`; zero missing locks; contract approval does not auto-release. Per-row rulings: `artifacts/tasks/R02/wait-contract-recompute.csv`.
- `tasks.json` `authority` flipped `CANDIDATE_NOT_ACTIVATED` → `ACTIVATED` with `activated_at` backfilled to the 2026-09-16 activation.
- R02 task state recorded (`SOFTWARE_DONE` / `SOFTWARE_ACCEPTED`) with consolidated evidence.
- `plan_guard.py` rerun after edits: exit 0, valid, 61 legacy / 50 packages, development DAG 53 nodes / 67 edges, acceptance union DAG 53 nodes / 138 edges, no missing IDs, no self-references (`artifacts/tasks/R02/plan-guard-rerun.json`).
- README R02 补记 section added (activation addendum + recompute ruling).

## Honest boundaries

- The live progress workbook remains the execution log until R01's migration verification; this slice did not restructure it (read-only preservation rule). Roll-up formula ranges extended to cover recent rows is bookkeeping hygiene, recorded in the execution log.
- plan_guard is static graph/declared-path checking only — not proof of deployed behavior.
