# B05 交付报告：最小闲鱼发布 open-only Recipe（2026-09-16）

执行：W-E/W-E2 子代理（两次死于 API 故障，留下 builtin_recipes.py 半成品）+ W0 主会话审计后续作完成。

## 半成品审计结论（红线）
- 既有 4 个 builtin 条目：probe/collect/xhs 三条 hash 逐字节一致 ✅；xianyu publish-1 的**字节原样**保入 LEGACY_BUILTIN_PACKAGES（hash a2331b80… 与基线一致）✅；仅 commandType→active 映射切到 v2
- v2 图引用 xianyu_publish_button/submit/tapsPublish：**零出现** ✅

## 交付内容
1. **recipe-xianyu-publish-2**（open-only 11 状态图，hash f706ba27…）：wait-home→open-sell→open-publish→await-form→select-media→fill-description(valueRef=listingBody)→confirm-description→await-price→fill-price(valueRef=price)→capture-confirm-point→checkpoint WAITING_USER 终态；**图内无任何提交/发布动作**（真实提交属 Q02 前置保护+逐对象授权）
2. **引擎参数绑定**（RecipeEngine）：新增 valueRef（图字节保持无参数、hash 稳定）；input 动作从 CommandV1.parameters 绑定值，缺 valueRef/空值 → PARAMETER_REQUIRED fail-closed；media 动作展开为冻结 steps 同款序列（tap add_image→等图库 select_0→依次 select_1..N→gallery_next），计数 1..49（tile 生成器 0..49，0 号快门），越界 fail-closed
3. **automation-sdk RecipeState** 补 valueRef 字段（StrictModel extra=forbid 必须显式）
4. **BuiltinRecipes.kt** 增 v2 字面量（与 python canonical 逐字节镜像）；v1 原样保留
5. 测试 PublishRecipeV2Test 6 用例：hash 钉死/open-only 红线/valueRef 绑定/有序选图（快门 tile 0 只作等待后置条件永不点）/空与超限 fail-closed/空参 fail-closed

## 门禁
- Android：62 套件 / 433 测试 / 0 失败（基线 61/427 +6）
- 后端全量：681 passed / 1 skipped 零新失败

## 部署依赖与未决
- **新图生效需 W0 部署首尔**（服务端 builtin 集当前无 v2）+ 新 APK 装机；旧 APK 收到 v2 pin 任务会 fail-closed（正确行为）
- 真机验收未做：待 Q02 前置保护 + 用户逐对象授权（open-only 到确认点也需真机过一遍表单/图库/价格键盘路径）
- 媒体上限勘误：K05 原文 xianyu 50 → 实际可选 49（tile 0..49 含快门），已在 A05 常量/引擎校验统一为 49，K05 附勘误
