# 历史资料归档（2026-09-16，R01）

按交付包 `lamda_yun_delivery_20260916/04_仓库清理清单.md` 由控制器逐文件 `git mv` 归档；不删除任何内容，均可 `git revert` 回退。

| 文件 | SHA-256 |
|---|---|
| `docs/project-plans/LAMDA云控系统_V1重审开发计划_20260905.xlsx` | 79c0dd5860c720d6… |
| `docs/project-plans/lamda_yun_一期审阅与实施_需求确认版.xlsx` | ea44178e0dac7867… |
| `docs/project-plans/lamda_yun_一期智能体实施手册_需求确认版.md` | f409e5203430dfe3… |
| `docs/project-plans/计划优化问题清单.md` | ac029585cd1a90f8… |
| `docs/project-plans/项目交接说明.md` | efbeb0fab031bc09… |
| `docs/delivery/task-status.md` | 5c052e25c4edea81… |
| `docs/compatibility/yuyou-assistant-qa_旧稿pre勘误_20260916.md` | 3ed6949baa58a831… |

## 登记

- **CL01** Kotlin 错误缓存已隔离到仓库外 `../../.cleanup-quarantine-20260916/cloudctl-kotlin-cache/`（含 restore.json，可恢复），并从工作区移除。
- **CL07/CL08** 两份 Excel 保留在 `docs/project-plans/` 原位作冻结历史基线（KEEP_UNTIL_ACTIVATED→已激活，转冻结，不移动）。
- **CL10** `docs/phase1/multi-agent-work-items.json` 未物理移动：R02 已就地写入 `historical:true + supersededBy`，清理清单期望 blob 因此不再匹配；就地保留即满足去权威化。
- **CL11** `docs/compatibility/yuyou-assistant-qa.md` 已替换为用户最新专家评审稿（含第二轮追问+全量源码复核勘误，2026-09-16），旧稿存本目录。
- **CL12** task-status.md 为 2026-08-31 快照；`scripts/generate_delivery_status.py` 仍可重新生成该路径。
- **CL13** AndroidManifest 重复 `POST_NOTIFICATIONS` 已去重（仅去重，未触碰无障碍/IME 授权边界）。
- **CL14** `.gitignore` 新增 `.kotlin/`、`mobile/companion/.gradle/`。
- 迁移、锁文件、Gradle wrapper、未结案台账、签名密钥、真实证据全部保留，未删除。
