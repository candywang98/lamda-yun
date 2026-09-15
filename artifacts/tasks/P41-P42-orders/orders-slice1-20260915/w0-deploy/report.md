# W0 部署报告：首尔控制 API 升级 orders-7adc827 — 2026-09-15

执行：W0 总控，持 DEPLOY:seoul 锁。部署 SHA `7adc827`（集成 HEAD：W1 后端 + W3 Web 修正 + 总控提交），时点在 W2 合并之前（后端能力不依赖 W2）。

## 变更内容

1. **新 release**：`~/cloudctl-mobile/releases/orders-7adc827/`（git archive 集成 HEAD，14MB）+ `.venv`（Python 3.12.3，`pip install -e .[dev]`）
2. **DB 迁移**：alembic `20260915_0020 → 20260915_0021`（xianyu_order 表，PostgreSQL 15x docker `cloudctl-mobile-postgres` @127.0.0.1:55432）。迁移前备份：`~/cloudctl-mobile/shared/backups/pre-0021-20260915-211748.dump`（pg_dump -Fc，296KB）
3. **服务切换**：新 drop-in `99-zz-orders.conf`（词法最后生效，含 WorkingDirectory+ExecStart+UnsetEnvironment=PYTHONPATH）；`99-xy-maint.conf` 改名 `.bak-20260915` 留存。`systemctl daemon-reload && restart cloudctl-mobile-api`
4. 回滚路径：改回 `.bak` 文件名 + daemon-reload + restart；迁移可 alembic downgrade（0021 仅建表，旧代码不受影响）

## 过程问题（记录）

- drop-in 词法序陷阱：`99-orders.conf` 排在 `99-p09-*.conf` 之前不生效，两次重启仍跑旧代码——改用 `99-zz-` 前缀解决。历史 drop-in（90-p14/99-p09-hardening/99-p09-ledger/99-xy-maint.bak）全部保留仅被遮蔽。
- shell `source` 加载 env 文件会截断含空格 JSON 值（systemd EnvironmentFile 按整行+去引号解析）——预检脚本 `/tmp/run_api_port.py` 按 systemd 语义加载。

## 验证（全部实测）

| 检查 | 结果 |
|---|---|
| 8901 预检（切换前） | health 200；openapi 151 paths 含全部 5 个订单端点；batch 无认证 401 |
| 迁移后 8901 GET /api/v1/orders | 200 `{"items":[],"total":0}` |
| 生产 localhost:8000 | health 200；orders 200 空集；batch 401 |
| 公网 https://43.133.243.154.sslip.io | health 200；orders 200；platform-tasks 200×3 |
| 旧功能 | platform-tasks 200；maintenance 端点在 151 paths 中（151=旧 146+5 新增） |

注：公网偶发 curl 000 为本机代理连接复用毛刺，重试即 200，非服务问题。

## 手机路径

Companion 基址 `https://43.133.243.154.sslip.io`（nginx 443 → 127.0.0.1:8000）。当前手机仍跑旧 APK（无 readOrders）；等 W2 合并后装机，`POST /companion/v2/orders/batch` 与 `POST /api/v1/xianyu/orders:collect` 已就绪。

## 未决项

- 采集入口在 Web 仍禁用（定位器 verified=false，待装机烟测后总控翻转）
- `/api/v1/xianyu/orders:collect` 未冒烟真实调用（避免给旧 APK 派发无法执行的 readOrders 任务）
