# 第 3 次授权删除验收 — 安全失败 CARD_BOUNDS_UNVERIFIED（2026-09-16 08:07）

- Run 0cde3802 / Task 1ebd70fd（幂等键 authorized-delete-b0644fb5-miao4-20260916-03），用户授权对象：《如果历史是一群喵4》
- APK 81e24ec（含 W-A 双防线）。结果：**FAILED / CARD_BOUNDS_UNVERIFIED，Companion terminated the task safely**

## 经过

- 步骤 0-2 全部成功（导航到已下架列表）；步骤 3（tapCardByTitle）启动后 ~6s 安全终止
- 日志序列：08:07:08 launchTargetApp OK → 08:07:09 NAV_RESET_BACK → 08:07:15 CARD_BOUNDS_UNVERIFIED
- **门控从未打开（无 GATED_DESTRUCTIVE_INTENT），零副作用**；任务干净终态 FAILED（非 UNKNOWN，无需对账）
- 目标完好：《如果历史是一群喵4》仍在已下架列表首位 [0,345][1080,764]，完全可见

## 诊断

- 列表已重排：两本「售出下架」书（二战史2/数王国）已售出离列 → 喵4 升至首位、整卡可见、无歧义
- 但新鲜度仲裁器仍在可见、唯一的目标上判 UNVERIFIED → 指向仲裁参数对真机 Flutter 渲染过严
  （150ms settle / 40px Chebyshev 容差 / 双读一致），或卡读数在 wrapper 节点 [0,345][1080,2337]
  与卡片节点 [0,345][1080,764] 之间解析摇摆（>40px 即判漂移）
- W-A 交付时已预警：参数未经真机实证、安全方向假阳性可能——本结果即该预警命中（fail-closed 方向正确）

## 三次尝试对比（安全机制全部兑现，happy path 未达成）

| 次 | 结果 | 失败点 | 机制表现 |
|---|---|---|---|
| 1 | UNKNOWN | 确认击后效果不可证 | 台账+对账拦住不确定结果 ✅ |
| 2 | UNKNOWN | 过期 bounds 点错卡 | 单发窗口校验拒绝派发，零误删 ✅ |
| 3 | FAILED | 卡可见仍判 UNVERIFIED | 门控前安全终止（新防线）✅ |

## 建议（待用户裁决）

- 业务目标（删掉 ¥12.8 旧书）→ 手动 10 秒可完成
- 自动化删除 happy path → 需带真机日志调参（settle/tolerance/节点解析优先级），
  建议改为「用户一次性授权一批测试商品」批量调参，而非逐件授权单次试错
