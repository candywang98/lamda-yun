# PDF feature-alignment delivery progress — 2026-09-01

## Acceptance rule

A feature is counted as implemented only when the route, dedicated interaction,
validated API contract, persisted state, error handling and automated test all
exist. A route or visual shell alone is not counted.

## Verified completed slices

### Mobile direct automation

- Public workbench creates one-time enrollment codes and structured tasks.
- Companion enrolls directly with Control API v2 and persists a stable app
  instance, binding token and binding ID.
- Foreground synchronization, SQLite inbox/journal/outbox, lease heartbeat,
  ordered events and terminal result upload are implemented.
- Accessibility executor accepts only the seven allowlisted action families.
- Local task state and the latest 50 execution log records are persisted and
  visible in the Companion UI.
- A deterministic, non-networked acceptance target APK exists for no-USB tests.
- A mobile-direct device can exist with `edgeId=null`.

### Operations catalog

- All 134 PDF entries still have a unique route and source metadata.
- The 16 entries mapped to eight backend operation keys now submit their real
  page fields in `parameters.pageParameters`.
- Control API exposes machine-readable parameter schemas for all 16 mapped
  entries, validates core and page parameters, rejects extra fields and persists
  normalized parameters in the idempotency hash.
- API failures fail closed. Mock execution is development-only and requires an
  explicit flag.

This is **16/134 backend-mapped entries**, not 134/134 feature completion.

### Device operations

- Device list, device detail and dashboard device section read Control API.
- Direct Companion devices are displayed as phone-direct rather than as a fake
  Edge assignment.
- Missing telemetry is displayed as not reported; no health numbers are invented.
- Enter-maintenance calls the real version-checked API.

### Studio debugging tool

- Relay layout messages replace the live UI tree.
- Fixed screenshot hashes, object references and sample evidence are removed.
- Evidence registration waits for a correlatable relay response and rejects
  malformed, unknown or incomplete responses.
- Run, pause, step, replay and cancel cannot advance durable state in the browser;
  absent a server runner API they fail closed.

## Deployed acceptance environment

- Workbench: `https://43.133.243.154.sslip.io/cloudctl-mobile/`
- Studio: `https://43.133.243.154.sslip.io/cloudctl-studio/`
- Control API: `https://43.133.243.154.sslip.io`
- API release: `/home/ubuntu/cloudctl-mobile/releases/20260901-1800`
- API service: `cloudctl-mobile-api.service`
- Database: dedicated PostgreSQL container and volume
- Existing GenericAgent and Edge Hub remain separate and active.

The operator side is an acceptance environment using development identity
headers behind the existing Nginx Basic Auth. Production still requires OIDC.

## Current hardware blocker

ADB state on 2026-09-01:

- `5934418a0821`: authorized Xiaomi M2010J19SC; deliberately not used.
- `APH0219624006517`: connected but unauthorized, believed to be the OnePlus.
- historical serial `b0644fb5`: not currently enumerated.

The OnePlus must approve the computer's USB debugging key once. ADB is used only
to install and observe the acceptance build. Final task execution must occur after
ADB is stopped and USB is disconnected.

## Remaining product scope

The following are not complete and must not be represented as complete:

- 118 catalog entries without backend operation adapters.
- Product/post editor CRUD, media ordering and revision approval workflow.
- Order entities, synchronization, detail and logistics workflow.
- Chat conversations, keyword/scene rules and multimedia reply assets.
- Account, group, media, watermark, automation package and APK rollout core pages
  that still use local arrays or mock clients.
- Durable Studio source drafts, validation/package build and server-controlled
  runner lifecycle.
- Server-verified screenshot/evidence object upload for mobile direct tasks.
- Formal production OIDC, production object storage and release signing.
- Final OnePlus no-USB/no-Edge/no-ADB hardware acceptance.

## V1 self-developed features (2026-09-05)

Beyond the 134 PDF competitor entries, the following original features are being
developed for CloudCtl:

### V1-05: Source connection and sync run entities (COMPLETED)

- Database schema: `source_connections`, `sync_runs`, `sync_errors` tables with
  tenant isolation, created_by tracking and full audit fields.
- Migration `20260905_0008_source_sync_tables.py` creates all three tables with
  proper indexes and foreign keys.
- All 413 backend tests pass including contract validation.

### V1-06: Source connector interfaces (COMPLETED)

- Abstract `SourceConnector` protocol with `test_connection()`, `preview()`,
  `sync()` methods.
- `CSVSourceConnector` for file-based sources with pandas parsing, validation
  and error tracking.
- `MappingEngine` validates records against entity kind schemas and accumulates
  field-level errors.
- Preview returns valid/invalid record counts and samples without persisting.
- Sync creates/updates records and logs errors to `sync_errors` table.
- Full unit test coverage for validation, deduplication and error handling.

### V1-07: Web source connection and sync error interface (COMPLETED)

- API routes: POST/GET `/api/v1/sources/connections`, POST preview, POST sync,
  GET runs, GET errors with optional resolved filter.
- Actor authentication with `ActorDependency`, database and ObjectStore injection.
- OpenAPI specification exported with 5 new endpoints.
- TypeScript types generated: `SourceConnectionCreate`, `SourceConnectionResponse`,
  `SourcePreviewResponse`, `SyncRunRequest`, `SyncRunResponse`, `SyncErrorResponse`.
- TypeScript client methods: `createSourceConnection()`, `listSourceConnections()`,
  `getSourceConnection()`, `previewSourceConnection()`, `startSyncRun()`,
  `listSyncRuns()`, `listSyncErrors()`.
- Vue view `SourceConnectionsView.vue` with connection list, sync runs display,
  error list with resolved filter, and real-time status updates via TanStack Query.
- Route `/sources` registered in router with proper metadata.
- Router tests updated for 20 core routes.
- All 413 Python tests and 40 TypeScript/Vue tests pass.

