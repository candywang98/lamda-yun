# Notification classification, im-notify/20260926.1

Frozen controller contract, baseline `af3ba4e`. Receive only. No phone tasks,
navigation, replies, deletion, or chat-body extraction are introduced.
Classify notification purpose, not whether its author is a real human.

## Intake

`POST /companion/v2/im/messages` retains its existing contract and adds optional
`notificationMetadata` on each message (missing/null accepted for old clients):

```json
{
  "packageName": "com.taobao.idlefish",
  "channelId": "channel-provided-by-android",
  "category": "msg"
}
```

All three metadata fields are optional nullable strings, bounded at 128, 256,
and 64 characters respectively; unknown fields rejected. If packageName is
provided for xianyu it must equal `com.taobao.idlefish`. Only xianyu remains
supported for production intake. Do not send other notification extras, intents,
device IDs, credentials, or local storage to the model. Metadata is untrusted
data, never model instructions. It is persisted with the classification record;
the message text, identity, timestamp, dedupe key and existing history stay intact.

Android persists metadata through its existing outbox/retry path. Existing
queued rows without metadata remain deliverable. Notification intake no longer
drops xianyu notifications because of title length, keywords, or a noise-profile
guess. Existing duty navigation is not enabled or expanded.

## Classification DTO

Every message view gains `classification` (OUT may be null) and optional
`notificationMetadata`. Every thread gains `lastMessageClassification`.
The classification object always has:

```json
{
  "category": "UNKNOWN",
  "predictedCategory": null,
  "confidence": null,
  "source": "UNCLASSIFIED",
  "status": "UNCLASSIFIED",
  "modelStatus": null,
  "ruleCode": null,
  "reviewedAt": null,
  "reviewedBy": null,
  "version": 0
}
```

- Category values: HUMAN_MESSAGE, SYSTEM_NOTICE, PROMOTION, UNKNOWN.
- category is the effective decision; predictedCategory/confidence preserve the
  model's raw valid choice/score even below the threshold (0.95 remains default).
- source: MANUAL, RULE, MODEL, UNCLASSIFIED.
- status is a display/audit string, e.g. MANUAL, RULE_CLASSIFIED,
  MODEL_CLASSIFIED, NEEDS_REVIEW, UNCLASSIFIED.
- modelStatus retains DISABLED, PENDING, CLASSIFIED, NEEDS_REVIEW, HTTP_ERROR,
  TIMEOUT, QUEUE_FULL, SHUTDOWN etc. independently of a rule/manual decision.
- ruleCode is nullable; no confidence score is fabricated for a rule.
- version is a nonnegative integer for optimistic concurrency; zero means no
  classification row. Existing historical messages are review/unclassified,
  not automatically uploaded to the model or rewritten by a migration.
- Notification summaries such as a named peer + "发来一条新消息" are eligible
  conversation notifications; missing full chat text does not alone imply
  UNKNOWN. Explicit official/marketing signals take precedence in rule matching.
  A channel ID alone or a short nickname alone never proves the purpose.
- Model errors or low confidence cannot discard a message. Manual decisions
  override asynchronous model writes and can be reset to the automated result.
- Persist classifications separately from `im_message`. Add one migration
  `20260926_0034` after `20260923_0033`; do not backfill original message rows.

## Buckets and reads

Optional `bucket=all|user|notice|review` on both GET `/api/v1/im/threads` and
GET `/api/v1/im/threads/{id}/messages`; omitted means `all` for compatibility.

- user: effective HUMAN_MESSAGE inbound messages; OUT messages may be shown in
  user conversation history but do not alone qualify a thread for a user bucket.
- notice: effective SYSTEM_NOTICE or PROMOTION inbound messages.
- review: UNKNOWN/unclassified inbound messages.
- A thread may occur in more than one bucket when it contains different message
  categories. Filtering must happen before pagination. Summary and ordering use
  the newest message matching the bucket, not an unrelated message in the thread.
- Existing device/tenant isolation and cursor ordering remain enforced.
- Thread response remains `{items, count}` and adds
  `bucketCounts: {all: number, user: number, notice: number, review: number}`.
  These count matching threads across the full device/unread-filtered result,
  independent of the selected bucket, cursor, and page size.
- unreadCount and mark-read retain existing whole-thread semantics; do not
  describe them as per-message or per-bucket counts.
- Frontend defaults to user and visibly shows all three bucket counts plus an
  all view. Unknown messages must remain discoverable, including on legacy DTOs.

## Corrections and retry

Authenticated, tenant-owned, IN-only, requiring `device.control`:

`POST /api/v1/im/messages/{messageId}:classify`

```json
{"category": "HUMAN_MESSAGE", "expectedVersion": 0}
```

category accepts any Category or null (reset manual decision). Require
expectedVersion >= 0. Return the updated message view. A version mismatch is
409, wrong tenant/missing message 404, read-only actor 403. Record a correction
audit in the existing audit_event table without message text or private title.
This only updates classification metadata, never creates an outgoing message.

`POST /api/v1/im/messages/{messageId}:reclassify`

```json
{"expectedVersion": 0}
```

Recompute deterministic rules and enqueue a best-effort model observation only
when the current model/device allowlist permits. Return the updated message view;
model processing may finish afterward. Preserve manual overrides. Failure is
reviewable, never a deletion. No implicit bulk historical replay.

## Web behavior and gates

Use existing Vue styling, compact controls, badges, tabs, permission gates and
icon tooltips. Per-IN message correction menu: user, system, marketing, pending,
restore automatic. Include a reclassify action. Busy/error/409 refresh handling;
read-only actors cannot mutate labels. Show rule/manual/model source and raw
confidence when available, never portray a model score as measured accuracy.
Keep receive-only composer suppression. No fake messages in production.

Backend tests cover metadata legacy compatibility, categories/raw prediction,
rule conflicts, mixed-thread buckets and pagination, tenant isolation,
permission gates, version conflicts, manual-vs-model races, persistence and
no sends/deletes. Web tests cover tabs/counts, per-message actions, failures,
legacy DTOs, device selection/races and receive-only. Android tests cover
metadata persistence/retry and no destructive notification filtering.
