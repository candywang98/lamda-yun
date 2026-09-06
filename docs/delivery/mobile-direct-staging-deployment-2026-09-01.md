# Mobile direct staging deployment — 2026-09-01

## Runtime

- Public base URL: `https://43.133.243.154.sslip.io`
- Workbench: `/cloudctl-mobile/` (inherits the existing GenericAgent Basic Auth)
- Companion API: `/companion/v2/*` (no Basic Auth; enrollment code or binding bearer required)
- Operator mobile API: `/api/v1/mobile/*` (inherits existing Basic Auth and application RBAC)
- Health: `/health/live`
- TLS leaf SHA-256: `4aa79fab99f90aefda2a66b9456ee2839c5e5379716a8e98e49bee15ea2619bc`

The deployment is isolated from `/home/ubuntu/GenericAgent` and from the Edge Hub.
The API listens on `127.0.0.1:8000`; Nginx is the only public HTTPS ingress.

## Persistence and services

- API systemd unit: `cloudctl-mobile-api.service`
- PostgreSQL container: `cloudctl-mobile-postgres`
- PostgreSQL bind: `127.0.0.1:55432`
- PostgreSQL volume: `cloudctl-mobile-postgres`
- Release: `/home/ubuntu/cloudctl-mobile/releases/20260901-1800`
- Workbench files: `/var/www/cloudctl-mobile-20260901-1815`
- Studio files: `/var/www/cloudctl-studio-20260901-1810`
- Nginx backup: `/etc/nginx/sites-available/ga-web.before-cloudctl-mobile-20260901`

Verified on 2026-09-01:

- API, Nginx, PostgreSQL and the pre-existing Edge Hub were active.
- Public health returned `{"status":"ok"}`.
- An unauthenticated task claim returned HTTP 401 from Control API.
- Alembic upgraded through `20260901_0007`.
- Operation catalog exposes strong `parameterSchema` contracts for the 16 mapped
  PDF pages.

## Acceptance device

- Direct device ID: `4aabc387-6e4b-4b59-a525-b1c119ec7f5b`
- Logical name: `oneplus-9r-b0644fb5`
- `edgeId`: `null`

The one-time enrollment code must be created only when the phone is ready,
because it expires in at most one hour.

## Security status

This is an acceptance/staging deployment. Operator authentication currently uses
the development identity-header mode behind the existing Nginx Basic Auth. It is
not a production OIDC deployment. Companion authentication, one-time enrollment,
TLS pinning, binding bearer tokens, task leases and structured action validation
are active.

## Deterministic no-USB target

The acceptance target package is `com.company.cloudctl.testtarget`. Approved
locators are:

- `status_text`
- `input_field`
- `action_button`
- `result_panel`

The target contains no network, shell, ADB, dynamic-code or privileged capability.
