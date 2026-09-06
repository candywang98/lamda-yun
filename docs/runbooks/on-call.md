# On-call and SLO response

The local compose stack provisions Prometheus rules, Alertmanager, and the `cloudctl-slo` Grafana
dashboard. `infra/otel/alertmanager.yml` intentionally retains alerts locally; it is not proof of
an external paging integration. Configure a reviewed receiver from
`alertmanager-oncall.example.yml`, send a test alert, confirm delivery and resolution, and record
the receiving escalation policy before production acceptance.

## Control API availability

Check ingress, `/health/live`, `/health/ready`, database pool wait, and recent deployments. Stop
new scheduling if business truth is unavailable. Roll back only through an approved change.

## Edge command ACK

Check Edge stream connectivity, network RTT, spool growth, and runner saturation. Do not bypass
the outbound authenticated stream or expose device port 65000.

## Schedule deviation

Check scheduler backlog, approvals, executor capacity, outbox lag, and maintenance windows. Do not
release work that lacks required authorization or evidence capacity.

## Device heartbeat

Confirm Edge health and last known device state. Treat an unreachable device as unavailable; do
not infer success from a stale heartbeat.

## Lease, lock, or fencing

Page P1. Put the device in maintenance, stop new scheduling, compare the database lease, highest
fencing token, active runner, and LAMDA lock. Never lower/reuse a token or let an old runner write.

## Unknown commit result

Page P1 and freeze the target. Preserve commit intent, before-commit evidence, workflow history,
Edge spool, and device observations. Reconcile read-only; never repeat `commit_once`.

## Evidence completeness

Stop completion/promotion of the affected high-risk task. Recover missing before/after/failure or
commit evidence without fabricating a result, then append the recovery action to audit.

## Edge spool and disk

Stop admission before the filesystem is full, preserve WAL/database files, upload high-priority
commit evidence first, and only delete acknowledged/reconstructable data through an approved
cleanup procedure.

## Telemetry pipeline

Check collector and Prometheus health, scrape targets, time synchronization, and label cardinality.
Telemetry loss must not weaken fencing, approvals, audit, or fail-closed behavior.

For every page, record severity, owner, request/correlation/workflow/device identifiers, timeline,
mitigation, recovery proof, and follow-up action. P5-004 remains pending until a real receiver and
escalation drill are evidenced.
