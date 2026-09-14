# Control API production deployment

## OIDC verification

The Control API verifies every bearer access token inside the application. Reverse proxies and ASGI middleware
must not inject trusted identity claims; `cloudctl.oidc_claims` and `X-Tenant-Id`/`X-User-Id`/`X-Roles` are
ignored when the development bypass is disabled.

Set the following production values:

```bash
export CLOUDCTL_ENV=production
export CLOUDCTL_REPOSITORY_MODE=postgresql
export CLOUDCTL_DATABASE_URL='postgresql+asyncpg://cloudctl:change-me@postgres/cloudctl'
export CLOUDCTL_DEV_AUTH_BYPASS=false
export CLOUDCTL_OIDC_ISSUER='https://identity.example.com/realms/cloudctl'
export CLOUDCTL_OIDC_AUDIENCE='cloudctl-api'
export CLOUDCTL_OIDC_JWKS_URL='https://identity.example.com/realms/cloudctl/protocol/openid-connect/certs'
export CLOUDCTL_OIDC_ALLOWED_ALGORITHMS='["RS256"]'
```

## WeChat publisher secret encryption

Production requires `CLOUDCTL_WECHAT_SECRET_ENCRYPTION_KEY`, a valid Fernet key
(32-byte url-safe base64; generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
The Control API refuses to start in production without it, and any configured
key is validated at startup. Without the key only development/test deployments
degrade to an obfuscated at-rest form (`dev-b64:` prefix); that is never allowed
in production. Rotating the key requires re-encrypting existing
`wechat_account.secret_ciphertext` rows offline; there is no multi-version key
support yet.

Exactly one of `CLOUDCTL_OIDC_JWKS_URL`, `CLOUDCTL_OIDC_PUBLIC_KEY_PEM`, or
`CLOUDCTL_OIDC_PUBLIC_KEY_PATH` may be configured. Prefer JWKS for managed rotation. A production JWKS URL and
issuer must use HTTPS; redirects are not followed. Static keys are limited to 64 KiB. The algorithm allowlist
contains only `RS256` and/or `ES256`; the token header cannot expand it.

Required claims are `sub`, `tenant_id`, `user_id`, `roles`, `iss`, `aud`, and `exp`. `nbf`, when present, is
verified. `tenant_id` and `user_id` must be UUIDs, `roles` must contain CloudCtl role names, and `mfa` is the
boolean consumed by separation-of-duties checks. Signature, expiry, not-before, issuer, or audience failure is
returned as authentication failure without exposing cryptographic details.

JWKS responses are capped at 1 MiB and 100 keys. Keys are cached for
`CLOUDCTL_OIDC_JWKS_CACHE_SECONDS` (default 300); an unknown `kid` triggers one forced refresh to support key
rotation. Keep the old signing key published until all tokens signed by it have expired.

## Database migration

Take a database backup, deploy the new application artifact, and run the migration as a one-off job before
starting any new Control API instances:

```bash
. .venv/bin/activate
alembic -c services/control-api/alembic.ini current
alembic -c services/control-api/alembic.ini upgrade head
alembic -c services/control-api/alembic.ini current
alembic -c services/control-api/alembic.ini check
```

Revision `20260831_0001` creates the original control-plane schema. Revision `20260831_0002` backfills the new
`operation_task.context` value for existing rows, adds feature and approval fields, and creates
`debug_session`/`debug_evidence` with indexes and uniqueness constraints. Application startup never calls
`create_all` in production or PostgreSQL mode.

For a planned rollback, stop writers first and preserve any Debug Session evidence or approval metadata needed
for audit. Downgrading `20260831_0002` removes those new tables and columns:

```bash
alembic -c services/control-api/alembic.ini downgrade 20260831_0001
```

Restore the database backup rather than downgrading if the new Debug Session or approval records must remain
queryable. After migration or rollback, verify `/health/live`, `/health/ready`, a valid bearer-token call to
`/api/v1/session`, tenant isolation, and the Operations/Debug Session integration tests.
