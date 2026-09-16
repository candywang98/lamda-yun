# Q03 real publish acceptance — PASSED (2026-09-16 14:0x, Asia/Shanghai)

- Task: 24c923bb-2691-4ae9-b285-8f91a281e87f (platform-tasks, family-A, Idempotency-Key q03-publish-v112-20260916-07)
- Recipe: recipe-xianyu-publish-2 v1.1.1 (hash becbe9d8…) — APK revision 628f19c
- Graph journal: all 12 states SUCCEEDED (wait-home→…→await-confirm), ~12s
- Checkpoint: PAUSED_WAITING_USER persisted (open-only terminal; result = 到达确认点)
- Operator completion at checkpoint (authorized by user): price 9.90 via 价格设置 keypad + 发布
- Listing verified LIVE: 我发布的→在卖 187 (+1), first card 云控平台验收测试服务 ¥9.9 包邮 (q03-onsale.png, q03-listing-live.png)
- Description IME commit verified re-render-stable (q03-f1.xml: standalone text node; f2 scroll test passed)
- Failed predecessors this run (all distinct root causes, fixed same day):
  2414914b (old graph missing edit page), 92dda2c4 (stale venv editable path on deploy),
  e22395db (tap settle wait missing → v1.1.1), db2d6347 (resume persistence bug), d6e9f7a2 (checkpoint OK; operator fling destroyed draft), c3b4a9ce (checkpoint OK; SET_TEXT illusion → CloudCtl Input IME required), 4dfa8dfc (claimed during a11y rebind window)
