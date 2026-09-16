# Runbook：fleet 部署身份、构建版本与备份恢复基线（D10）

适用范围：fleet-first 计划基础设施线。本文钉死端口/路径事实、首尔现状（R00 + D10 只读取证）、staging 流程、生产变更窗口、回滚与 legal-hold 策略。

- 建立日期：2026-09-16（D10）
- 取证方式：全部为只读操作（curl 公网、只读 ssh `cat`/`systemctl cat`/`systemctl show`/`journalctl`/`docker ps`），未对首尔服务器做任何变更
- 工具脚本：`scripts/fleet-preflight.sh`（backup / restore-verify / probe-auth / version）
- staging 编排：`infra/compose/staging/`

---

## 1. 端口与路径事实（钉死，防止误连）

| 位置 | 地址 | 说明 |
|---|---|---|
| 本地 dev API | `http://127.0.0.1:18000` | `scripts/run-api-dev.sh`；**8000 被本机 Spider_XHS 占用，根 README 已声明，不要连 8000** |
| staging compose API | `http://127.0.0.1:18001` → 容器 8000 | `infra/compose/staging/docker-compose.yml` |
| staging compose PG | `127.0.0.1:15432` → 容器 5432 | 避开本机 Homebrew PostgreSQL（5432，本机实测在跑 PG 16.15） |
| 首尔 API（本机回环） | `127.0.0.1:8000` | systemd `cloudctl-mobile-api.service`，uvicorn 2 workers |
| 首尔 PG | `127.0.0.1:55432` | docker 容器 `cloudctl-mobile-postgres`（postgres:18-alpine），库 `cloudctl` |
| 首尔公网入口 | `https://43.133.243.154.sslip.io` | nginx 443 唯一公网 HTTPS 入口；80 仅 ACME + 301 |
| 首尔对象存储 | `/home/ubuntu/cloudctl-mobile/shared/media` | filesystem 模式（staging 形态，生产应切 S3） |
| edge-hub（首尔） | `/opt/cloudctl-edge-hub`，release `20260901-rpc10` | 与 mobile-api 隔离部署（R00） |

注意：`infra/compose/docker-compose.yml`（observability 全栈）把 postgres 映射到 `127.0.0.1:5432`，与本机 Homebrew PostgreSQL 冲突；起那套栈前先停本机 PG 或改端口。staging 编排已刻意避开（15432）。

## 2. 首尔现状事实（R00 + D10 只读取证，2026-09-16/17）

### 2.1 运行版本

- systemd `cloudctl-mobile-api.service`：`ActiveState=active`，MainPID 565373，启动于 **2026-09-16 12:50:13 CST**。
- 实际 ExecStart：`/home/ubuntu/cloudctl-mobile/releases/a11-9c53cc7/.venv/bin/python -m uvicorn cloudctl_api.app:app --host 127.0.0.1 --port 8000 --workers 2 --proxy-headers --forwarded-allow-ips=127.0.0.1`。
- drop-in 链（`systemctl cat` 只读）：base `20260901-1800` → `90-p14.conf`（p14-bb81051）→ `99-p09-hardening.conf`（p09-ef9eb2b）→ `99-p09-ledger.conf`（p09-ledger-ce823ad）→ …最终生效 a11-9c53cc7。**注意：该链是"后写的 drop-in 覆盖前写的"，排障时必须以 `systemctl show -p ExecStart` 为准，不要按文件名猜。**
- 环境文件 `/home/ubuntu/cloudctl-mobile/shared/control-api.env`（键名+已核实值）：
  - `CLOUDCTL_ENV=development`
  - `CLOUDCTL_DEV_AUTH_BYPASS=true`
  - `CLOUDCTL_REPOSITORY_MODE=postgresql`，`CLOUDCTL_DATABASE_URL=postgresql+asyncpg://…@127.0.0.1:55432/cloudctl`
  - `CLOUDCTL_OBJECT_STORE_DIR=/home/ubuntu/cloudctl-mobile/shared/media`（filesystem 对象存储）
  - 另有 `CLOUDCTL_PUBLIC_BASE_URL` / `CLOUDCTL_CORS_ALLOWED_ORIGINS` / `CLOUDCTL_AUTOMATION_SIGNING_PUBLIC_KEYS`
- 仓库 HEAD `57f27a0` 领先服务器 3+ 个功能合并（R00 结论）。

### 2.2 nginx 暴露面（`/etc/nginx/sites-enabled/ga-web` + `/etc/nginx/snippets/cloudctl-mobile-api.conf`，只读拉取）

- 443 default server（`43.133.243.154.sslip.io`）**server 级**有 `auth_basic "GenericAgent"`（`/etc/nginx/.ga_htpasswd`）。
- 但 snippet 对以下路径 **`auth_basic off`**：`/companion/`、`/api/v1/mobile/`、`/api/v1/`、`/health/`。
- 静态：`/cloudctl-mobile/`（alias `/var/www/cloudctl-mobile-current/`）、`/cloudctl-studio/`（alias `/var/www/cloudctl-studio-current/`）。
- **公网健康探测用 `/health/live` 和 `/health/ready`**（nginx location 是 `/health/` 带斜杠）。`/healthz` 不匹配该 location，落到 Basic Auth 保护的 GA 位置，公网实测 HTTP 401——外部探测不要用 `/healthz`（2026-09-16 实测钉死）。
- 安全响应头（nginx 层）：HSTS `max-age=31536000; includeSubDomains`、`X-Frame-Options: DENY`、`X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer`、`server_tokens off`。

### 2.3 实测安全形态（D10 只读探测，2026-09-17 00:0x CST）

对公网 `https://43.133.243.154.sslip.io/api/v1/session`：

| 探测 | 结果 |
|---|---|
| 匿名（无任何头） | HTTP 401（拒绝，正常） |
| 伪造 Bearer（`Authorization: Bearer eyJ…forged.sig`） | HTTP 401（拒绝，正常） |
| 伪造开发身份头（合法 UUID 租户 + `X-Roles: security_admin`） | **HTTP 200，返回任意伪造租户/角色的 session（越权成立）** |
| 伪造身份头 + 非法角色名（`admin,superuser`） | HTTP 403（角色枚举校验生效） |

**结论（红线事实）**：operator 命名空间 `/api/v1/` 在公网仅靠可伪造的开发身份头保护——2026-09-01 交付文档所写"`/api/v1/mobile/*` 继承 Basic Auth"已与现状不符（配置漂移：snippet 对整个 `/api/v1/` 关掉了 Basic Auth）。**任何报告里的 dev 头都不构成生产权限；生产切换前必须按第 3 节清单整改并通过 `fleet-preflight.sh probe-auth --mode strict`。**

### 2.4 TLS

- 公网 leaf：SHA-256 `FE:17:8C:22:BA:43:27:C0:A7:1C:DD:0C:75:61:65:4F:B7:6F:F6:7C:02:AA:54:61:F0:76:BF:2F:C6:06:22:D1`，CN=`43.133.243.154.sslip.io`，有效期 **2026-09-11 → 2026-12-10**（Let's Encrypt，约 90 天轮换；09-01 文档记录的 `4aa79fab…` 已轮换作废）。
- 证书路径 `/etc/letsencrypt/live/43.133.243.154.sslip.io/`，ACME http-01 走 80 端口 `/.well-known/acme-challenge/`（80 端口不能关）。**每次部署演练前核对 `notAfter`，剩 <30 天先走续期。**

### 2.5 日志脱敏现状

- `journalctl -u cloudctl-mobile-api` 近 200 行样本 `grep -icE "authorization|bearer|x-roles|password|secret"` = 0 次命中；uvicorn 访问日志仅含 IP/路径/状态码。
- 应用侧结构化日志经 `packages/observability` 的 `redact/redact_text`（`configure_logging`）输出，token/密钥类字段在应用层脱敏。基线成立，但生产切换时应在窗口内复查一次大样本。

## 3. 生产安全切换门（dev 形态 → 生产形态）

按顺序完成，全部通过才允许视为"生产权限基线"：

1. `CLOUDCTL_ENV=production`（settings 校验器随即强制：OIDC 恰一个验证源且 https、repository_mode=postgresql、object_store=s3+https、wechat Fernet key、禁 CORS 通配）。
2. 移除 `CLOUDCTL_DEV_AUTH_BYPASS`（校验器在 production 下直接拒绝 true）。
3. nginx 恢复：`/api/v1/`（至少 operator 面）保留/恢复 `auth_basic`，或 OIDC 全面接管后保持 401 兜底；`/companion/` 保持注册码/binding bearer 自鉴权。
4. 验证：`scripts/fleet-preflight.sh probe-auth https://43.133.243.154.sslip.io --mode strict --require-tls` 必须 PASS（当前形态下该命令会 FAIL，这是预期的纠偏信号）。
5. 复查 journal 脱敏（2.5 节方法）。

## 4. 版本可查询基线（API / APK / Recipe）

现状（2026-09-16）：

- API：`/health/live`、`/health/ready`、`/healthz` 只返回 status/repositoryMode，**不含构建号**。服务真实版本当前只能靠服务器上 release 目录名（`a11-9c53cc7`）定位。
- Recipe：`GET /companion/v2/recipes/active`（首尔实测 200，设备侧在用）。
- APK：设备注册表 versionCode/versionName（R00：设备 b0644fb5 = versionCode 1 / 0.1.0，构建哈希 `2391f380…`）。

D10 落地的接线（不改服务代码，服务代码不归 D10）：

- `infra/compose/staging/` 构建时注入 `BUILD_SHA`（build-arg + 容器环境变量 + OCI label `org.opencontainers.image.revision`），staging 编排默认 `BUILD_SHA=$(git rev-parse --short HEAD)`。
- **服务侧待办（归属 control-api 维护者，非 D10）**：`/health/ready` 响应中加入 `buildSha`（读 `BUILD_SHA` 环境变量，缺省 `"unknown"`）。落地后 `fleet-preflight.sh version <url> --require-build` 即可机器校验；首尔 systemd 部署则在 unit 的 `Environment=` 或 env 文件补 `BUILD_SHA=<release>`。
- 查询：`scripts/fleet-preflight.sh version http://127.0.0.1:18001 --compose-dir infra/compose/staging`。

## 5. 备份与还原基线（部署前强制）

### 5.1 backup

```
scripts/fleet-preflight.sh backup <DEST_DIR> [--objects-dir <对象根目录>]
```

- 连接走标准 libpq 环境变量（`PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD`；缺省 `127.0.0.1:5432/cloudctl/cloudctl`）。
- 产出：`postgres-<UTC时间戳>.dump`（custom 格式）+ `.sha256` 校验、`objects-<时间戳>.tsv`（对象清单：sha256/大小/legal-hold 标记/相对路径）、`manifest-<时间戳>.json`（时间、gitSha、库、对象数、legal-hold 数）。
- `legal-hold/` 前缀下的对象在清单中单独标记（第 9 节）。
- S3 桶清单：脚本不直接拉 S3（依赖约束），用桶侧 inventory 导出或 `mc mirror --dry-run` 生成清单后并入 DEST_DIR，manifest 中记 `objectsDir`。

### 5.2 restore-verify（隔离库还原验证）

```
scripts/fleet-preflight.sh restore-verify <DUMP> [--keep]
```

- 校验 dump 的 sha256 旁车文件（存在才校验）。
- `createdb cloudctl_pverify_<时间戳>` 隔离临时库 → `pg_restore --no-owner` → 与源库逐表比对：表集合一致、每表 `count(*)` 一致、每表全行摘要一致（`md5(string_agg(md5(row::text) ORDER BY …))`，顺序无关）。覆盖任务/意图/对象摘要相关业务表（`mobile_task`、`commit_intent`、`media_asset`、`fleet_device_session` 等，存在即在报告中逐表点名）+ `alembic_version` 迁移位。
- 结束自动 `dropdb` 临时库；`--keep` 保留排查。
- 退出码 0 = 可信备份；1 = 任何不一致。

### 5.3 首尔实操（仅授权窗口内执行，D10 未在生产跑过）

- **pg_dump 版本对齐**：服务器是 PostgreSQL 18，本机 Homebrew 是 16——pg_dump 16 不能 dump 18，必须用容器内的 pg_dump：
  ```
  ssh seoul 'docker exec cloudctl-mobile-postgres pg_dump -U cloudctl -d cloudctl --format=custom' > postgres-<ts>.dump
  ```
  服务器端留副本则重定向到 `/home/ubuntu/cloudctl-mobile/backups/`（写入操作，需窗口授权）。对象清单：`--objects-dir /home/ubuntu/cloudctl-mobile/shared/media`。
- **禁止**在本机直接 `pg_dump -h 43.133.243.154`：5432/55432 均不对公网开放（安全组只开 22/80/443），走 ssh 是唯一正路。

## 6. staging 流程（本地 compose；staging 允许自动重启）

```
cd infra/compose/staging
BUILD_SHA=$(git rev-parse --short HEAD) docker compose build
BUILD_SHA=$(git rev-parse --short HEAD) docker compose up -d     # migrate 服务先跑 alembic upgrade head
```

验证顺序（D10 验收路径）：

```
scripts/fleet-preflight.sh version http://127.0.0.1:18001 --compose-dir infra/compose/staging
scripts/fleet-preflight.sh probe-auth http://127.0.0.1:18001 --mode dev-bypass   # staging 形态
PGPORT=15432 scripts/fleet-preflight.sh backup /tmp/stg-backup --objects-dir <media目录>
PGPORT=15432 scripts/fleet-preflight.sh restore-verify /tmp/stg-backup/postgres-*.dump
```

- staging 形态即 `CLOUDCTL_DEV_AUTH_BYPASS=true`（无 OIDC 依赖），probe 必须用 `--mode dev-bypass` 且**绝不暴露公网**（compose 只绑 127.0.0.1）。
- staging 可随意 `docker compose restart/down`；数据卷 `staging-postgres-data` 保留以便回归。

## 7. 生产变更窗口流程（仅授权窗口；D10 不执行）

1. **授权**：用户明确批准窗口（时间窗 + 变更内容 + 回滚标准）；未授权不碰生产。
2. **窗口前置**（全部 PASS 才动手）：
   - `fleet-preflight.sh backup`（5.3 节首尔路径）+ `restore-verify` PASS；
   - 确认磁盘空间（新 release venv + 备份）；
   - 当前 ExecStart/release 记录进变更记录（`systemctl show -p ExecStart`）。
3. **部署**：新 release 目录（`/home/ubuntu/cloudctl-mobile/releases/<git-sha>`）+ 独立 venv + env 文件；用**新增 drop-in（序号最大）**覆盖 WorkingDirectory/ExecStart；`systemctl daemon-reload && systemctl restart cloudctl-mobile-api`。
4. **验证**：`/health/live` 200 → `probe-auth`（按当时形态选 mode）→ 业务冒烟（companion recipes/任务链路）→ journal 无异常刷屏。
5. **保留旧镜像/release**：至少保留**最近 2 个**旧 release 目录与当前运行目录，**永不删除正在运行的那个**；清理需在下一个窗口单独授权。
6. **迁移兼容**：只上"兼容迁移"（expand-contract：先加列/表 → 双写回填 → 下个窗口才收缩）；`alembic upgrade head` 在切换 ExecStart 前对新库执行；`fleet_device_session`（0023）等新表均为纯新增，向后兼容。

## 8. 回滚

- **服务回滚**（首选，分钟级）：删除/改名本次新增 drop-in（或新写一个指回旧 release 的 drop-in）→ `daemon-reload` → `restart`。旧 release 目录和 venv 未删即可用。
- **数据库回滚**：兼容迁移下**不需要回数据库**（旧代码忽略新表/新列）。仅当迁移含收缩性变更且作者标注 downgrade 已验证时，才允许 `alembic downgrade -1`，且必须在窗口内、备份 restore-verify 通过之后。
- **对象存储**：任何回滚都不删对象；误删靠备份清单 + legal-hold 副本恢复。
- 回滚判据（写进变更记录）：健康检查失败、5xx 率、核心链路（任务下发/意图提交）失败即回滚，不在线上调试。

## 9. Legal-hold（UNKNOWN 证据目录策略）

背景：删除自动化议题中 UNKNOWN/KEEP_WAITING 证据有独立挂起通道（scope-decisions.md 登记），未经授权不重试删除。

- 对象根目录（首尔 `/home/ubuntu/cloudctl-mobile/shared/media`，staging 卷 `/var/lib/cloudctl/media`）下设 **`legal-hold/`** 前缀：判定为 UNKNOWN/存疑的证据对象，在**任何**部署/清理/迁移动作前复制/移动到该前缀。
- legal-hold 对象：内容寻址（sha256 文件名或在清单中记录 sha256）；**排除于一切自动清理/保留期策略**；`fleet-preflight.sh backup --objects-dir` 会在清单中对 `legal-hold/` 前缀打 `legal_hold=1` 标记并单独计数。
- 从 legal-hold 移出或删除**只能由用户显式授权**（删除门），执行后在本 runbook 追加执行记录（日期、授权人、对象清单哈希）。
- 与删除议题的分工：判定"UNKNOWN → legal-hold / KEEP_WAITING → 保留 / 确认废弃 → 走删除门"的裁决流程归删除自动化议题；本策略只保证一旦进入 legal-hold，基础设施侧不会再丢证据。

## 10. 已知缺口与归属

| 缺口 | 归属 |
|---|---|
| `/health/ready` 不返回 buildSha（BUILD_SHA 已注入环境，服务未读） | control-api 服务侧任务（非 D10） |
| 首尔 operator 面公网可伪造身份头越权（2.3 节） | 生产整改窗口（第 3 节清单），需用户授权 |
| 首尔无 OIDC（dev bypass 形态） | 生产切换前置项 |
| 仓库根缺 `.dockerignore`（构建上下文可能带入无关文件） | 仓库根不在 D10 owned paths，未动；建议后续补 |
| 对象存储仍是 filesystem（生产要求 S3） | 生产切换前置项（settings 校验器会强制） |
