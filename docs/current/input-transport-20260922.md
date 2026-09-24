# B14 输入通道升级执行计划（2026-09-22）

## 范围

按用户要求不调查、不接入闲鱼/淘宝开放平台业务 API。使用 Android 系统公开 Accessibility API；不增加 Root、ADB、Shizuku、Device Owner 生产依赖。主线代码路径为 cloudctl-source，保留本轮开始前评价模块和设备锁的未提交改动；不提交或部署。

## 冻结设计

1. Android 13+：XML flagInputMethodEditor + 自定义 accessibilityservice.InputMethod，独立编辑连接读写，保留用户当前键盘。主线程串行捕获/校验编辑器生命周期，IPC 读取在后台，读取返回后复核 generation，过期读取无效。
2. Android 11–12：用户预先启用同包 CloudCtl Input；Accessibility SoftKeyboardController.switchToInputMethod 按 ID 切入。切换事务只包住这一次 replaceText，不跨整个任务。finally（包括取消）按原 ID 精确恢复并观察实际 ID；用户中途选了其他输入法则保留并返回 USER_INTERFERENCE；恢复失败返回 IME_RESTORE_FAILED，禁止把切换 true 当恢复成功。不调用 setInputMethodEnabled。Android 13+ 无障碍编辑连接未绑定时必须 INPUT_READBACK_UNAVAILABLE / INPUT_REJECTED，绝不调用 TemporaryImeSwitch，绝不切走用户搜狗/讯飞。
3. Android 10：保持用户显式选 CloudCtl Input 的边界。非当前时拒绝无人值守文本输入，不走剪贴板。
4. 文本事务：目标包/定位器/窗口节点身份与 EditorInfo 指纹一起钉住；完整回读包含选区、offset 和截断检查。密码字段不操作；composition 不打断。默认仅允许空框或已等于预期的完整内容，其他旧草稿返回 FIELD_DIRTY_BY_USER，不静默覆盖。
5. 写入最多一次；commit 后重建连接只能重新读取同字段，不能重发。连续两次全文严格相等并且字段/连接稳定，才形成输入证明。replaceText 成功后按 targetPackage + locatorRef 持有一次聊天证明；发送点击前由 LocalAutomationUi 复核定位器、会话守卫、编辑器字段和全文，发送后消费。无证明、过期或变化则拒绝。waitForText / visibleTextContains / 剪贴板都不是发送授权。非聊天描述在本次 replace 返回前完整复核，不持有发送证明。API 30–32 的旧 InputConnection 读不到真实选区时，证明只认全文、generation 和字段身份，不伪造选区到末尾。目标变化/读取不完整/用户修改停止；不宣称 UI 读取等于消息已送达。
6. 闲鱼描述和聊天统一受控输入，去掉描述 SET_TEXT/剪贴板/长按粘贴链，去掉描述整页子串成功条件。价格按 xianyu_price 定位器分流，金额维持九键数值回读；数字描述不能误走价格。
7. UI 按版本说明能力：API33 不要求设 CloudCtl 为日常键盘；API30–32 只提示启用备用；API29 提示需手工选择。能力领取门与上述通道一致，但字段绑定仅运行时判定。

## 检查点

- C1 设计与接口核实：本文件、SDK/AOSP签名核验、基线diff和设备锁只读状态；立即记录09/01/00/10。
- C2 实现：输入抽象、无障碍适配、临时切换恢复、文本证明、现有调用接线和UI；模块测试与debug/APK instrumentation构建。
- C3 验证与交接：全量Android单测、lint、debug和androidTest构建，关键负例复验；受控输入靶场供真机验证。不改服务器、不发真实聊天、不发布商品。

## 软件验收

必须覆盖：API29/30/33能力决策；第三方键盘不切换；offset未知/非零、选区被遗漏、窗口到上限、密码、composition；旧草稿拒绝；仅一次commit；commit后generation变化只读；目标/字段消失；用户修改；切换拒绝/取消/恢复失败/用户改选；数字描述不走价格。

命令：mobile/companion/gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleDebugAndroidTest；python scripts/plan_guard.py docs/current/tasks.json；git diff --check。保存实际退出码/测试数，不用mock代替设备验收。

## 真机边界

发现USB b0644fb5与Wi-Fi 192.168.5.6:5555。现有设备锁库未初始化，FREE不证明空闲；其他OCR会话正在核实设备占用。未取得生产租约/远控/实体使用证明前不安装、不驱动共享手机。先完成全部软件和受控测试准备；真机项保持blocked_hardware，不把Android 13–15或ColorOS兼容性写成已通过。

设备验收需保留搜狗/讯飞默认，测试空框中文/emoji/换行/长文、restart后文本存活、用户并发输入拒绝、IME精确恢复。仅在测试靶场输入，不点击真实发送/发布。
