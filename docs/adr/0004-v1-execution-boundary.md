# ADR 0004: V1 execution boundary and platform scope

- Status: accepted
- Date: 2026-09-05
- Supersedes: aspects of historical LAMDA-primary architecture descriptions
- Related: ADR 0003

## Context

The project initially targeted a LAMDA-driven edge architecture where automation runs on a local workstation with USB-connected devices. ADR 0003 accepted mobile-local execution for production tasks. However, documentation in README.md, AGENTS.md, and various runbooks still refers to Edge/LAMDA as the primary execution path, creating confusion about the production architecture.

V1 development needs a clear boundary:
- Which execution methods are production vs. development/diagnostic
- What platforms are in scope for complete V1 delivery
- How device tasks and API-based publishing coexist
- Whether Edge/LAMDA and Companion can run simultaneously on the same device

## Decision

### Execution paths

**Production (V1)**:
1. **Companion direct**: Web → Control API → Companion APK (HTTPS) → AccessibilityService → platform app
   - Owner: `mobile/companion`
   - Platforms: 闲鱼商品, 小红书图文, 抖音视频
   - No USB, ADB, or local workstation required
   - Task delivery via HTTPS enrollment and claim protocol

2. **API publisher**: Web → Control API → server-side publisher → platform official API
   - Owner: `services/control-api` publisher modules
   - Platforms: 微信公众号文章 (via official API)
   - No device required for API-accessible platforms

**Development/diagnostic only**:
- Edge Gateway + LAMDA sidecar: for Studio live debugging, layout inspection, evidence preview
- Owner: `edge/gateway`, `packages/lamda-driver`
- Not a production execution dependency
- Must not conflict with Companion synchronization on the same device

### V1 platform scope

Complete V1 includes exactly four platforms:
1. 闲鱼 (Xianyu) - 商品发布 via Companion
2. 小红书 (Xiaohongshu) - 图文 via Companion  
3. 抖音 (Douyin) - 视频 via Companion
4. 微信公众号 (WeChat Official Account) - 文章 via official API

Other e-commerce or content platforms mentioned in the original architecture package are **frozen** for V1. They remain as extension points but are not in the V1 acceptance criteria.

### Shared business objects

Both execution paths use the same business domain:
- `Product`, `ContentRevision`, `MediaAsset` from source connectors
- `PublishPlan`, `PublishTarget`, `PublishSnapshot` for task persistence
- `CommitIntent` ledger for exactly-once commit semantics
- `PlatformAccount` and capability verification

The only difference is the executor:
- Companion tasks require `device_id` and accessibility permissions
- API publishers require server-side credentials and official SDK

### Runner exclusivity

A device enrolled to Companion must not simultaneously run Edge/LAMDA automation. The single-runner invariant (AGENTS.md rule 4) applies: one device, one active execution lease. Edge may observe or capture evidence, but must not issue competing write commands while Companion holds a task lease.

## Consequences

### Documentation updates required

1. **README.md**: clarify that Edge/LAMDA setup is for Studio/debugging, not production task delivery
2. **AGENTS.md**: add explicit Companion vs. Edge execution ownership
3. **docs/v1/02-实施方案.md**: reference this ADR for execution boundary

### Implementation boundaries

- `mobile/companion`: production Companion tasks, no Edge dependency
- `services/control-api`: API publishers, device-independent publishing
- `edge/gateway`: Studio/debugging only, no production task dispatch
- `packages/lamda-driver`: isolated LAMDA wrapper for diagnostic use

### Testing and verification

- Companion acceptance test (ADR 0003) runs without USB/Edge after enrollment
- API publisher tests run without devices
- Edge/Studio tests explicitly marked as development/diagnostic
- Hardware gates (`blocked_hardware`) remain for real-device evidence

### Non-goals

- Simultaneous Edge + Companion execution on one device (conflicts with single-runner rule)
- Additional platforms beyond the four listed (frozen until post-V1)
- Companion → Edge handoff or Edge → Companion migration (no active use case)

## References

- ADR 0003: Mobile-local production execution
- V1 implementation plan: `docs/v1/02-实施方案.md`
- Original architecture package handoff: `项目交接说明.md`
