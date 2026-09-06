# CloudCtl engineering rules

This repository implements the architecture in `docs/reference/`. Keep the following invariants in every change:

1. Only `packages/lamda-driver` may import `lamda`.
2. Browser and cloud services never connect to device port 65000 and never receive device PEM material.
3. Edge connections are outbound and authenticated; all device commands carry a lease ID and monotonically increasing fencing token.
4. A device has one active runner. Publish commit follows `commit_intent -> commit_once -> reconcile`; `commit_once` has one attempt.
5. PostgreSQL is the business source of truth, Temporal is execution history, S3 stores binaries/evidence, and Edge SQLite is a spool only.
6. Real-device tasks remain `blocked_hardware` until authorized hardware evidence exists. Mock tests never satisfy hardware acceptance.
7. Do not add arbitrary shell, ADB/SSH exposure, Frida, MITM, CAPTCHA handling, anti-detection, account farming, fake traffic, or unauthorized bulk actions.

## V1 execution ownership (ADR 0004)

**Production automation**:
- **Companion mobile-local** (`mobile/companion`): enrolled Android APK executes device tasks via accessibility without USB/ADB/Edge. Platforms: 闲鱼, 小红书, 抖音.
- **API publisher** (`services/control-api` publishers): server-side official API calls. Platforms: 微信公众号.

**Development/diagnostic only**:
- **Edge + LAMDA** (`edge/gateway`, `packages/lamda-driver`): Studio live layout inspection and evidence preview. Not required for production task delivery. Must not hold a write lease when Companion is enrolled.

V1 platform scope is exactly four: 闲鱼商品, 小红书图文, 抖音视频, 微信公众号文章. Other platforms are frozen for V1.

Keep edits inside your assigned component paths when parallel agents are active.


