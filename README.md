# CloudCtl

当前进度计划（表内更新至 2026-09-09）：[一期智能体执行计划与交接快照](docs/project-plans/README.md)。
当前为 P00–P49 共 50 个功能包，P14 版本生命周期仍在推进。模块通过不代表整包真实验收；[V1 审核与实施计划](docs/v1/README.md)、下方及 `docs/delivery/` 中较早交付说明保留作历史背景。

CloudCtl is the LAMDA cloud-control system implemented from the supplied architecture package. The monorepo
contains 16 logical projects: 9 deployable applications/services, 6 shared packages, and the infrastructure
and operations project.

The system is intended only for devices, accounts, applications, and content that the operator owns or is
explicitly authorized to control.

## Repository map

| Area | Projects |
| --- | --- |
| Browser applications | `apps/web`, `apps/studio` |
| Cloud services | `services/control-api`, `services/temporal-worker`, `services/edge-hub`, `services/outbox-dispatcher` |
| Edge runtime | `edge/gateway` |
| Android applications | `mobile/companion`, `mobile/dpc` |
| Shared packages | `packages/domain`, `packages/edge-protocol`, `packages/lamda-driver`, `packages/automation-sdk`, `packages/observability`, `packages/api-contracts` |
| Deployment and operations | `infra`, `scripts`, `.github/workflows` |

## Local mock profile

Prerequisites are Python 3.12+, Node 22+, pnpm 10.15+, and Docker Compose. Android builds additionally need
JDK 17/21 and Android SDK 35.

```bash
cp .env.example .env
set -a && . ./.env && set +a
docker compose -f infra/compose/docker-compose.yml up -d
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pnpm install --frozen-lockfile
alembic -c services/control-api/alembic.ini upgrade head
python scripts/export_openapi.py
```

Start the development processes in separate terminals:

```bash
. .venv/bin/activate
python -m cloudctl_api
```

```bash
. .venv/bin/activate
python -m cloudctl_worker.main
```

```bash
. .venv/bin/activate
python -m cloudctl_outbox.main
```

```bash
pnpm dev
```

Development URLs:

- Web console: `http://127.0.0.1:5173`
- Studio: `http://127.0.0.1:5174`
- Control API: `http://127.0.0.1:18000` (not 8000; that port is commonly taken by Spider_XHS)
- OpenAPI UI: `http://127.0.0.1:18000/docs`
- Temporal UI: `http://127.0.0.1:8088`
- MinIO console: `http://127.0.0.1:9001`
- Grafana: `http://127.0.0.1:3001`

The browser applications intentionally use deterministic mock data by default. This exercises the complete UI
without granting a browser direct device access.

## Production execution paths (ADR 0003, ADR 0004)

**V1 production automation** uses two execution methods:

1. **Companion mobile-local** (闲鱼, 小红书, 抖音): enrolled Android APK receives tasks via HTTPS, executes via AccessibilityService, uploads evidence independently. No USB, ADB, or local workstation required after enrollment. See ADR 0003 for acceptance criteria.

2. **API publisher** (微信公众号): server-side Control API calls official platform APIs directly. No device required.

Both paths share the same business domain (`Product`, `ContentRevision`, `PublishTarget`) and commit ledger.

**Edge Gateway + LAMDA** is for **Studio development and debugging only**: live layout inspection, evidence preview, and diagnostic workflows. It is not required for production task delivery and must not conflict with Companion task leases. Edge requires separately provisioned mTLS identities and an authorized LAMDA device profile.

The Edge Gateway runs LAMDA `10.8` in a dedicated Python `3.12` sidecar so its protobuf `6.x`
dependency cannot alter the control-plane protobuf `7.x` environment. Set the absolute
`CLOUDCTL_LAMDA_SIDECAR_PYTHON` path before Edge startup. The local handshake validates the Python,
LAMDA, and IPC protocol versions and opens no network listener. See
`docs/runbooks/lamda-sidecar.md` for preparation and failure behavior.

## Control API authentication and migrations

`CLOUDCTL_DEV_AUTH_BYPASS` is disabled by default and can only be enabled explicitly in `development` or
`test`. With the bypass disabled, the API verifies the bearer JWT itself and never accepts identity claims from
ASGI scope or proxy-populated identity headers. Configure exactly one verification source: an HTTPS JWKS URL,
a static public-key PEM, or a path to a public-key PEM. Production accepts only `RS256` and/or `ES256`, verifies
signature, expiry, not-before, issuer, and audience, and rejects missing or invalid tokens.

Production schema changes are applied before process startup:

```bash
. .venv/bin/activate
export CLOUDCTL_DATABASE_URL='postgresql+asyncpg://cloudctl:change-me@db.example/cloudctl'
alembic -c services/control-api/alembic.ini upgrade head
alembic -c services/control-api/alembic.ini current
python -m cloudctl_api
```

`Base.metadata.create_all()` remains available only for fresh in-memory/local SQLite development and test
databases. Production and PostgreSQL startup never mutate the schema implicitly. See
`docs/runbooks/control-api-production.md` for the claim contract, key rotation, deployment, and rollback steps.

## Verification

```bash
. .venv/bin/activate
ruff format --check .
ruff check .
pyright
mypy
pytest -q
scripts/check-security-boundaries.sh
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm e2e
```

Android host-side checks:

```bash
cd mobile/companion && ./gradlew test lint
cd ../dpc && ./gradlew test lint
```

`connectedCheck` and every task requiring real LAMDA, APK installation, rollback, endurance, chaos, or production
rollout evidence remain `blocked_hardware` until an authorized device lab is available. Mock tests never promote
those gates to done. Detailed status is in `docs/delivery/task-status.md`.

## Security invariants

- Port 65000 is never exposed by the control plane or browser.
- LAMDA imports are restricted to `packages/lamda-driver`.
- LAMDA's incompatible Python dependencies are isolated in a version-gated local sidecar.
- Device writes require a database fencing lease, Edge token validation, a single Runner, and a LAMDA API lock.
- Publish commit is attempted once after a durable commit intent; uncertain outcomes are reconciled, never
  resubmitted automatically.
- Production capabilities exclude arbitrary shell, Frida, MITM, CAPTCHA handling, anti-detection, fake traffic,
  and unauthorized messaging or bulk actions.
