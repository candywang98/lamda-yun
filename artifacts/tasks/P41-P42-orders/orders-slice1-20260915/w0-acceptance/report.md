# W0 真机验收报告：订单同步 slice 1 readOrders 采集 — 2026-09-15

执行：W0 总控，串行持 DEVICE:b0644fb5。生产首尔 `orders-7adc827`（后端）+ 翻转后 APK（2df376b 翻转 + 重试修复提交）。全程只读采集（导航+读取），零平台副作用，不涉 G3。

## 验收结论：✅ 双方向真机采集闭环通过

| 项 | 结果 |
|---|---|
| SOLD 采集 run `bdb3dc74`（task e1c912db） | **SUCCEEDED**，3 行真实订单入库 |
| BOUGHT 采集 run `3f77b85f` | **SUCCEEDED**，3 行真实订单入库 |
| 操作员查询 `GET /api/v1/orders?direction=SOLD` | 200，total=3，camelCase 视图（W3 页面数据源） |
| 幂等重放（同 Idempotency-Key 再 collect） | 200 + `Idempotency-Replayed: true`，无重复行 |
| 价格碎片解析（U+200B） | ¥10.80→1080、¥8.88→888、¥0.80→80、¥17.88→1788 全对 |
| 复合自然键 | `SOLD|RUSHANG|《黄同学漫画二战史2》个人闲置|1080` 等与勘察 dump 逐行一致 |

入库样本（SOLD）：RUSHANG/交易成功/1080、tbNick_d7yml/交易成功/888、cll嘎哈/交易关闭，有退款/888。
入库样本（BOUGHT）：星光卡劵/等待见面交易/80、爱写作的大师兄/等待见面交易/680、大大章鱼/交易成功/1788。

## 验收中发现并修复的缺陷（第一轮失败）

- 首轮 run `9f35a8a9`（task 4579e4d1）：前两步导航全绿（翻转生效），第 3 步 readOrders `LOCATOR_NOT_FOUND`——**Flutter 订单列表在导航 tap 落点后仍在渲染**，容器一次性解析扑空（手机停在订单页、3 行节点俱在，实锤时序问题而非锚点错误）。
- 修复：readOrders 容器解析在步超时窗口内轮询重试（700ms 间隔，与既有 waitFor 同语义；空列表=成功 0 行不重试；调用方传入的 min(任务死线, 步超时) 即重试窗口）。新增 2 个单测（渲染中重试成功 / 窗口耗尽 LOCATOR_NOT_FOUND）。
- 测试期间发现测试自身问题：ticking elapsed 与 execute() L145 的组合死线交互——修正后 Android 全量 BUILD SUCCESSFUL。

## 定位器翻转记录（§7 纪律）

- `xianyu_order_list_sold` → `Text("我卖出的")`（实测 text 字段 TextView，非 desc）
- `xianyu_order_list_bought` → `Text("我买到的")`
- `xianyu_orders_container` → `IndexedContentDescriptionPrefixParent("订单信息", 0)`（行的共享父节点）
- `xianyu_order_detail_container` 预注册为未验证（slice 2 详情采集，fail-closed 机制持续有真实测试对象）
- 翻转提交前 Android 全量单测绿（含改写后的注册表测试）。

## 遗留（非阻塞）

- occurred_at 恒空（列表页无时间字段，slice 2 详情页升级）
- 复合键碰撞局限（同对手同商品同价去重）——契约 20260915.2 已记
- 采集入口 Web 按钮可启用（定位器已 verified；下轮 W3 小改）
