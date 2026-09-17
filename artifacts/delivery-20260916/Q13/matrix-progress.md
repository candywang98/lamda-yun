# Q13 五机受控业务验收——执行中证据（2026-09-17 11:30-11:45）

## 已过项
1. **安全往返矩阵（门槛30次/台）**：五机各30次 probe 全 SUCCEEDED（150/150，idempotency q13-matrix-{A..E}-{1..30}）
   - 同机串行 ✓（每台30连发队列顺序消化）；异机并行 ✓（五机同时执行，跨4 OEM×3 Android版本）
   - A(9R/14) B(OnePlus7/12) C(P30Pro/10) D(vivo/10) E(小米/10)
2. **一机故障隔离**：11:35:51 force-stop E → 停机期间 B(e313cc6b)/C(38161f6b) probe 照常 SUCCEEDED → E 重启后无障碍被禁（AOSP 行为实证，小米允许 adb 恢复）→ 恢复后 E 领取 a5570fde SUCCEEDED
3. **订单同步（真机）**：A 机 xianyu.collect_orders.steps.v2 SUCCEEDED（55e3cfb7），xianyu_order 表新增行（总计10行，最新 03:43:30Z）
   - 首次尝试失败 NAV_RESET_FAILED → 根因1：ColorOS「应用启动确认」拦截 Companion 启动闲鱼（已勾选始终允许+打开，永久放行）→ 根因2：switchaccess 向导抢屏（已 pm disable-user 禁用，无障碍列表恢复干净）→ 重试成功

## 发现的真机问题（如实登记）
1. 【环境·已解】ColorOS 应用启动确认拦截外部 App 启动——装机清单需加「启动确认放行」步骤（OEM 差异：仅 ColorOS 出现）
2. 【环境·已解】switchaccess 与 CloudCtl 无障碍并存导致抢屏/uiautomator 桥故障——已禁用；运维清单：Companion 机不得安装其他无障碍服务
3. 【SOP 重申】force-stop 后无障碍禁用 = AOSP 通用行为（小米实测复现，与专家结论一致）

## 进行中/待办
- 发布草稿（open-only 到确认点）：A/B 机执行（登录态确认中）
- C/D/E 闲鱼登录态未知——业务项前需确认（可能需用户提供账号登录）
- IM 互斥：软件层已证（Q10/ACCOUNT_BUSY）；真机值班并发归 B 线后续
