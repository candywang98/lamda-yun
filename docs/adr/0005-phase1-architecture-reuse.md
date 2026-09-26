# ADR 0005: Phase 1 Architecture Reuse and New Component Boundaries

- Status: accepted
- Date: 2026-09-06
- Related: ADR 0003, ADR 0004
- Context: LAMDA-YUN Phase 1 Implementation (120 tasks)

## Context

Phase 1 implementation requires extensive changes to support:
- Real-time video streaming (R03: MediaProjection + WebRTC + TURN)
- Remote control with observer/controller separation (R04)
- Per-platform single account binding (R10)
- Recipe-based local state machines (R07, R08)
- Unified device write lease across all operations (R04, R09)

The existing codebase has:
- ✅ Tenant/User/PlatformAccount models
- ✅ Device/Edge enrollment
- ✅ PublishPlan/Target/Snapshot business objects
- ✅ CommitIntent ledger
- ✅ MediaAsset/Upload/Derivative
- ✅ Temporal scheduler
- ✅ Outbox dispatcher
- ⚠️ LAMDA-based Edge execution (ADR 0004: dev/diagnostic only)
- ❌ Real-time video streaming
- ❌ Remote control protocol
- ❌ Recipe engine
- ❌ Unified device lease

## Decision

### 1. Preserve Core Business Domain (复用)

**Keep and reuse**:
- `TenantRow`, `UserRow` - multi-tenant foundation
- `PlatformAccountRow` - extend with `platform`, `bindingVersion`
- `ProductRow`, `ProductMediaRow` - product catalog
- `ContentItemRow`, `ContentRevisionRow` - content versioning
- `MediaAssetRow`, `MediaUploadRow`, `MediaDerivativeRow` - media lifecycle
- `PublishPlan`, `PublishSnapshot`, `PublishTarget` - publication tracking
- `CommitIntent` - exactly-once commit ledger
- `AutomationVersionRow` - package signing and promotion
- Temporal workflows - scheduling and retry
- Outbox pattern - reliable event delivery

**Do NOT create parallel systems** for products, media, publishing, or scheduling.

### 2. Add Device Control Plane (新增)

**New tables** (services/control-api/migrations/):
```python
class DeviceLeaseRow(Base):
    """Unified write lease for AUTO/REMOTE modes"""

    device_id: FK(DeviceRow)
    owner_type: Enum["AUTO", "REMOTE"]  # task vs. manual control
    control_epoch: int  # fencing counter
    expires_at: datetime
    task_id: str | None  # if AUTO mode
    session_id: str | None  # if REMOTE mode
```

**Extend DeviceRow**:
```python
class DeviceRow:
    # existing fields...
    fencing_counter: int  # increments on re-enrollment
    maintenance: bool  # blocks AUTO tasks
```

**Key principle**: 
- Single writer per device at any time
- FIFO queue for AUTO tasks on same device
- REMOTE control must acquire lease, pausing AUTO
- Lease renewal required during long operations (e.g., media download)

### 3. Add Video Streaming Plane (新增)

**New service**: `services/video-relay/`
- WebRTC signaling server (WSS)
- TURN relay configuration
- Session management with device binding
- No video stored in database (only metadata)

**New protocol**: `contracts/video-streaming.proto`
- Offer/Answer/ICE candidate exchange
- Session authentication with deviceId + epoch
- Observer (read-only) vs. Controller (write) roles

**APK component**: `mobile/companion/.../video/`
- MediaProjection capture
- WebRTC PeerConnection
- Adaptive bitrate (target 720p@20fps, range 15-30fps)

### 4. Add Remote Control Protocol (新增)

**New protocol**: `contracts/remote-control.proto`
```
RemoteAction {
  session_id, control_epoch, seq, ttl_ms
  action: tap | swipe | key | type
  args: {x, y} | {text} | {key_code}
}
```

**Execution path**:
Web → WSS → APK → AccessibilityService

**Safety**:
- Requires REMOTE lease
- Epoch validation prevents stale commands
- TTL prevents queued old commands after reconnect
- Coordinate actions only (no shell/intent/root)

### 5. Add Recipe Engine (新增)

**New component**: `packages/automation-sdk/`
- Recipe manifest schema (JSON + signature)
- State machine interpreter
- Local variables, conditionals, loops (bounded)
- Whitelist of safe actions

**Storage**:
```python
class RecipeManifestRow(Base):
    id, version, hash, signing_key_id
    min_engine_version, platform, app_package
    command_types: list[str]
    state_graph: JSON
    published_at, published_by
```

**Principle**: 
- Cloud sends high-level Command (taskId, recipeId, snapshot)
- APK downloads signed Recipe
- APK executes state machine locally
- Cloud does NOT send low-level step-by-step instructions

### 6. Extend Account Binding (修改)

**Modify PlatformAccountRow**:
```python
class PlatformAccountRow:
    # existing: id, tenant_id, platform, external_subject_ref
    # ADD:
    verified_fingerprint: str | None  # actual login identity
    verified_at: datetime | None
    capabilities: JSON  # OAuth scopes, UI permissions
```

**New table**:
```python
class AccountDeviceBindingRow(Base):
    account_id: FK(PlatformAccountRow)
    device_id: FK(DeviceRow)
    platform: str  # 'xianyu' | 'xiaohongshu'
    binding_version: int
    status: Enum["BOUND", "UNBOUND"]
```

**Constraint**: One device can have ONE active binding per platform.
- 1 device → 1 xianyu + 1 xiaohongshu (parallel OK)
- 1 device → NOT 2 xianyu accounts simultaneously

### 7. Task State Machine (统一)

**Extend MobileTaskRow** → **PlatformTaskRow**:
```python
States:
  QUEUED → WAITING_MATERIALS → PREFLIGHT → RUNNING
  → PAUSE_REQUESTED → PAUSED_WAITING_USER → RESUME_CHECK
  → RECONCILING → SUCCEEDED/FAILED/CANCELLED/EXPIRED

Separate field:
  control_mode: Enum['NONE', 'AUTO', 'REMOTE']
```

**Key points**:
- REMOTE is NOT a task state (it's a control mode)
- Pause preserves queue position
- Cancel is terminal (cannot resume)
- Reconcile for uncertain commit results

### 8. Migration Strategy

**Phase 1A: Add without breaking** (T003-T011)
- Create new tables (DeviceLease, RecipeManifest, AccountDeviceBinding)
- Add columns to existing tables (fencing_counter, maintenance, binding_version)
- Migrations must be reversible

**Phase 1B: Feature flags** (T012-T025)
- Old step-based tasks continue to work
- New recipe-based tasks use new path
- Gradual cutover per platform

**Phase 1C: Cleanup** (post-T120)
- Deprecate old step execution
- Remove compatibility shims

## Consequences

### What to reuse (DO)
✅ Tenant/User/Auth framework
✅ Product/Content/Media domain models
✅ PublishPlan/Target/Snapshot
✅ CommitIntent ledger
✅ Temporal scheduler
✅ Outbox dispatcher
✅ MediaAsset upload/derivative pipeline

### What NOT to duplicate (DON'T)
❌ Second product database
❌ Second media storage
❌ Second task queue
❌ Second commit ledger
❌ Second device enrollment

### New services to add
➕ Video relay service (WebRTC signaling)
➕ Recipe engine (APK-side state machine)
➕ Remote control protocol (WSS)

### Database schema changes
📝 Add: DeviceLeaseRow, AccountDeviceBindingRow, RecipeManifestRow
📝 Extend: DeviceRow, PlatformAccountRow, MobileTaskRow
📝 Migrations: Alembic, must support rollback

### Risks and mitigations

**Risk**: Breaking existing tasks during migration
**Mitigation**: Feature flags, parallel execution paths

**Risk**: Device lease conflicts (REMOTE vs. AUTO)
**Mitigation**: Single DeviceLease table, epoch-based fencing

**Risk**: Recipe compatibility with app updates
**Mitigation**: Version ranges in manifest, graceful failure

## References

- Implementation handbook: `lamda_yun_一期智能体实施手册_需求确认版.md`
- Tasks T003-T025: Architecture foundation
- Tasks T026-T037: Video and remote control
- Tasks T038-T052: Recipe engine
