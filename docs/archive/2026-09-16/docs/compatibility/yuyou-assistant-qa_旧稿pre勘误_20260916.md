# 鱼游助手对照问答录

对照对象：鱼游助手 v7.8.2（Auto.js Pro 9.3.11）。采集口径见文末「证据边界」。  
本仓库挂起问题：[闲鱼自动删除 happy path 未达成](../../artifacts/tasks/P09-unknown/xianyu-maintenance-20260916/delete-automation-issue-handoff.md)。

用途：CloudCtl 真机再卡在无障碍 / 输入 / 删除 / 保活时，按章节把「下一轮要问」整段复制给参考产品，不必重讲背景。

结论（2026-09-16，第二轮已钉死落点）：鱼游是「无障碍 + 节点查找 + 失败就跳过/重试」。动作锚点是可见按钮（降价/更多）的 `parent().click()`，不是卡片中心、不是标题、不是 bounds 二次校验。没有自有 IME，没有 `platformItemId`，没有 GATED tapOnce，没有 UNKNOWN。他们能「几乎总能删掉/发出去」，是阈值更松 + 环境约束，不是定位更稳健。CloudCtl 缺的那层稳健定位，这套 APK 里同样没有。

---

## 怎么用

| CloudCtl 正在卡 | 先读 | 直接去问 |
|---|---|---|
| 删除点错卡 / `CARD_BOUNDS_UNVERIFIED` | §1、§1.1、§6、挂起文档 | 第三轮 A′（详情路径、保护期、点后回扫） |
| 描述/聊天 SET_TEXT 幻觉 | §3 | B 组（仍缺） |
| ColorOS 无障碍掉线、force-stop | §4 | 已钉：无特判、无 Root 等人；C 组只剩 Shizuku 写哪些 |
| 确认键点了商品还在 | §2、§6 | 已钉：当成功，继续下一件 |
| 队列被 PAUSED/WAITING_USER 卡住 | §7 | E 组（仍缺） |
| 批量下架、布局漂 500px | §1、§1.1、§6 | F 组可再问广告卡/N 的计数 |
| 相册点到快门、通知当买家 | §8 | 快门已钉跳过第 0 格；通知规则仍缺 |

红线（问参考产品时也要带上，防止对方方案把我们的门禁带松）：

- 真实删除/下架/发布须逐件授权。
- UNKNOWN 任务禁止自动重试。
- GATED / 单次 `dispatchGesture` 不可改成「没出弹窗就再点」。
- 生产路径不引入 Root、不静默写 `Settings.Secure`、不加 Frida/改包。

---

## 0. 两边怎么控

| | CloudCtl Companion | 鱼游助手 v7.8.2 |
|---|---|---|
| 主干 | AccessibilityService + 自有 IME CloudCtl Input | Auto.js：无障碍 + Root `input tap` + Shizuku + OpenCV 找图 + 系统 IME 剪贴板 |
| 确认动作 | `dispatchGesture` 一次，失败就停 | `my_click`：`click(x,y)` → `press(10ms)` → `press(1ms)`，三次失败建议重启/换机 |
| 不确定结果 | `UNKNOWN` / `RECONCILING`，禁止盲续 | 无这套状态机 |
| 并发 | 一台机同一时刻一个执行者 | 业务队列串行；`auto_monitor` 消息线程 + 防干扰线程并行 |
| 用户必须配合 | 开无障碍、选 CloudCtl Input（IM/描述） | 忽略电池优化、悬浮窗、后台弹出、指定闲鱼版本、搜狗或讯飞、标题不要重复、尽量 Root、别息屏 |

鱼游把系统难控转成「把环境配成脚本能跑」。CloudCtl 把同一类难控收进产品门禁，所以单点成功率看起来更低。

---

## 1. 无障碍树 / Flutter 定位

**我们踩过的：** 闲鱼 Flutter 列表常无稳定 viewId；字在 `contentDescription`；整列表 wrapper 包住所有卡片，点中心=点错卡（误下架「爆笑漫画成语」）；横幅一天漂 546px；uiautomator 树 ≠ accessibility 树。

**他们怎么做：**

- 主力 Auto.js 选择器：`desc()` 63、`text()` 29、`clickable` 23、`className` 12、`id()` 8。Flutter Semantics / `viewIdResourceName` 在业务脚本里基本没有。`fishflutterboost` 只出现在鱼币 H5 URL，不是定位器。
- 商品身份 = 标题。明文：「系统根据宝贝标题判断宝贝的唯一性，请勿有标题相同的宝贝」。无 `platformItemId`。
- 列表仍用「编辑宝贝列表第 N 个宝贝」「次翻动宝贝列表」——可见顺序，不是每件独立身份。
- 找不到：切瀑布流 → 翻列表 → 重载。没有「旧坐标任务作废」。
- 小红书草稿挡导航：文案「确定要退出发布吗？」+ 存草稿，点掉即走，不是 `NAV_RESET_FAILED`。

### 1.1 第二轮钉死：落点不是卡片中心

降价循环（解码后）：

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
| wrapper 整列矩形 / bounds | 没有 `bounds()`、center、overlap |
| 点「删除」按钮 | 降价不点删除。删除另走 `find(text('更多'))[0]` → `text('删除').click()` → `text('确定').click()` |

同一屏两个「降价」靠得近时，`parent()` 仍可能糊到相邻行。他们完成文案自己承认：成功数小于总数可能因为标题相同、无降价按钮、特殊宝贝。

删除/下架更粗：先按想要/标题收集，再 `find(text('更多'))[0]`——**可见第一张「更多」**，不是 `platformItemId`。保护文案 `'在保护时间内，无法删除'`。点完不回扫、不看角标、不比截图。

### 1.2 切瀑布流（第二轮解开活路径）

上次「未见」是混淆没解开。活路径：

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
- `FzrFz = "领取奖励"` 是死分支（`if (jqzqn !== jqzqn)`），不要被误导。

---

## 2. 点击 / 手势

**我们踩过的：** Flutter 常不理 `ACTION_CLICK` / `ACTION_SCROLL_FORWARD`；满幅上滑过头；ColorOS 底栏吞点击（2400−2249）；`dispatchGesture` completed ≠ 业务成功。

**他们怎么做：**

1. SDK&lt;7：root `input tap x y`
2. 否则 Auto.js `click(x,y)`
3. 失败 `press(x,y,10)` 再 `press(x,y,1)`
4. 三次失败：「手机操作系统异常，请尝试重启手机或更换手机」
5. 另有节点 `.click()`、坐标点发送、「desc卖闲置不存在，启用备用方法点击」

底部手势条不躲。确认键策略是「未出现确认按钮，准备重新点击」——正是我们禁止的二击。成功不跟列表消失/角标/截图哈希解耦。

---

## 3. 输入 / IME

**我们踩过的：** 闲鱼 `SET_TEXT` 重绘即丢；描述前 16 字相同会误报旧草稿；价格是自定义九键；聊天走剪贴板会发出脏数据；自有 IME 才打穿，且 Flutter 约每秒重建 InputConnection；Android 14 读 `ENABLED_INPUT_METHODS` 会崩并连带关掉无障碍。

**他们怎么做：** 无自有 IME。闲鱼 ≥7.14.50 硬依赖搜狗/讯飞。

| 场景 | 做法 |
|---|---|
| 能 `setText` 的框 | 直接 `setText` |
| 不稳 | `setClip` + paste / 点「粘贴」 |
| 闲鱼 ≥7.14.50 | 必须点输入法剪贴板气泡的校准坐标 |
| 校准 | 「绑定闲鱼」任务记下 x/y |
| 来喜输入法 | 已知会坏 |
| 聊天 | 「想跟TA…」+ 坐标点发送 |

不校验「提交后重绘仍在」。价格是否走九键：答卷未见明文，不能当成他们点了数字键盘。换输入法皮肤/导航条/横幅后，校对坐标作废。

---

## 4. 无障碍掉线 / 重绑 / 保活

**我们踩过的：** ColorOS 上 `force-stop` Companion 会关无障碍；`enabled` ≠ `active`；负载下服务 rebind ~1s；Doze 会杀同步；claim 后断连的释放协议尚未现网联调。

**他们怎么做：**

- 发现：轮询 `auto.service`，队列显示「等待无障碍开启中」。
- 有 Root：`init.js` 写 `Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES` + `ACCESSIBILITY_ENABLED=1`。生产 CloudCtl 不做这个。
- 无 Root：跳设置让人手开；Shizuku 当特权备选。
- 保活：忽略电池优化、`keepScreenOn(24h)`、前台服务、悬浮窗。息屏会断总控，策略是不让息，不是 Doze 下还能跑。
- rebind 不当瞬态。确认键准备再点。
- OPPO/VIVO/小米 Android 13/14：Activity 拉起闲鱼/鱼币页会失败，补丁是「后台弹出界面 / 悬浮窗」，让用户自己搜机型教程。

第二轮补钉：

- **没有 OnePlus / ColorOS / 一加 分支。** 品牌只出现 oppo、vivo、小米、魅族。`ENABLED_INPUT_METHODS` SecurityException、ColorOS 关无障碍，脚本无特判。
- 有 Root：写 `Settings.Secure` 立刻生效，toast 延迟 1000ms；另有「授予root后请重启」。
- 无 Root：拉系统无障碍设置。**没有 1s 心跳、没有 autoService 重绑监听用于恢复。** 开关校验失败只 toast「请先开启无障碍」——下次点任务按钮才再卡。恢复时间完全取决于用户何时回到设置页。
- 会 `am force-stop com.taobao.idlefish`（杀闲鱼），**不杀自己**。没有 ColorOS 把无障碍一起掐掉之后的自救。

执行中途无障碍重绑 1 秒：脚本无 `onUnbind`/`onRebind`、无确认键去抖、无点击幂等 token。删除确认是线性连点：

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

## 5. 窗口 / 焦点 / 前台

**我们踩过的：** 闲鱼在前台时 Companion 要等自己成为活动窗口；已在里页时普通 launch 空操作；确认框必须绑当前 `windowId`；值班曾在 RUNNING 时重启闲鱼导致误发；键盘起来后底栏坐标作废。

**他们怎么做：** `back()` 循环直到 `text('消息')`；草稿点「确定要退出发布吗？」；确认框全局 `text/desc('确定')`；消息监听线程与任务并行，防干扰只看 `currentPackage` 是不是闲鱼/转转，**不给执行任务让路**；聊天发送已在用坐标，键盘弹出后会漂。投屏只是 MediaProjection 截图给 OpenCV/日志，不是远控。

---

## 6. 确认弹窗 / 破坏性动作（对挂起删除最要紧）

挂起文档三次尝试：① 确认击发出但效果不可证；② 滚动后点错卡被单发拦住；③ 目标卡完全可见仍 `CARD_BOUNDS_UNVERIFIED`。全程零误删。

**他们怎么做：** 不解耦，无 UNKNOWN。

- 降价：可见「降价」→ `parent().click()` → 等「现价」→ `setText` → 「确定降价」。点前抠标题去重，点后不回扫。
- 删除：`find(text('更多'))[0]` → `text('删除')` → `text('确定')`，各 sleep 1–1.3s。可见第一张「更多」，不是目标卡片上的那一个。
- 保护文案 `'在保护时间内，无法删除'`（时长是否写死第二轮未钉）。
- 成功 = 文案或直接进入下一件。点了确定商品还在 = **静默当成功**。
- 误删防护：标题唯一（用户承诺）+ 瀑布流降低叠层 + 保护期放弃。点前有标题去重，**不是**点前再读「这张卡现在是不是目标」的 bounds 校验。

对挂起删除的含义：同类「按钮锚点 + parent 热区」能躲开卡片中心误点，但解决不了 `CARD_BOUNDS_UNVERIFIED`，也没有 platformItemId。可以研究「点降价/更多/管理，不要点卡片中心」作为布局策略；不能把「可见第一张更多 + 点完当成功」搬过来。

---

## 7. 任务生命周期

**我们踩过的：** 服务端 cancel 后本地 `PAUSED`/`WAITING_USER` 占队头，新任务领不走。这是更严谨状态机才有的坑。

**他们怎么做：** WebSocket `web_to_aj_command` 可删任务、清空队列、强制结束、`restart_aj`。本地 JS 数组队列。无 CLAIMED/lease/WAITING_USER。发布确认由脚本自己点确定，人等不是一等公民。息屏断线则取消丢失。旧草稿靠回首页 + 点退出发布。

---

## 8. 媒体 / 通知 / 边角

- **相册故意跳过第 0 格。** 等 `desc('所有图片和视频')`/`所有文件` 最多 10×1s，然后同 depth 的 clickable `ImageView` 用 `indexInParent(1)` 点第一张图。`indexInParent(0)` 当快门，纯下标，不识别快门图标。明文还有「进入相册」「双击选择当前图片」「宝贝图片选择完毕」。
- 闲鱼版本钉死：`7.9.70` 一档兼容；`7.14.50` 主推荐（剪贴板）；`7.18.92` 当前钉。发品图数量对不上就让换 7.18.92。7.18.92 取消会玩帖子首页展示后不再更新该功能。`7.4.10` 只出现在 IME/剪贴板分支（那一档不点「剪贴板」）。没有跟随商店最新版。
- 下载后 `update_MediaStore(path)`，尾斜杠/MIME 是否规范看不清。
- 消息是进闲鱼消息列表扫未读，无 notification channel 白名单，营销 Feed 可能当买家。
- 小米双开不支持总控回复；分身要用户先点开一个闲鱼。
- 无 scrcpy 远控。

---

## 12 问对照（可直接贴）

1. **列表点第 N 个还是按标题/ID？** 标题当唯一键。降价落点是「降价」`parent().click()`；删除是可见第一张「更多」。无 viewId，无 `platformItemId`。
2. **点击节点 Action 还是手势？底栏？** 节点 `.click()` + `click(x,y)` + press + root input tap。底栏不躲。三次降级重试。
3. **描述/聊天 SET_TEXT 吗？换输入法吗？** 先 setText，不行剪贴板。闲鱼钉 7.14.50 / 7.18.92，强制搜狗/讯飞。无自有 IME。
4. **如何证明输入重绘后还在？** 不证明。
5. **无障碍被关 / force-stop 后要不要人开？** 有 Root 写回 Secure；无 Root toast 等人，无自愈轮询。force-stop 只杀闲鱼不杀自己。无 ColorOS 特判。
6. **执行中 a11y 重绑 1 秒？确认键防二击？** 无处理。确定会连点；点完当成功。
7. **点了确定商品还在？** 静默当成功，继续下一件。无 UNKNOWN。
8. **误删相邻商品？标题二次校验？** 点前标题数组去重；点的是按钮 parent 不是卡片中心。无 bounds 校验。同屏两个「降价」仍可能糊行。
9. **批量是可见第一张还是独立身份？布局漂 500px？** 删除用可见「更多」`[0]`。瀑布流只换布局（顶栏第 6 个 LinearLayout），身份仍是标题。启发式 8 个 LinearLayout 一漂会静默不切。
10. **云端取消后几秒能领新任务？** WS 删本地队列项，间隔未知；息屏窗口取消丢失。
11. **里页 / 草稿弹窗怎么回根？** `back()` + 文案锚点。Activity 拉起在 OPPO/VIVO/小米 13/14 会失败。无 OnePlus 分支。
12. **发品、回消息、值班、投屏能否同时？** 业务串行，监听并行。无远控。无「执行期值班必须停」。

---

## 下一轮还要问

第二轮已钉：wrapper 落点、瀑布流切法、ColorOS 无特判、确认键二击、相册跳过第 0 格、闲鱼钉 7.14.50/7.18.92。下面只留**仍空、且会撞上挂起删除或输入**的。按组复制。

### A′. 删除（挂起文档仍优先）

1. 从列表进**详情页再点管理菜单**（编辑/下架/删除）有没有？我们 v2 走这条，卡在进详情前的卡片点击。降价是 `降价.parent().click()`，删除若只有「可见第一张更多」，进详情这条可能根本没有。
2. 「在保护时间内，无法删除」是 sleep 多重试、跳过并记成功、还是当失败？时长写死多少？
3. 已下架 tab 的删除，锚点还是「更多」，还是改成「删除」按钮？已下架卡片往往没有「降价」。
4. OpenCV 找图在删除/下架里用不用？（第一轮提到 so 里有，业务脚本是否真调）

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

「清除非买家未读」的判定规则（头像、文案关键字、入口）？`libroot_automator.so` 失败时会不会在脚本不知情下再点一次？

---

## 对我们的含义（先别改门禁）

可以研究、不要直接搬：

- **动作锚点用可见按钮（管理/更多/删除）的 parent 热区，不要点卡片几何中心。** 这是第二轮唯一对挂起删除有用的布局启发；仍必须保留标题二次校验和 bounds 仲裁，不能改成「可见第一张更多」。
- 瀑布流作为只读布局预处理（顶栏启发式，失败要可观测，不能静默不切）。切完身份仍按标题/将来的 platformItemId，不改第 N 张。
- 相册选图跳过 `indexInParent(0)`（快门）。我们已有「第 0 格是快门」的知识，应对齐成硬规则。
- 闲鱼版本钉死在已验证档（他们是 7.14.50 / 7.18.92；我们设备当前版本要单独登记，不能盲跟）。
- 保护期「无法删除」当可预期失败，而不是 UNKNOWN 重试。

明确不要搬：

- 确认键连点、Root 写无障碍、标题当唯一 ID、剪贴板坐标当输入主路径、成功=文案或「点完即成功」、监听线程和任务并行、无 Root 时无自愈。

挂起删除的下一步仍以交接文档为准：XML 离线回放匹配器、卡片节点优先于 wrapper、新鲜度参数。可额外试「先解析卡片内管理/删除/更多按钮再点 parent」，而不是点标题中心；真机时一次性授权一批已下架测试商品。

---

## 证据边界

- 鱼游侧：APK 明文中文、明文 API、能还原的函数体。jsjiami v6 未解开的标为未见/未知，不编。第二轮补了降价循环、瀑布流活路径、删除连点、相册 `indexInParent(1)`、版本配置键。
- CloudCtl 侧：OnePlus 9R `b0644fb5` 真机记录与 `mobile/companion` 代码，见挂起文档和 `artifacts/tasks/P09-unknown/`。
- 本问答录不代替执行计划；不把参考产品的通过写成 CloudCtl 验收通过。
