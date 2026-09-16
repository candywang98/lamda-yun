# 鱼游助手对照问答录（控机链路 · 专家评审稿）

- **对照对象：** 鱼游助手 v7.8.2（Auto.js Pro 9.3.11，包名 `com.ydydyd8818`）
- **提问口径：** CloudCtl Companion 在 OnePlus 9R / Android 14 / ColorOS + 闲鱼 Flutter 上踩过的真机事故，不是架构设想
- **答卷口径：** APK 明文中文、明文 API、能还原的函数体。jsjiami v6 未解开的标为未见/未知，不编
- **日期：** 2026-09-16（含第二轮追问 + 全量源码复核后的勘误）
- **配套：** 同目录《鱼游助手_v7.8.2_全量业务逻辑调研报告.md》写「做什么」；**本文件写「怎么点、怎么输、失败怎么办」**

---

## 评审怎么读

1. 先看「一句话结论」和「§0 两边怎么控」。
2. §1–§8 每节都是同一结构：**我们踩过的 → 问对方 → 他们怎么做**。
3. 「短版 12 问」可单独抽出去贴给参考产品。
4. 「仍缺」是源码仍钉不死、需要真机/对方口头补的。
5. 「对我们的含义」只给研究建议，**不改 CloudCtl 门禁**。

**本轮已更正、勿沿用旧句：**

| 旧结论（第二轮一度写下） | 源码复核后 |
|---|---|
| 相册故意跳过第 0 格快门（`indexInParent(1)`） | 源码无「快门」字面量。选图走 `select_aibum` 两路；`album_index` 是**批量进度游标**，不是格子下标 |
| 切瀑布流后改成第 N 项 | 切的是顶栏第 6 个 LinearLayout；**切完身份仍是标题**。该路径出现在搜索互动，不是「我的宝贝」主列表 |
| `setting.websocket_domain = wss://api.yuxianxian.com:7070` | 死配置。实际 WS：`wss://wss.yuxianxian.com:443` |
| 控机栈 = 无障碍 + Root `input tap` + Shizuku + OpenCV 找图 | Root `input tap` 仅 SDK&lt;7 分支；Shizuku 只在 Manifest 声明、业务 JS 无调用；OpenCV so 在包内但 JS 只用 `requestScreenCapture`，无 `findImage` |
| 「未出现确认按钮，准备重新点击」= 主动二击策略 | 该句出自 `start_xy_son` 且在恒假死分支（`'dkprc'!=='dkprc'`），不会执行。实际是线性连点、无任何去抖 |

红线（问参考产品时也要带上，防止对方方案把我们的门禁带松）：

- 真实删除 / 下架 / 发布须逐件授权。
- `UNKNOWN` 任务禁止自动重试。
- GATED / 单次 `dispatchGesture` 不可改成「没出弹窗就再点」。
- 生产路径不引入 Root、不静默写 `Settings.Secure`、不加 Frida/改包。

---

## 一句话结论

鱼游走的是「**无障碍 + 节点查找 + 坐标点击 + 失败就跳过/重试**」。  
动作锚点是可见按钮（降价 / 更多）的 `parent().click()`，不是卡片几何中心，也不是 bounds 二次校验。  
没有自有 IME，没有 `platformItemId`，没有 GATED `tapOnce`，没有 `UNKNOWN` / `RECONCILING`。

他们能「几乎总能删掉 / 发出去」，是**安全阈值更松 + 把环境配成脚本能跑**（指定闲鱼版本、搜狗/讯飞、标题不许重复、尽量 Root、别息屏），不是定位更稳健。  
CloudCtl 缺的那层稳健定位，这套 APK 里同样没有。

---

## 0. 两边怎么控

| | CloudCtl Companion | 鱼游助手 v7.8.2 |
|---|---|---|
| 主干 | AccessibilityService + 自有 IME CloudCtl Input | Auto.js 无障碍节点查找 + 坐标点击（仅 SDK&lt;7 分支走 root `input tap`）；无自有 IME，`setText` 失败换剪贴板并要求搜狗/讯飞。Shizuku 只在 Manifest 声明、业务 JS 无一处调用；OpenCV so 在包内，JS 层只用 `requestScreenCapture` 截图，无 `findImage` 找图 |
| 确认动作 | `dispatchGesture` 一次，失败就停 | `my_click`：`click(x,y)` → `press(10ms)` → `press(1ms)`，三次失败仅 console.verbose 记日志、静默继续 |
| 不确定结果 | `UNKNOWN` / `RECONCILING`，禁止盲续 | 无这套状态机；点了确定商品还在 = 静默当成功 |
| 并发 | 一台机同一时刻一个执行者 | 业务队列串行；`auto_monitor` 消息线程 + 防干扰线程并行 |
| 用户必须配合 | 开无障碍、选 CloudCtl Input（IM/描述） | 忽略电池优化、悬浮窗、后台弹出、指定闲鱼版本、搜狗或讯飞、标题不要重复、尽量 Root、别息屏 |
| 身份 | 目标是 `platformItemId`（删除挂起后的候选） | 标题当唯一键。明文：「系统根据宝贝标题判断宝贝的唯一性，请勿有标题相同的宝贝」 |

鱼游把系统难控转成「把环境配成脚本能跑」。CloudCtl 把同一类难控收进产品门禁，所以单点成功率看起来更低。

---

## 1. 无障碍树 / Flutter 定位

### 我们踩过的

1. 闲鱼 Flutter 列表经常**没有稳定 `viewId`**。字在 `contentDescription`，同屏多条只靠文本会糊。
2. **整列表被一个全高 wrapper 包住。** dump 里卡片没有独立 bounds，点 wrapper 中心 = 点到别的商品（第二次删除有弹窗截图铁证）。
3. uiautomator dump 和 Accessibility 树经常对不上。
4. 横幅会把整页坐标平移。草稿 tab 一天内 y 从 753–885 漂到 213–339，**546px**。写死坐标的批量下架基本不能用。
5. 小红书重置导航会被「是否保存草稿」挡住锚点，表现为 `NAV_RESET_FAILED`。

### 当时问对方

- 闲鱼列表定位靠什么：viewId、文本、截图像素、深度学习，还是自家 hook？
- Accessibility 树和 uiautomator dump 不一致时听谁的？
- 卡片嵌套在全高 wrapper 里，怎么算可点矩形？
- 布局平移 500px+ 时，旧坐标任务怎么失效？

### 他们怎么做

- 主力 Auto.js 选择器（含混淆 `["desc"]()` 写法全量计数）：`desc` 368、`text` 346、`descStartsWith` 120、`clickable` 189、`className` 112、`id` 68；`bounds()` 145 处但只取 `centerX/centerY` 转坐标点击，无 overlap 仲裁。Flutter Semantics / `viewIdResourceName` 在业务脚本里基本没有。`fishflutterboost` 只出现在鱼币 H5 URL，不是定位器。
- **商品身份 = 标题。** 无 `platformItemId`。
- 列表仍用「编辑宝贝列表第 N 个宝贝」「次翻动宝贝列表」——可见顺序，不是每件独立身份。
- 找不到：切瀑布流 → 翻列表 → 重载。没有「旧坐标任务作废」。
- 小红书草稿挡导航：文案「确定要退出发布吗？」+ 存草稿，点掉即走，不是 `NAV_RESET_FAILED`。

#### 1.1 落点不是卡片中心（第二轮钉死）

降价循环（解码后，活路径）：

```js
if (desc('降价').exists()) {
  var nodes = desc('降价').find();
} else {
  var nodes = text('降价').find();
}
for (let i = 0; i < nodes.length; i++) {
  // parent().parent() + indexInParent 只用来抠 title，做 _0xb16bf0 去重
  if (_0xb16bf0.indexOf(title) == -1) {
    toast("操作第" + (_0xb16bf0.length+1) + "个宝贝：" + title);
    _0xb16bf0.push(title);
    nodes[i].parent().click();   // ← 真正落点
    sleep(2000);
    // 等「现价」最多 5s，setText 新价，点「确定降价」
  }
}
```

| 我们踩过的 | 鱼游 |
|---|---|
| 点卡片中心 → 邻卡 / `CARD_BOUNDS_UNVERIFIED` | 不点中心。锚点是「降价」节点，落点是它的 `parent().click()` |
| 标题二次校验 | 点之前用 `parent().parent()` 抠标题，数组去重；**点完不回扫** |
| wrapper 整列矩形 / bounds | `bounds()` 用得多，但只取 `centerX/centerY` 转坐标点击；无整列矩形、无 overlap 仲裁 |
| 点「删除」按钮 | 降价不点删除。删除另走 `find(text('更多'))[0]` → `text('删除').click()` → `text('确定').click()` |

同一屏两个「降价」靠得近时，`parent()` 仍可能糊到相邻行。他们完成文案自己承认：成功数小于总数可能因为标题相同、无降价按钮、特殊宝贝。

删除 / 下架更粗：先按想要/标题收集，再 `find(text('更多'))[0]`——**可见第一张「更多」**，不是目标卡片上的那一个，也不是 `platformItemId`。保护文案 `'在保护时间内，无法删除'`。点完不回扫、不看角标、不比截图。

#### 1.2 切瀑布流（搜索互动活路径，不是「我的宝贝」主列表）

```js
if (text('筛选').exists()) {
  let filter = text('筛选').findOne();
  // 筛选.parent.parent 下 LinearLayout 数量 == 8 → 当前是列表模式
  if (filter.parent().parent().find(className('android.widget.LinearLayout')).length == 8) {
    className('android.widget.LinearLayout')
      .depth(filter.depth() - 1)
      .indexInParent('5')     // 字符串 '5'，不是数字 5
      .findOne()
      .click();
    sleep(2000);
  }
}
```

- 切的是顶栏第 6 个 LinearLayout（`indexInParent('5')`），深度 = 「筛选」depth − 1。不是点「瀑布流」文案，也不是坐标。
- 启发式：祖父节点下正好 8 个 LinearLayout 才切；布局一漂会静默失败。
- 切完身份仍是标题（`title.indexOf` / `text(title)`），没有改成第 N 项。
- 出现在搜索互动（`start_flow_search`）。「我的宝贝」主列表靠「降价」节点 + 标题去重。
- `FzrFz = "领取奖励"` 一类是死分支（`if (jqzqn !== jqzqn)`），不要被误导。混淆里 `===` / `!==` 两个不同字面量会让整段赋值变成死代码。

---

## 2. 点击不是「找到节点就 performAction」

### 我们踩过的

1. Flutter 列表经常不理 `ACTION_CLICK` / `ACTION_SCROLL_FORWARD`。我们点击走 `dispatchGesture`；滚动先试语义滚动，不行再手势上滑。
2. 手势上滑很容易过头。满幅 swipe 会把目标滑出屏幕。
3. 系统手势带会吞点击。ColorOS 底栏约 2400−2249。必须把点击夹进「卡片 ∩ 屏幕安全带」。
4. `dispatchGesture` 回调成功 ≠ 业务成功。第一次删除：确认手势发出去了，闲鱼商品还在。
5. **我们禁止 fallback。** 点不准就停。对方若靠「点三个候选之一」，误删率会低很多，但我们不能接受。

### 当时问对方

- 点击用 `performAction` 还是注入手势？Flutter 两种各成功率多少？
- 怎么处理底部手势区、全面屏指示条？
- 如何证明「确定」真的点到了，而不是 gesture completed？
- 失败后重试还是停？重试如何避免二刷误删？

### 他们怎么做

1. SDK&lt;7：root `input tap x y`
2. 否则 Auto.js `click(x,y)`
3. 失败 `press(x,y,10)` 再 `press(x,y,1)`
4. 三次失败：只 `console.verbose` 记「尝试三次点击后失败，手机操作系统异常，请尝试重启手机或更换手机」——**不抛错、不重试、函数静默返回**，调用方当成功继续。恒假死分支里是 `send_goods_card`（不会执行）。弹「检测到设备屏幕无法正常点击」toast 的是任务前的屏幕自检（goods_manage_b），不是点击重试
5. 另有节点 `.click()`、坐标点发送、「desc卖闲置不存在，启用备用方法点击」
6. `my_swipe`：老系统 `input swipe`，新系统 `swipe()`；`my_longclick`：老系统一小段 swipe 模拟，新系统 `press(duration)`

**底部手势条 / ColorOS 2400−2249：完全没处理。** 没有「卡片 ∩ 屏幕安全带」。

确认键无去抖、无幂等 token。「未出现确认按钮，准备重新点击」出自 `start_xy_son` 且在恒假死分支（`'dkprc'!=='dkprc'`）里，不会执行——**连这句防御都是死代码**，实际就是线性连点点完即成功。成功不跟列表消失 / 角标 / 截图哈希解耦。

---

## 3. 输入：SET_TEXT 在闲鱼上是幻觉

### 我们踩过的

1. 无障碍 `ACTION_SET_TEXT` 对闲鱼 Flutter 编辑器不可靠。节点文本瞬间变了，一重绘就没了（Q03 `c3b4a9ce`，「SET_TEXT 幻觉」）。
2. 描述字段用「前 16 字相同」当成功会误报旧草稿。
3. 价格不能当普通文本。闲鱼是自定义数字键盘。
4. 聊天框走「剪贴板 + 长按粘贴」会发出脏数据。失败必须 `INPUT_REJECTED`，绝不粘贴兜底。
5. 最终方案：强制切到自有 IME「CloudCtl Input」。验收完还得改回搜狗。
6. 即使自有 IME 也有三层坑：键盘起来后焦点在 IME 窗口；Flutter 不实现 `getExtractedText`；聊天编辑器大约每秒重启 InputConnection。
7. 搜狗占着输入连接时，SET_TEXT 进不了 Flutter 聊天框。
8. Android 14 / targetSdk 35 读 `Settings.Secure.ENABLED_INPUT_METHODS` 会 `SecurityException`，App 启动即崩，ColorOS 跟着把无障碍关掉。

### 当时问对方

- 闲鱼标题 / 描述 / 价格 / 聊天，分别怎么输入？
- 是否要求用户把默认输入法换成他们的？换了系统输入法后怎么恢复？
- 怎么验证「提交后重绘仍在」，而不是节点 text 闪一下？
- 是否处理过 Flutter 每秒重建 InputConnection？
- 价格是 SET_TEXT 还是点九键？

### 他们怎么做

无自有 IME。闲鱼 ≥7.14.50 硬依赖搜狗 / 讯飞。

| 场景 | 做法 |
|---|---|
| 能 `setText` 的框 | 直接 `setText` |
| 不稳 | `setClip` + paste / 点「粘贴」 |
| 闲鱼 ≥7.14.50 | 必须点输入法剪贴板气泡的校准坐标 |
| 校准 | 「绑定闲鱼」任务记下 x/y |
| 来喜输入法 | 已知会坏 |
| 聊天 | 「想跟TA…」+ 坐标点发送 |
| 降价循环内的新价 | 从「现价」抠数字 → 按比例/固定额算 `p2` → `setText(p2)`。**未见九键逐键** |

不校验「提交后重绘仍在」。换输入法皮肤 / 导航条 / 横幅后，校对坐标作废。  
价格是否走自定义九键：降价场景是 `setText`；发品价格是否点数字键盘，源码未钉死，不能当成他们点了九键。

---

## 4. 无障碍服务本身会掉、会重绑、会被系统杀

### 我们踩过的

1. ColorOS 上 `adb shell am force-stop` Companion 会关掉无障碍。生产版 adb 写不了 secure 设置，恢复只能人去设置里打开。
2. 「无障碍已开启」≠「服务实例活着」。要拆 `enabled` / `active`。
3. 负载下服务会自己 rebind，一次约 1 秒。wait 必须把 rebind 当瞬态。
4. Doze / 省电会杀前台同步。
5. claim 之后无障碍断开：释放协议源码有了，现网 APK 还没联调。

### 当时问对方

- 无障碍被关后怎么发现、怎么恢复？要不要人值守？
- force-stop、杀后台、电池优化分别怎么处理？
- 执行中途服务重绑，任务续还是重来？如何保证确认键不点第二次？

### 他们怎么做

- 发现：轮询 `auto.service`，队列显示「等待无障碍开启中」。
- **有 Root：** `init.js` 写 `Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES` + `ACCESSIBILITY_ENABLED=1`，toast「已自动开启无障碍」，外层 delay 1000ms。另有「授予root后请重启」。**生产 CloudCtl 不做这个。**
- **无 Root：** 跳系统无障碍设置让人手开。失败只 toast「请先开启无障碍」——下次点任务按钮才再卡。恢复时间完全取决于用户何时回到设置页。Shizuku 在 Manifest 里声明了 Provider（`com.ydydyd8818.shizuku`），但全部业务 JS 无一处调用——「Shizuku 特权备选」未见实装。
- 保活：忽略电池优化、`device.keepScreenOn(0xe10×0x18×0x3e8 = 86400000ms = 24 小时)`、前台服务、悬浮窗。息屏会断总控，策略是不让息，不是 Doze 下还能跑。
- **没有 OnePlus / ColorOS / 一加 分支。** 品牌只出现 oppo、vivo、小米、魅族。`ENABLED_INPUT_METHODS` SecurityException、ColorOS 关无障碍，脚本无特判。
- 会 `am force-stop com.taobao.idlefish`（杀闲鱼），**不杀自己**。没有 ColorOS 把无障碍一起掐掉之后的自救。
- **没有 1s 心跳、没有 `onUnbind` / `onRebind` 用于恢复。**

执行中途无障碍重绑 1 秒：脚本无确认键去抖、无点击幂等 token。删除确认是线性连点：

```js
find(text('更多'))[0].click();
sleep(1000);
text('删除').click();
sleep(1000);
text('确定').click();
sleep(1300);
```

若重绑落在 `text('确定').click()` 前后：**会点两次**；点完不回扫标题，商品还在也当成功、继续下一件；没有从当前商品断点恢复，只有标题数组去重，页面被重置则下一轮又从可见「更多」`[0]` 开始。

---

## 5. 窗口、焦点、前台抢占

### 我们踩过的

1. 闲鱼在前台时，Companion 自己的界面抢不回来。任务开始必须等到 Companion 成为活动窗口。
2. `FLAG_ACTIVITY_NEW_TASK` 启动已在前台的闲鱼是空操作，人停在里页时「回首页」不会发生。
3. 系统可能拦后台启动 → `LAUNCH_REQUIRES_USER`。
4. 确认框必须来自当前活动窗口；跨窗口拼会点到别的弹窗。
5. 值班模式曾在 RUNNING 任务期间重启闲鱼 + 坐标乱点，把正在输入的回复清掉。
6. 键盘起来后，底部坐标（如 975,2331）全废。

### 当时问对方

- 目标 App 已在里页，怎么可靠回到列表根？
- 自动化、投屏、值班轮询抢同一台机时谁让？
- 确认弹窗如何绑定「当前活动窗口」而不是屏幕上任意「确定」？

### 他们怎么做

- `back()` 循环直到 `text('消息')`；草稿点「确定要退出发布吗？」。
- 确认框全局 `text/desc('确定')`，**不绑当前 `windowId`**。
- 消息监听线程与任务并行，防干扰只看 `currentPackage` 是不是闲鱼/转转，**不给执行任务让路**。
- 聊天发送已在用坐标，键盘弹出后会漂。
- 无投屏远控。截图走 `requestScreenCapture()`（bz.js / main.js 申请），JS 层未见 `findImage` / `matchTemplate`——OpenCV so 在包内，但业务脚本没拿它找图，截图只用于日志/上传。
- Activity 拉起闲鱼 / 鱼币页在 OPPO / VIVO / 小米 13/14 会失败，补丁是「后台弹出界面 / 悬浮窗」，让用户自己搜机型教程。无 OnePlus 分支。

---

## 6. 确认弹窗 / 破坏性动作（对挂起删除最要紧）

### 我们踩过的

删除、下架、发布都有「确定」：

1. 弹窗要三元齐全：标题、取消、确定，位置合法，且是唯一结构。
2. 先点取消必须能闭环。
3. GATED：服务器先授权这一次点击，本地只许 tapOnce。
4. 点完必须独立观测：列表消失、角标 −1、截图哈希变。观测不到就 UNKNOWN，**不根据「我点了」认定删掉**。
5. 角标读不出时（`BADGE_UNREADABLE`）不能用角标当成功。
6. 列表第一击容易漂到图片 / 「去转卖」编辑器。

三次授权删除《如果历史是一群喵4》全没 happy path，但**零误删**。对方若「几乎总能删掉」，请追问误删率和失败重试策略。

### 当时问对方

- 破坏性确认如何和「点了」解耦？
- UNKNOWN 怎么处理？会不会自动再点一次确定？
- 批量删除 / 下架如何保证每件都是指定 commodity，而不是「当前第一张卡」？

### 他们怎么做

不解耦，无 UNKNOWN。

- **降价：** 可见「降价」→ `parent().click()` → 等「现价」→ `setText` → 「确定降价」。点前抠标题去重，点后不回扫。
- **删除：** `find(text('更多'))[0]` → `text('删除')` → `text('确定')`，各 sleep 1–1.3s。可见第一张「更多」，不是目标卡片上的那一个。
- 保护文案 `'在保护时间内，无法删除'`（时长是否写死未钉）。
- 成功 = 文案或直接进入下一件。点了确定商品还在 = **静默当成功**。
- 误删防护：标题唯一（用户承诺）+ 瀑布流降低叠层 + 保护期放弃。点前有标题去重，**不是**点前再读「这张卡现在是不是目标」的 bounds 校验。

对挂起删除的含义：同类「按钮锚点 + parent 热区」能躲开卡片中心误点，但解决不了 `CARD_BOUNDS_UNVERIFIED`，也没有 `platformItemId`。可以研究「点降价 / 更多 / 管理，不要点标题中心」作为布局策略；**不能把「可见第一张更多 + 点完当成功」搬过来。**

---

## 7. 任务生命周期

### 我们踩过的

1. 人在发布确认页时任务是 `WAITING_USER`。服务端 cancel 了，手机本地 PAUSED 行还占着，`claimNext` 被队头挡住。
2. 操作员手滑把草稿划没了，任务其实已经停对了（Q03 `d6e9f7a2`）。
3. 旧草稿 / 旧表单还开着时来新任务，第一步找「卖闲置」会超时。
4. 领取瞬间的动态头（lease/epoch）若算进动作身份哈希，服务器和手机对不上。

### 当时问对方

云端取消如何到达手机？暂停 / 等人时新任务怎么排队？

### 他们怎么做

- WebSocket `web_to_aj_command` 可删任务、清空队列、强制结束、`restart_aj`。
- 本地 JS 数组队列。无 CLAIMED / lease / WAITING_USER。
- 发布确认由脚本自己点确定，人等不是一等公民。
- 息屏断线则取消丢失。
- 旧草稿靠回首页 + 点退出发布。
- 云端取消后几秒能领新任务：间隔未知。

---

## 8. 媒体、通知、其它平台边角

### 我们踩过的

1. 闲鱼相册格子：**第 0 格是快门，不是照片**。按「前 N 张图」会打开相机。
2. MediaStore 写入目录必须带规范尾斜杠，MIME 要补扩展名。
3. 闲鱼通知通道混着营销 Feed。私信和 Feed 的 channel id 要现场标定。
4. 抖音选图：要点「选中勾」所在的 cell 容器。
5. 投屏是 JPEG 帧，不是完整远控协议；和自动化抢单写者。

### 他们怎么做

#### 相册（源码复核后，覆盖第二轮「跳过第 0 格」）

源码无「快门」字面量。选图走 `select_aibum`：

1. 先 `className("ImageView").descStartsWith(title_md5)` 点**已下载缩略图**。
2. 之后分两路（都是活代码）：
   - 「所有图片和视频」：点 `desc("双击选择当前图片")`（最多 9 次）
   - 「所有文件」：把可点的 `desc("选择")` `reverse()` 后逐个点
3. 最后「下一步」。
4. 找不到则 `aibum_list_down` 下滑重试（`android.view.View` depth=`goods_dep+7` 的 `scrollForward`）。25 次仍失败：back + 递归 `select_aibum`，toast「相册列表加载失败，准备重新加载...」。

`album_index` 是**批量发品的进度游标**，不是相册格子下标。  
第二轮看到的 `indexInParent(1)` 来自混淆恒假比较附近的死/歧义分支，**不能当成「故意跳过快门格」的产品策略。**

对我们的含义：闲鱼第 0 格是快门这件事仍然成立（我们真机踩过）；只是**不能再说鱼游用下标硬跳过第 0 格**。他们靠的是「先点自己刚下载的缩略图 desc」，碰巧躲开快门。

#### 其它边角

- 闲鱼版本钉死：`7.9.70` 一档兼容；`7.14.50` 主推荐（剪贴板）；`7.18.92` 当前钉。发品图数量对不上就让换 7.18.92。7.18.92 取消会玩帖子首页展示后不再更新该功能。`7.4.10` 只出现在 IME / 剪贴板分支。没有跟随商店最新版。
- 下载后 `update_MediaStore(path)`，尾斜杠 / MIME 是否规范看不清。
- 消息是进闲鱼消息列表扫未读，无 notification channel 白名单，营销 Feed 可能当买家。
- 小米双开不支持总控回复；分身要用户先点开一个闲鱼。
- 无 scrcpy 远控。
- 小米 4c：发布直接进拍照，无法发宝贝。

---

## 短版 12 问对照（可直接贴）

按优先级问这 12 句就够判断他们是不是同一条路：

| # | 问 | 鱼游答 |
|---|---|---|
| 1 | 闲鱼列表点第 N 个商品，还是按标题/ID 找？Flutter 无独立 viewId 怎么办？ | 标题当唯一键。降价落点是「降价」`parent().click()`；删除是可见第一张「更多」。无 viewId，无 `platformItemId` |
| 2 | 点击用节点 Action 还是手势注入？底部手势条怎么躲？ | 节点 `.click()` + `click(x,y)` + press 三级降级（仅 SDK&lt;7 走 root `input tap`）。底栏不躲。三次失败只记日志 |
| 3 | 闲鱼描述/聊天用 SET_TEXT 吗？要不要换系统输入法？ | 先 setText，不行剪贴板。闲鱼钉 7.14.50 / 7.18.92，强制搜狗/讯飞。无自有 IME |
| 4 | 如何证明输入在**重绘之后**还在？ | 不证明 |
| 5 | 无障碍被 ColorOS 关掉或 force-stop 后，要不要人去设置里打开？ | 有 Root 写回 Secure；无 Root toast 等人，无自愈轮询。force-stop 只杀闲鱼不杀自己。无 ColorOS 特判 |
| 6 | 执行中途 AccessibilityService 重绑 1 秒，任务怎么续、确认键怎么防二击？ | 无处理。确定会连点；点完当成功 |
| 7 | 删除/下架点了「确定」但商品还在，算成功、重试，还是停？ | 静默当成功，继续下一件。无 UNKNOWN |
| 8 | 点错相邻商品的误删，靠什么防止？有没有「标题二次校验」？ | 点前标题数组去重；点的是按钮 parent 不是卡片中心。无 bounds 校验。同屏两个「降价」仍可能糊行 |
| 9 | 批量动作是「当前可见第一张」还是每件独立身份？布局漂 500px 怎么办？ | 删除用可见「更多」`[0]`。瀑布流只换布局（顶栏第 6 个 LinearLayout），身份仍是标题。启发式 8 个 LinearLayout 一漂会静默不切 |
| 10 | 云端取消任务后，手机队列几秒内能领新任务？ | WS 删本地队列项，间隔未知；息屏窗口取消丢失 |
| 11 | 目标 App 已在里页或被草稿弹窗挡住，怎么回根页面？ | `back()` + 文案锚点。Activity 拉起在 OPPO/VIVO/小米 13/14 会失败。无 OnePlus 分支 |
| 12 | 一台设备能否同时跑：发品、回消息、值班轮询、投屏？不能的话谁让路？ | 业务串行，监听并行。无远控。无「执行期值班必须停」 |

如果答案是「无障碍 + 坐标脚本 + 失败就重试」，和我们是同一类，只是他们把安全阈值放宽了。  
如果是「厂商 / 无障碍增强 + 自有 IME + 业务 ID 映射」，那才是我们现在缺的稳健定位（`platformItemId` 映射正是删除挂起后的候选方案）。

**判定：鱼游属于前者。**

---

## 仍缺、建议继续问

下面只留**源码仍空、且会撞上挂起删除或输入**的。按组复制给对方 / 真机。

### A′. 删除（挂起文档仍优先）

1. 从列表进**详情页再点管理菜单**（编辑/下架/删除）有没有？我们 v2 走这条，卡在进详情前的卡片点击。降价是 `降价.parent().click()`，删除若只有「可见第一张更多」，进详情这条可能根本没有。
2. 「在保护时间内，无法删除」是 sleep 多重试、跳过并记成功、还是当失败？时长写死多少？
3. 已下架 tab 的删除，锚点还是「更多」，还是改成「删除」按钮？已下架卡片往往没有「降价」。
4. OpenCV 找图在删除/下架里用不用？（so 里有，业务脚本是否真调）

### B. 输入（发布描述、价格、IM）— 整组仍缺

1. 闲鱼描述框 `setText` 之后，读回的是节点 text、desc，还是截图 OCR？有没有「写上了、一滑就没了」的工单？
2. 价格是 `setText`、剪贴板，还是点自定义数字键盘？7.14.50+ 价格和标题是不是同一套剪贴板坐标？
3. 「绑定闲鱼」校对剪贴板气泡：开哪个框、点哪里、存绝对坐标还是相对输入框。换搜狗皮肤/横竖屏/全面屏要不要重绑？
4. 来喜输入法具体怎么坏？除搜狗/讯飞外还验证过谁？
5. 聊天「通过坐标点击发送」在键盘弹起后坐标怎么补？
6. 有没有遇到 Flutter 输入框每秒重建、setText 被吞？

### C′. 保活只剩一条

Shizuku 无 Root 时到底能写哪些：只启动 Activity，还是也能写 `ENABLED_ACCESSIBILITY_SERVICES`？

### E. 队列 / 取消（仍缺）

1. WS 下发「删除任务」时若正卡在确认弹窗：当前 `click` 跑完再清，还是立刻停手势？
2. 发品队列和消息回复冲突时，有没有「正在发品则暂停回复」的实现（不只总控文案）？
3. 息屏断线重连后，未完成任务是重做、跳过，还是要总控再派？重做如何避免二发？

### F′. 批量计数（可选）

「第 N 个宝贝」的 N 是当前可见屏第 N 张，还是含已滚走的全局第 N？中间插广告卡怎么数？切瀑布流后一屏更多，N 会不会错位？

### G′. 通知（可选）

「清除非买家未读」的判定规则（头像、文案关键字、入口）？（`libroot_automator.so` 在包内、JS 无 `RootAutomator` 调用——若引擎层真用了它，失败时会不会在脚本不知情下再点一次？）

---

## 对我们的含义（先别改门禁）

可以研究、不要直接搬：

- **动作锚点用可见按钮（管理/更多/删除）的 parent 热区，不要点卡片几何中心。** 这是第二轮唯一对挂起删除有用的布局启发；仍必须保留标题二次校验和 bounds 仲裁，不能改成「可见第一张更多」。
- 瀑布流作为只读布局预处理（顶栏启发式，失败要可观测，不能静默不切）。切完身份仍按标题 / 将来的 `platformItemId`，不改第 N 张。
- 相册：我们对「第 0 格是快门」的真机知识仍然有效，应继续当硬规则。鱼游的实际做法是「点自己刚下载的缩略图 desc」，不是下标跳过第 0 格——可参考「用业务标记选图」，不要抄下标。
- 闲鱼版本钉死在已验证档（他们是 7.14.50 / 7.18.92；我们设备当前版本要单独登记，不能盲跟）。
- 保护期「无法删除」当可预期失败，而不是 UNKNOWN 重试。

明确不要搬：

- 确认键连点、Root 写无障碍、标题当唯一 ID、剪贴板坐标当输入主路径、成功=文案或「点完即成功」、监听线程和任务并行、无 Root 时无自愈。

挂起删除的下一步仍以交接文档为准：XML 离线回放匹配器、卡片节点优先于 wrapper、新鲜度参数。可额外试「先解析卡片内管理/删除/更多按钮再点 parent」，而不是点标题中心；真机时一次性授权一批已下架测试商品。

---

## 证据边界

- **鱼游侧：** APK 明文中文、明文 API、能还原的函数体。jsjiami v6 未解开的标为未见/未知，不编。已钉：降价循环、瀑布流活路径（搜索互动）、删除连点、`select_aibum` 两路选图、版本配置键、实际 WS `wss://wss.yuxianxian.com:443`。
- **CloudCtl 侧：** OnePlus 9R `b0644fb5` 真机记录与 `mobile/companion` 代码；挂起问题见 CloudCtl 仓库 `artifacts/tasks/P09-unknown/xianyu-maintenance-20260916/delete-automation-issue-handoff.md`。
- 本问答录不代替执行计划；不把参考产品的通过写成 CloudCtl 验收通过。
- 不提供可运行的控机脚本、不补 exploit、不给出可直接复用的攻击载荷。

本地证据：

| 文件 | 内容 |
|---|---|
| `~/Desktop/鱼游助手_v7.8.2_全量业务逻辑调研报告.md` | 全部业务模块（做什么、从哪进、成功/失败文案） |
| `~/Desktop/LAMDA云控系统/cloudctl-source/docs/compatibility/yuyou-assistant-qa.md` | 本问答录在仓库里的工作底稿（相册「跳过第 0 格」未改，**以本桌面稿为准**） |
| `GenericAgent/temp/yuyou_apk_analysis/decoded_clean/` | 去二次转义后的 JS |
| `GenericAgent/temp/yuyou_apk_analysis/report_correction_notes.md` | 已钉死、勿回退（WS / 选图 / album_index） |
| `~/Downloads/鱼游助手_v7.8.2.apk` | 原始包 |

---

*专家评审请以本文件为准。仓库底稿 `yuyou-assistant-qa.md` 第 22 / 222 / 250 / 294 行仍写着「快门已钉跳过第 0 格」，那是第二轮的旧结论，源码复核后作废。*
