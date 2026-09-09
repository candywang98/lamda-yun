# T010–T012 progress

Date: 2026-09-06

## T010 / T011
- Same device + platform keeps one BOUND account; 闲鱼 and 小红书 may coexist.
- Rebind unbinds the previous platform account, increments bindingVersion, and fails queued mobile tasks with ACCOUNT_CHANGED.
- Product/Post remain tenant assets. Mobile tasks and publish targets freeze accountId, bindingVersion, and deviceIdAtExecution.
- GET /api/v1/accounts returns historical bindings with `historical: true`.
- GET /api/v1/accounts/{id}/ownership lists frozen tasks/targets for an unbound account.
- SQL: `services/control-api/migrations/versions/003_account_binding_ownership.sql`

## T012
- CommandV1 schema: `contracts/phase1/command-v1.schema.json`
- Python: `cloudctl_api.command_v1.parse_command_v1`
- TypeScript: `@cloudctl/api-contracts` `parseCommandV1`
- Kotlin: `CommandV1Parser`
- Fixtures under `contracts/phase1/fixtures/{valid,invalid}`
- Unauthorized shell/DEX/JS fields are rejected.

## Evidence
- Tests to run: account rebind + command v1 + openapi contract.
- Excel status: 待联调 (no production DB migrate, no Companion CommandV1 claim path on device yet).
