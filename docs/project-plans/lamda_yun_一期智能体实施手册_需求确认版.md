# LAMDA-YUN 一期智能体实施手册

> 与《lamda_yun_一期审阅与实施_需求确认版.xlsx》使用同一份数据。Excel用于管理进度，本手册用于向实现智能体逐项下达任务。

审阅日期：2026-09-06。代码基准：`b394475c56a07b0ea660531222d182646e1c7e66`。
审阅边界：公开可见源码静态复核；当前容器尝试 clone 因 DNS 解析失败，未实际运行 Web/Python/Android 构建、后端服务、数据库并发测试或真机。下面是已核查行为、需求差距和待验证风险的分级清单，不是“所有 Bug 已穷尽”的保证。

共有 **63 条审阅记录、120 项实施任务、960 个具体步骤、37 个来源链接**。
记录分类：静态确认 25条；待复现风险 10条；需求差距 22条；待验证约束 4条；复核纠正 2条。

## 交给实现智能体的执行指令

你正在实现既有仓库，不是在另起一个Demo。开始前读取仓库AGENTS.md、README及真实依赖锁文件，并核对commit。
按T编号与依赖执行，每次认领一个任务或一组不冲突的任务。先阅读该任务列出的源码和关联B问题，再执行8个步骤，补自动化测试，最后填写提交SHA、测试命令、退出码和证据。
生产数据以真实后端为准；不能用localStorage、mock、固定成功状态、假设备遥测或“点击了按钮”冒充业务完成。
任务状态只在Excel维护列修改；代码完成应标待联调或待真机，不能直接标已完成。真机证据至少包含deviceId、真实机型/SDK、平台App版本、recipeHash、taskId、事件和截图。
不具备运行环境时如实记录阻塞，保留已实现代码和复现命令。平台不提供的入口或字段标NOT_SUPPORTED/null+reason，不猜测、不伪造，也不悄悄删需求。
复用现有租户、账号、DeviceLease、PublishPlan/提交账本、MediaAsset/派生、AutomationVersion签名与Temporal。新旧路径不能各自占用一套不互通的设备写锁。
未知页面、登录验证、人机验证和条款变化暂停等人工，不绕过授权。人工接管前安全停止；交还后检查页面/账号/版本/检查点，继续原taskId。
所有发布/删除/评价/推广消耗在最终确认前有ActionJournal；结果未知先核对，禁止从头盲目重发。不要宣称第三方UI严格exactly-once。
Recipe新版本由用户在后台点发布才生效；生成代码的智能体无权自动对设备激活。运行或暂停任务固定原版本。
不扩展转转、抖音、采购、自动客服、计费或二期多客户UI。设备物理摆放不作为额外需求讨论。

### 完成回报模板

```text
TaskID:
修改文件:
提交SHA:
数据库迁移/回滚:
测试命令及退出码:
真机型号/SDK/App版本/Recipe版本:
测试taskId与证据路径:
已满足验收:
未满足项/阻塞及原因:
Excel状态: 待联调 / 待真机 / 待验收 / 已完成 / 阻塞
```

## 1. 已确认需求

### R01 · 规模 · 一期至少10台，面向百台扩展
区分在线数、运行任务数和同时观看数；百台在线不等于百路高码率视频。

依据：用户已确认。

### R02 · 连接 · SIM移动网络连接
APK主动连接公网云端；手机和电脑不需同局域网。生产执行不依赖USB、ADB常驻或Edge Gateway。

依据：用户已确认。

### R03 · 视频 · 流畅实时视频是一期必做
画面流畅优先，不追求最高分辨率；截图轮询仅作诊断/降级，不能作为实时投屏验收。

依据：用户已确认。

### R04 · 远控 · 观看不中断，写操作先接管
点击、滑动、长按、文字输入、返回/Home/多任务；观看任务不占写锁，接管先暂停自动化。

依据：用户已确认。

### R05 · 恢复 · 人工处理后继续原任务
未知页面保留现场并暂停；交回控制权后校验页面与检查点，再继续原taskId。取消和暂停必须分开。

依据：用户已确认。

### R06 · 兼容 · 红米Note9作为最低兼容基线，当前调试机是 OnePlus 9R
不猜Android版本。APK自动上报SDK/ROM/目标App版本；用户不用手填。手机常亮，允许无障碍、投屏授权和前台服务。
红米 Note 9 仍是一期最低兼容目标（最差机型），但当前联调真机是 OnePlus 9R `LE2100` / Android 14 / SDK 34。验收证据必须写真实机型，不能把 9R 结果写成 Note 9 已通过。

依据：用户已确认最低机型；2026-09-07 用户确认当前调试机为 OnePlus 9R。

### R07 · 解耦 · 云端负责做什么，APK负责怎么做
云端负责内容、素材、业务快照、队列、定时、指令、状态；手机本地负责识别、动作、分支、采集和恢复。

依据：用户已确认。

### R08 · 更新 · APK整体升级+Recipe独立更新
新版本生成并测试后，由用户在后台点击发布；未发布不可生效。运行中任务固定原版本。

依据：用户已确认。

### R09 · 队列 · 立即/预约/周期；每设备串行FIFO
闲鱼与小红书共享同台设备写队列；不做优先级。多设备操作生成独立任务，不新增父任务状态。

依据：用户已确认。

### R10 · 账号 · 每设备1闲鱼+1小红书，可解绑换绑
两平台各自绑定。历史订单、发布实例、任务和统计归原账号；换绑不迁移历史。云端待发布内容库可复用。

依据：用户已确认。

### R11 · 异常 · 已知弹窗处理，未知暂停等人工
登录失效、人机验证、风控及未知页面暂停并提供接管入口；不自动绕过平台或系统的验证/授权。

依据：用户已确认。

### R12 · 文件 · 图片/视频上传、下发与使用
素材必须云端持久化并下载到手机供发布；支持文件推送、截图保存和复制粘贴。剪贴板按系统授权边界实现。

依据：用户已确认。

### R13 · 保留 · 长期保存，可由用户删除
原素材、内容、订单、指标快照、任务和证据不默认到期删除；删除需引用检查及审计。直播画面不默认全程录像。

依据：前句已确认；直播不录像为设计默认。

### R14 · 订单 · 默认全部，可指定N个
默认扫描当前授权账号可正常访问的全部订单；指定N按稳定顺序取N个去重订单。字段尽量完整；不可访问字段为null并说明原因。

依据：用户已确认。

### R15 · 采集 · 宝贝信息尽量完整，保留历史
区分未采到/无权限/平台不显示与真实0；每次采集追加快照，而非覆盖过去数据。

依据：范围已确认；历史模型为设计。

### R16 · 闲鱼 · 授权任务全范围
签到鱼币、抵扣、推广、好评均纳入；云端发明确指令参数，APK执行。涉及消耗/删除设确认和防重。

依据：用户已确认。

### R17 · 小红书 · 只做发布笔记，不多开
图片/视频、正文、标题、标签及现有发布模式接通；不要求用户手填App版本。不可承诺未知版本全部兼容。

依据：用户已确认。

### R18 · 部署 · 一期个人，二期多客户
保留tenant_id、鉴权和审计，不在一期新增客户注册、计费和复杂组织管理。

依据：用户已确认。

### R19 · 产品 · 产品编辑六类+商品管理三类
普通宝贝、水印、通用地址池、设备地址池、描述池、标签池；商品列表、导入、分组。

依据：用户已确认。

### R20 · 范围 · 不加入未要求的二期业务
不扩到转转、抖音、公众号、采购、自动客服等。旧入口不应伪装为一期可用；真实缺口列出证据。

依据：按原始范围约束。


## 2. 设计默认与真实平台限制

### D01 · 技术分层
保留模块化Control API及既有Temporal/租约/发布账本；本地签名声明式状态图+Kotlin原语。

边界：用户确认云端/手机解耦；具体状态图技术为本稿设计。

### D02 · 视频起点
MediaProjection+WebRTC+TURN；建议默认720p约20fps、自适应15–30fps，以流畅为先。

边界：数值不是用户硬指标；正式验收必须写明网络条件和测量口径。

### D03 · 远控承载
WebRTC DataChannel有序操作+epoch/seq/ttl；HTTPS用于业务和素材，WSS用于信令。

边界：不把可靠传输等同可重放点击；重连丢弃过期操作。

### D04 · 账号安全
云端不保存平台密码；设备本地登录态和绑定版本约束任务。

边界：账号身份不可只凭昵称合并；不绕过验证码。

### D05 · 资源池选择
设备地址池优先、通用池fallback；随机/轮询可配置；实际选中值冻结。

边界：用户未指定算法，故为可配置默认。

### D06 · 订单范围
数量为空取当前授权账号可见全部；角色默认ALL_VISIBLE，可筛买入/卖出。

边界：不承诺平台未显示历史；任何截止条件要说明complete/stopReason。

### D07 · 定时补发
支持即时/单次/周期；时区显式存储，补发策略SKIP/QUEUE_ONE等必须在schema列明。

边界：具体补发默认建议QUEUE_ONE，避免离线后补发大量周期实例；用户可配置。

### D08 · 保存边界
业务素材/订单/历史/证据长期保留，可手动删；直播不默认持续录像。

边界：本机任务相册和临时上传可清理，不等于删除云端原件。

### D09 · 系统权限
无Root/Device Owner作为默认前提；录屏重新授权、安装确认、剪贴板限制准确上报。

边界：不能由普通APK承诺静默安装、任意杀进程、后台无限读剪贴板。

### D10 · 旧帖子入口
闲鱼发布/删除帖子先真机核查可用性，存在则实现，不存在出证据并保留阻塞。

边界：用户未确认排除；旧repo retired字样不是当前平台能力的证明。

### D11 · 队列/租约参数
队头未就绪或暂停阻塞后项；设计初值租约60秒/15秒续租；发布定时过期窗口可配置。

边界：参数以真机弱网压测调整；不引入优先级，不自动堆积补发所有错过周期。

系统约束参考：
- S32：https://developer.android.com/media/grow/media-projection
- S33：https://developer.android.com/about/versions/10/privacy/changes#clipboard-data
- S34：https://developer.android.com/reference/android/content/pm/PackageInstaller.SessionParams#setRequireUserAction(int)
- S35：https://webrtc.org/getting-started/turn-server
- S37：https://developer.android.com/develop/background-work/services/fgs/service-types

## 3. 架构与核心状态

### A01 · 控制面
Web→Control API：产品/帖子/资源池/订单/指标、账户和设备、任务/定时、版本发布、证据查询。

约束：复用现有tenant/authz/MediaAsset/PublishPlan/AutomationVersion等实体，不造双重事实。

### A02 · 执行面
APK→云端主动连接，领取高层Command，下载指定已发布Recipe与素材，使用本地状态机执行。

约束：Recipe本地包含分支/循环/抽取/恢复，云端不逐点击编排；限制循环与执行时长。

### A03 · 视频面
Android MediaProjection→WebRTC视频→浏览器；TURN穿越不可直连网络。

约束：信令鉴权，媒体不入关系数据库；多观看者共享只读语义，写权单独控制。

### A04 · 单写锁
每设备一个统一writer：AUTO或REMOTE；同台闲鱼/小红书任务共享FIFO。

约束：租约/fencing epoch贯穿任务、远控、重连和撤销；只读视频不占写锁。

### A05 · 任务状态
QUEUED→WAITING_MATERIALS/PREFLIGHT→RUNNING→SUCCEEDED；可经PAUSE_REQUESTED→PAUSED_WAITING_USER→RESUME_CHECK回RUNNING。

约束：提交不确定进入RECONCILING；FAILED与CANCELLED独立终态；取消不能再“继续原任务”。

### A06 · 恢复与防重
检查点存step/page/context/item cursor/recipeHash/snapshotHash/bindingVersion；最终副作用前写ActionJournal。

约束：INTENT无明确结果=UNKNOWN，核对后再决定，不宣称第三方UI exactly-once。

### A07 · 媒体快照
MediaAsset上传完成→水印派生就绪→快照冻结→MediaDelivery绑定设备任务→APK流式校验下载→确定性选相册。

约束：不持久化blob/data URL，不用图库第N项代替asset身份。

### A08 · 版本机制
Recipe草稿→静态校验/fixture/真机认证→用户手动发布→手机下载校验→空闲激活。

约束：运行/暂停任务固定旧版本；撤回阻止新选取，不破坏旧任务恢复；APK整包另走系统安装。

### A09 · 数据隔离
tenant贯穿现有实体；设备绑定按平台唯一；历史发布实例/订单/任务/指标归account。

约束：可复用的创作素材库与已经发布的账号实例分开；换设备或换绑不篡改历史归属。

### A10 · 默认完整采集
订单/指标只采当前授权账号正常可见字段；结构化批次幂等入库。

约束：null+reason区别缺失与0，complete/stopReason区别完整扫描与部分完成，rawText保留解析精度。

### 统一任务状态和控制权
业务任务状态：QUEUED、WAITING_MATERIALS、PREFLIGHT、RUNNING、PAUSE_REQUESTED、PAUSED_WAITING_USER、RESUME_CHECK、RECONCILING、CANCEL_REQUESTED，以及SUCCEEDED/FAILED/CANCELLED/EXPIRED终态。
设备写控制模式单独存储：NONE/AUTO/REMOTE。观看视频不占写控制权，REMOTE不是业务任务成功或失败状态。
暂停保护原队列头和现场，后续FIFO任务不得越过。取消与暂停分开；取消后不允许继续原任务。结果未知必须核对，不可用重试按钮直接绕过。


## 4. 待实现的协议示例
这些是设计示例，非当前仓库已存在接口。占位符必须替换；落地时先提交JSON Schema与TS/Python/Kotlin一致性测试。

### 高层指令示例
```json
{
  "protocolVersion": 1,
  "taskId": "task_example_001",
  "attemptId": "attempt_01",
  "commandType": "xianyu.publish_goods",
  "deviceId": "device_example",
  "accountId": "account_example",
  "bindingVersion": 3,
  "recipe": {
    "versionId": "recipe_20260906_01",
    "sha256": "<SHA256>",
    "engineMinVersion": 1
  },
  "snapshot": {
    "id": "snapshot_example",
    "sha256": "<SHA256>"
  },
  "params": {
    "mode": "DIRECT",
    "productRevisionId": "product_revision_example"
  },
  "mediaDeliveryId": "delivery_example",
  "lease": {
    "controlEpoch": 42,
    "expiresAt": "<RFC3339>"
  },
  "targetPackage": "<从设备探测与已发布Recipe取得实际包名>",
  "requiredCapabilities": [
    "accessibility",
    "gesture",
    "media_download"
  ]
}
```

### 恢复检查点示例
```json
{
  "taskId": "task_example_001",
  "attemptId": "attempt_01",
  "checkpointRevision": 8,
  "stateId": "FORM_READY",
  "stepId": "verify_price",
  "pageState": "XIANYU_EDITOR",
  "snapshotHash": "<SHA256>",
  "recipeHash": "<SHA256>",
  "accountId": "account_example",
  "bindingVersion": 3,
  "currentItemId": "listing_example",
  "variables": {
    "completedItemIds": [],
    "selectedMediaCount": 3
  },
  "pendingAction": {
    "key": "task_example_001:listing_example:publish",
    "status": "INTENT"
  }
}
```

### 人工控制示例
```json
{
  "sessionId": "remote_example",
  "controlEpoch": 43,
  "seq": 18,
  "ttlMs": 1500,
  "viewportVersion": 7,
  "action": "tap",
  "args": {
    "x": 0.52,
    "y": 0.75
  }
}
```

### 订单同步结果示例
```json
{
  "resultType": "xianyu.order_sync.summary",
  "schemaVersion": 1,
  "data": {
    "requestedLimit": null,
    "uniqueCount": 127,
    "complete": false,
    "stopReason": "PAUSED_FOR_LOGIN",
    "lastAckedBatchSeq": 6
  },
  "artifactRefs": [
    "evidence_example"
  ]
}
```


## 5. 一期功能覆盖

- SC01 设备列表 / 实时视频 / 远控 → **T038**；SIM公网观看、接管和继续原任务。
- SC02 普通宝贝编辑 → **T061**；完整字段与素材持久化。
- SC03 宝贝水印 → **T053**；模板/派生/发布素材链路。
- SC04 通用 / 设备地址池 → **T055**；真实CRUD、绑定、快照选用。
- SC05 宝贝描述池 / 标签池 → **T056**；描述任务 + T057 标签任务。
- SC06 商品列表 / 分组 → **T062**；分组另见 T060。
- SC07 商品导入 → **T065**；预检、幂等、媒体与错误清单。
- SC08 帖子编辑与管理 → **T068**；列表/分组/删除另见 T069。
- SC09 小红书发布笔记 → **T076**；两入口共用、图文和视频。
- SC10 闲鱼订单同步 → **T108**；默认全部 / 指定N / 字段可用性。
- SC11 宝贝信息采集 → **T112**；完整可见数据与历史快照。
- SC12 闲鱼授权任务全目录 → **T104**；下方31项逐一覆盖。

### 闲鱼31项目录

- xy-tasks-01 发布商品 → **T081**；真实发布命令。
- xy-tasks-02 发布帖子 → **T102**；先核查入口，存在则实现。
- xy-tasks-03 擦亮商品 → **T082**；真实命令。
- xy-tasks-04 上架商品 → **T083**；真实命令。
- xy-tasks-05 下架商品 → **T084**；真实命令。
- xy-tasks-06 删除商品 → **T085**；真实命令/确认防重。
- xy-tasks-07 删除帖子 → **T102**；先核查入口，存在则实现。
- xy-tasks-08 绑定闲鱼 → **T086**；账号探测与绑定。
- xy-tasks-09 签到鱼币 → **T087**；纳入一期。
- xy-tasks-10 鱼币抵扣 → **T088**；纳入一期。
- xy-tasks-11 鱼币推广 → **T089**；纳入一期/预算防重。
- xy-tasks-12 一键小刀 → **T090**；不同于降价。
- xy-tasks-13 一键降价 → **T091**；冻结新价，重试不二次降。
- xy-tasks-14 一键好评 → **T092**；真实交易评价/防重。
- xy-tasks-15 重启闲鱼 → **T093**；标准权限可用路径。
- xy-tasks-16 删除动态 → **T094**；真实命令。
- xy-tasks-17 删除消息 → **T095**；删除与点红点分支。
- xy-tasks-18 删除留言 → **T096**；真实命令。
- xy-tasks-19 草稿上架 → **T097**；提交防重。
- xy-tasks-20 编辑重发 → **T098**；修改字段可追溯。
- xy-tasks-21 托管无忧卖 → **T099**；资格/条款变化暂停。
- xy-tasks-22 快速编辑重发 → **T100**；逐项账本。
- xy-tasks-23 快速下架商品 → **T101**；批量结果核验。
- xy-tasks-24 采集宝贝信息 → **T112**；共享统计服务。
- xy-tasks-25 通用地址池 → **T055**；共享资源池。
- xy-tasks-26 设备地址池 → **T055**；共享绑定与选择。
- xy-tasks-27 描述池 → **T056**；共享资源池。
- xy-tasks-28 标签池 → **T057**；共享资源池。
- xy-tasks-29 图片水印 → **T053**；共享派生素材。
- xy-tasks-30 违禁词检测 → **T103**；后端规则服务。
- xy-tasks-31 视频操作教程 → **T104**；静态帮助内容/版本对应。

## 6. 代码审阅记录

### B001 · P0 · 静态确认 · 商品分组写错外键对象

模块：商品/数据库。关联实施：T058, T060。

**源码证据**：services.py batch_update_product_group/import_products 写 content_id=product_id；db.py 的content_id外键指向content_item。

**复现/核查**：在开启FK的数据库建1商品+1内容组；执行批量分组；检查FK异常或错误关联。

**修复指导**：新增ProductGroup/ProductGroupMembership，FK指向product；迁移旧groupName与可识别脏数据；禁止复用帖子membership。

**验收**：Postgres/SQLite FK开启均成功；分组删改不影响帖子；无孤儿行。

来源：S02、S03；完整链接见来源索引。

### B002 · P1 · 静态确认 · 字符串价格用于数值范围筛选

模块：商品/价格。关联实施：T058, T059。

**源码证据**：ProductRow.price=String；filter_products直接price >= min_price / <= max_price。

**复现/核查**：录入9.9/20/100/1000；查询20至100区间；核对结果。

**修复指导**：迁移price_cents BIGINT；Decimal转换，保留API兼容输出；范围过滤使用数值且None判断。

**验收**：20至100只返回20和100；0/小数/非法数值边界覆盖。

来源：S03、S02；完整链接见来源索引。

### B003 · P1 · 静态确认 · 批量删除绕过单项引用保护

模块：商品/删除。关联实施：T059。

**源码证据**：archive_product检查活跃PublishPlan；batch_delete_products直接ARCHIVED。

**复现/核查**：建引用商品的活动发布计划；分别单删和批删，比较行为。

**修复指导**：抽取统一归档保护并锁行；批量预检后同事务执行；返回blockedIds。

**验收**：单删批删同规则；任何被引用项导致整批不改；重复归档有明确幂等语义。

来源：S02；完整链接见来源索引。

### B004 · P1 · 静态确认 · 404/501自动转localStorage造成真假数据分裂

模块：Web数据。关联实施：T005。

**源码证据**：product-catalog/post-catalog的isMissingApi触发usingLocal并保存本地。

**复现/核查**：API模式把保存接口改成404；保存后直接查询数据库。

**修复指导**：生产环境失败即报错；仅显式dev mock允许本地；删除会话内隐式降级。

**验收**：生产404不显示成功、不写业务localStorage；切换浏览器数据一致。

来源：S08、S09；完整链接见来源索引。

### B005 · P1 · 静态确认 · 批删失败回退条件反向且可能部分删除

模块：商品/批删。关联实施：T062。

**源码证据**：product-catalog.archive 在非404/501错误时逐个archive；404/501却转本地。

**复现/核查**：批删返回409或500；观察是否仍发N个单删请求。

**修复指导**：禁止在权限/冲突/500后继续副作用请求；只对显式协商的接口兼容版本选路径。

**验收**：409/500后0个单删；批量失败无部分成功假象。

来源：S08；完整链接见来源索引。

### B006 · P1 · 静态确认 · 复制商品丢失媒体资产关联

模块：商品/复制。关联实施：T062。

**源码证据**：product-catalog.duplicate固定mediaAssetIds:[]。

**复现/核查**：复制有两图商品；比较新商品mediaAssetIds。

**修复指导**：复用已完成资产ID和顺序，不复制blob；明确封面与引用计数。

**验收**：复制后原件/副本都可预览发布，删除一方不误删共享媒体。

来源：S08；完整链接见来源索引。

### B007 · P1 · 静态确认 · 新媒体没有进入MediaAsset链路

模块：商品/媒体。关联实施：T044, T061。

**源码证据**：ProductEditView 新图进attributes.images，视频为blob URL；save保留旧mediaAssetIds。

**复现/核查**：上传新图片/视频保存后刷新，检查服务端媒体关联与手机manifest。

**修复指导**：统一上传create/upload/complete；存assetId；草稿预览URL与业务引用分离。

**验收**：刷新与换电脑可见，APK下载hash一致，payload无data/blob URL。

来源：S10；完整链接见来源索引。

### B008 · P1 · 静态确认 · 分组名和商品类别混用

模块：商品/字段。关联实施：T058, T061。

**源码证据**：ProductEditView.applyProduct用category补groupName；save用groupName写category。

**复现/核查**：改分组保存；检查category是否被覆盖。

**修复指导**：独立category与groupId；迁移需报告不确定记录，不能盲目改全部category。

**验收**：分组重命名不改变类别；筛选类别和分组相互独立。

来源：S10、S19；完整链接见来源索引。

### B009 · P1 · 待复现风险 · 编辑页切到新建可能沿用旧current.id

模块：商品/路由。关联实施：T061。

**源码证据**：loadProduct无id时resetForm未清current；save优先current.value.id。

**复现/核查**：同组件路由先?id=A，再去无id新建；保存，检查是否覆盖A。

**修复指导**：新建分支清current/id/SPU；异步加载加request epoch，旧响应不覆盖新路由。

**验收**：从编辑转新建创建B，A不变；快速切A/B不串数据。

来源：S10；完整链接见来源索引。

### B010 · P1 · 静态确认 · 导入逐行保存，失败会部分写入

模块：商品/导入。关联实施：T063, T064, T065。

**源码证据**：ProductImportView.importRows循环await catalog.save；无批次事务或结果账。

**复现/核查**：100行第50行注入错误；重试并观察重复与已写入行。

**修复指导**：改预检+批次提交+幂等导入；每行错误带rowNo；已提交批次重复返回原结果。

**验收**：错误行可定位；重试不重复；UI准确展示已写入/失败数量。

来源：S11；完整链接见来源索引。

### B011 · P1 · 静态确认 · 分组CRUD仍是浏览器本地事实

模块：商品/分组。关联实施：T060。

**源码证据**：data/product-groups.ts 使用本地持久化；ProductImportView调用createProductGroup。

**复现/核查**：浏览器A建组，浏览器B同账号查询。

**修复指导**：ProductGroup API为唯一真相；一次性导入旧数据，不长期双写。

**验收**：跨浏览器一致；API失败不能本地伪成功。

来源：S19、S11；完整链接见来源索引。

### B012 · P1 · 静态确认 · API模式的删除只写localStorage

模块：帖子/删除。关联实施：T067, T069。

**源码证据**：post-catalog.remove没有archive请求，只list/filter/saveLocal。

**复现/核查**：删除帖子后直接GET内容API并刷新页面。

**修复指导**：复用archive_content API，后端成功再刷新query；批量定义原子性。

**验收**：刷新不复活，另一个浏览器看不到已归档项。

来源：S09、S02；完整链接见来源索引。

### B013 · P1 · 静态确认 · 新增revision未同步列表使用的title

模块：帖子/标题。关联实施：T067。

**源码证据**：post-catalog保存已有帖只createRevision(payload)；add_revision未更新ContentItem.title。

**复现/核查**：改标题A为B；比较保存后列表、详情和revision。

**修复指导**：标题写入revision并同事务维护列表摘要字段；加expectedRevision。

**验收**：三处标题一致；并发编辑后写方获409。

来源：S09、S02；完整链接见来源索引。

### B014 · P2 · 静态确认 · 帖子列表额外N次HTTP请求

模块：帖子/性能。关联实施：T067, T069。

**源码证据**：post-catalog.list先contents再Promise.all每项content。

**复现/核查**：100帖子加载抓网络请求数。

**修复指导**：分页API直接给最新revision摘要、封面与分组；删除逐条GET。

**验收**：单页HTTP请求常数级，分页边界正确。

来源：S09；完整链接见来源索引。

### B015 · P1 · 静态确认 · 帖子图片/视频只存浏览器表示

模块：帖子/媒体。关联实施：T044, T068。

**源码证据**：PostEditorView图片compressImageFile，视频URL.createObjectURL。

**复现/核查**：保存有视频笔记后换浏览器，创建手机发布任务。

**修复指导**：复用MediaAsset上传，revision保存媒体顺序/封面/类型。

**验收**：帖子素材跨端可用，任务使用固定asset版本。

来源：S12；完整链接见来源索引。

### B016 · P2 · 静态确认 · 商品列表全量读取且逐商品查媒体

模块：商品/性能。关联实施：T059, T062。

**源码证据**：services.py list_products/filter_products对每个商品查询ProductMedia，未提供分页结果。

**复现/核查**：1000商品执行列表；记录SQL计数与返回条数。

**修复指导**：增加稳定排序分页和批量媒体join；限制pageSize；Web不取全量再分页。

**验收**：1页<=100条；SQL次数不随页内商品数线性增长。

来源：S02；完整链接见来源索引。

### B017 · P1 · 需求差距 · 小红书发布页面只保存本地计划

模块：小红书/发布。关联实施：T071, T076。

**源码证据**：PostPublishView.createTask没有API创建任务，提示不下发手机。

**复现/核查**：点击创建，查看Network和服务端任务列表。

**修复指导**：统一xhs.publish_note命令、快照、媒体delivery和真实任务状态。

**验收**：网页→手机→发布结果/证据闭环，刷新保持历史。

来源：S13；完整链接见来源索引。

### B018 · P1 · 需求差距 · 发布商品页面没有下发真实任务

模块：闲鱼/发布。关联实施：T078, T081。

**源码证据**：XianyuPublishGoodsView.createTask调用save/record并明确不会下发。

**复现/核查**：创建发布任务，确认服务端无对应任务。

**修复指导**：改统一任务API；前端仅传业务参数，不生成UI步骤。

**验收**：后台存在独立taskId，APK收到正确商品快照。

来源：S14；完整链接见来源索引。

### B019 · P1 · 需求差距 · 擦亮/上下架/删除/绑定仍为本地任务

模块：闲鱼/基础任务。关联实施：T077。

**源码证据**：XianyuSimpleTaskView.createTask只saveSimpleConfig/recordSimpleTask。

**复现/核查**：创建擦亮任务，检查服务端与手机。

**修复指导**：逐operation映射强类型命令并接真实任务页。

**验收**：每类有API、APK recipe与真机证据，不靠toast验收。

来源：S15；完整链接见来源索引。

### B020 · P1 · 需求差距 · 鱼币、评价、重发等只记录本地配置

模块：闲鱼/扩展任务。关联实施：T077。

**源码证据**：XianyuExtraTaskView.createTask只saveExtraConfig/recordExtraTask。

**复现/核查**：创建每种extra kind并观察无真实任务。

**修复指导**：15类逐项接通；保留字段语义；不要把一键小刀误写成一键降价。

**验收**：所有kind有schema映射和独立验收，风险操作防重。

来源：S16、S17；完整链接见来源索引。

### B021 · P1 · 需求差距 · 后端目标包allowlist不含小红书

模块：小红书/后端。关联实施：T009, T012。

**源码证据**：mobile_service._insert_task只允许Companion和闲鱼。

**复现/核查**：尝试创建小红书目标任务，观察拒绝。

**修复指导**：扩展TargetAppRegistry且任务创建按设备上报版本/能力校验。

**验收**：支持小红书可下发；未知包仍拒绝。

来源：S04；完整链接见来源索引。

### B022 · P1 · 需求差距 · APK本地allowlist及locator也不含小红书

模块：小红书/APK。关联实施：T009, T020。

**源码证据**：CloudCtlAccessibilityService.ensureReady和TargetLocatorRegistry只支持两个包。

**复现/核查**：传小红书目标给本地执行器。

**修复指导**：注册已签名平台定义与locator集；保留本地授权限制。

**验收**：正确包通过，篡改包或未发布recipe拒绝。

来源：S28、S29；完整链接见来源索引。

### B023 · P1 · 需求差距 · 定位器没有目标App版本维度

模块：平台兼容。关联实施：T009, T039。

**源码证据**：TargetLocatorRegistry按package分支，闲鱼大量固定contentDescription。

**复现/核查**：对两个App版本运行locator探测并比较。

**修复指导**：APK自动上报版本；包内兼容范围+页面指纹；未知页面暂停等待适配，不要求用户手填版本。

**验收**：升级后不盲点；兼容失败回报明确原因和证据。

来源：S29、S04；完整链接见来源索引。

### B024 · P1 · 静态确认 · 执行前没有统一拉起目标App

模块：APK/启动。关联实施：T021。

**源码证据**：runNext直接service.execute；ensureReady要求root.packageName==target。

**复现/核查**：手机停桌面时创建闲鱼发布任务。

**修复指导**：增加launch→等待目标包→账号探测→页面归一化；已知权限弹窗单独处理。

**验收**：桌面/其它App起点均能开始，未安装报APP_NOT_INSTALLED。

来源：S25、S28；完整链接见来源索引。

### B025 · P0 · 待复现风险 · 下载素材在执行try与续租之前

模块：APK/素材。关联实施：T016, T047, T021。

**源码证据**：runNext素材校验与deliver位于try之前，sendInitialHeartbeat与周期续租在其后。

**复现/核查**：大视频限速下载超过lease；或下载抛异常；观察本地RUNNING和服务端重领。

**修复指导**：领取后立即续租；下载也受任务状态机与取消控制；异常必须持久化可恢复状态。

**验收**：慢下载不失租；下载失败可重试且不卡死；旧租约不得继续执行UI。

来源：S25、S26；完整链接见来源索引。

### B026 · P1 · 静态确认 · 外层吞掉具体错误码和取消原因

模块：APK/诊断。关联实施：T014, T021。

**源码证据**：runNext catch(Exception)调用finish(false)默认TASK_EXECUTION_FAILED。

**复现/核查**：制造LOCATOR_NOT_FOUND、STEP_TIMEOUT和服务取消。

**修复指导**：分层处理业务异常/取消/未知异常；保留code、step、safeMessage、correlationId。

**验收**：不同错误分别可见；用户暂停不被标普通失败。

来源：S25、S27、S26；完整链接见来源索引。

### B027 · P1 · 静态确认 · 运行中事件仅入本地outbox，主循环执行后才flush

模块：APK/事件。关联实施：T014, T022。

**源码证据**：syncLoop在runNext前flushOutbox；step回调只recordStepEvent。

**复现/核查**：运行长任务并比较手机journal和云端events到达时间。

**修复指导**：独立outbox上传协程，按task/sequence有序重试，不阻塞执行线程。

**验收**：联网时步骤事件及时到云端；断线补传不乱序。

来源：S25、S26；完整链接见来源索引。

### B028 · P1 · 需求差距 · 截图证据未进入云端任务附件闭环

模块：任务/证据。关联实施：T050, T022。

**源码证据**：executor Screenshot仅校验path/hash并log；journal payload仅detailCode。

**复现/核查**：执行screenshot步骤后查看服务端任务证据。

**修复指导**：对象上传+Evidence元数据+事件引用，失败尽力上传最后一帧。

**验收**：Web可读原截图，hash/step/task匹配，越权拒绝。

来源：S27、S25；完整链接见来源索引。

### B029 · P1 · 需求差距 · 后置条件已满足被一律判为失败

模块：APK/恢复。关联实施：T023, T024, T027。

**源码证据**：Tap检测postcondition存在抛POSTCONDITION_ALREADY_MET。

**复现/核查**：暂停在点击后、记录前；恢复相同步骤。

**修复指导**：按动作与检查点做resume guard；核实是本任务已完成后跳过；证据不充分进RECONCILING，不能简单全改成功。

**验收**：既不重复发布/删除，也不把无关页面误认成功。

来源：S27；完整链接见来源索引。

### B030 · P1 · 需求差距 · 进程重启把运行任务标失败

模块：APK/恢复。关联实施：T023, T027。

**源码证据**：AutomationStore.recoverInterruptedRuns写FAILED_RESTART；缺状态变量/循环游标检查点。

**复现/核查**：执行中重启Companion，观察任务终态。

**修复指导**：持久化checkpoint与commit journal，重启后先恢复到暂停/核对，不重放不可逆动作。

**验收**：同taskId可安全恢复；不确定提交等待核对。

来源：S26；完整链接见来源索引。

### B031 · P1 · 需求差距 · 成功result固定空JSON

模块：结果协议。关联实施：T014, T022。

**源码证据**：AutomationStore.enqueueTerminalLocked成功仅发送result:{}。

**复现/核查**：完成发布/采集后检查complete body。

**修复指导**：按commandType发送typed result；大数据分批ingest，result带batch统计。

**验收**：非法resultType拒绝；发布/订单/指标各有结构化结果。

来源：S26、S06；完整链接见来源索引。

### B032 · P1 · 静态确认 · deliveryId没有绑定任务/设备/素材授权

模块：媒体/权限。关联实施：T046。

**源码证据**：media_manifest按tenant+assetIds查；deliveryId原样回显；download仅按tenant检查。

**复现/核查**：A设备请求分配给B的已知assetId，检查是否获文件。

**修复指导**：MediaDelivery绑定device/task/assetSet/expiry；所有下载入口强制校验并审计。

**验收**：同租户不同设备未授权素材403；取消/过期delivery失效。

来源：S04、S05；完整链接见来源索引。

### B033 · P1 · 静态确认 · 手机账号状态接口返回租户全部账号

模块：账号/权限。关联实施：T010。

**源码证据**：account_status先取tenant全部accounts；boundToDevice只是布尔字段。

**复现/核查**：A/B各绑不同账号；A调accounts/status。

**修复指导**：只返回当前设备活跃绑定账号的最小字段，去掉无关账号列表。

**验收**：A看不到B独有账号；解绑后立即不可见。

来源：S04；完整链接见来源索引。

### B034 · P1 · 需求差距 · 未保证同设备同平台仅一个当前账号

模块：账号/绑定。关联实施：T010, T011。

**源码证据**：bind_account_device只检查account/device配对，不查该设备同平台其它BOUND。

**复现/核查**：同台设备先绑闲鱼甲再绑乙，检查两个是否均BOUND。

**修复指导**：事务锁设备；平台维度唯一活跃绑定；换绑递增bindingVersion并阻止旧任务自动跟随。

**验收**：闲鱼甲/乙不能同时BOUND；闲鱼+小红书可并存；历史保留甲。

来源：S02、S03；完整链接见来源索引。

### B035 · P1 · 待复现风险 · 同设备可存在多个活跃Companion实例

模块：设备/身份。关联实施：T007。

**源码证据**：mobile_binding唯一键device_id+app_instance_id；enroll未撤销其它实例。

**复现/核查**：两个实例用不同enrollment绑定同一device；并发claim。

**修复指导**：一期每device一个active binding；重绑撤销旧token并抬高控制epoch。

**验收**：旧token无法领任务/远控；唯一活跃实例有DB约束。

来源：S04、S03；完整链接见来源索引。

### B036 · P0 · 待复现风险 · mobile claim缺设备级串行仲裁

模块：任务/互斥。关联实施：T016。

**源码证据**：claim锁任务行，未先锁设备/统一DeviceLease；两个并发请求均可能先看到无active。

**复现/核查**：Postgres并发2个claim，设备排队2任务，循环测试。

**修复指导**：先锁设备并取得统一fencing lease；再claim；所有执行路径共用同一仲裁。

**验收**：并发100次仅1个活跃writer；旧epoch后续动作被拒。

来源：S04、S03；完整链接见来源索引。

### B037 · P1 · 静态确认 · mobile任务路径未检查maintenance

模块：设备/维护。关联实施：T016。

**源码证据**：_insert_task与claim读取device/任务但未应用set_maintenance的设备限制。

**复现/核查**：设备设maintenance=true，再建/领mobile任务。

**修复指导**：维护模式阻止新AUTO执行；维护与lease变更使用同一事务；已有任务按暂停策略处理。

**验收**：维护中不能执行AUTO；退出后正常排队。

来源：S04、S02；完整链接见来源索引。

### B038 · P1 · 需求差距 · 现有是2秒截图，不是实时视频

模块：视频。关联实施：T030, T029, T032。

**源码证据**：DeviceDetailView请求captureIntervalMs=2000，使用img/blob轮询；后端存image_bytes。

**复现/核查**：打开远控页观察Network，没有实时媒体传输。

**修复指导**：MediaProjection+WebRTC媒体链路；公网TURN兜底；DB只存会话元数据。

**验收**：SIM真机连续视频与点击可用；不以提高截图频率冒充视频。

来源：S21、S04；完整链接见来源索引。

### B039 · P1 · 待复现风险 · 设备切换可能沿用旧预览session及迟到帧

模块：视频/路由。关联实施：T032。

**源码证据**：startPreview在已有session时return；watch设备id变化不先stop旧会话；poll用当前deviceId。

**复现/核查**：A投屏中路由切B，延迟A响应；检查stop参数与显示画面。

**修复指导**：会话绑定immutable deviceId；路由切换取消请求/旧session；frame带deviceId+session epoch。

**验收**：A帧绝不显示在B设备页面，旧回调不关闭B会话。

来源：S21；完整链接见来源索引。

### B040 · P1 · 静态确认 · 前端权限是SecurityAdmin开发桩

模块：Web/权限。关联实施：T005, T006。

**源码证据**：session.ts固定user-local且can()总true。

**复现/核查**：改角色或使用普通用户，观察按钮和权限判断。

**修复指导**：加载真实/me；dev桩仅dev；前端不替代后端鉴权。

**验收**：普通用户无远控/版本发布权限；直调API同样拒绝。

来源：S24；完整链接见来源索引。

### B041 · P1 · 静态确认 · 接口声称不点击发布但builder任务会直发

模块：发布/语义。关联实施：T078, T080。

**源码证据**：dispatch_post_to_xianyu返回tapsPublish=False；调用build_text_publish_task默认auto_publish=True。

**复现/核查**：检查生成steps是否含publish并比对响应。

**修复指导**：mode显式DIRECT/DRAFT/FORM_ONLY；返回行为与snapshot一致；不可逆动作走commit guard。

**验收**：DIRECT包含提交且响应一致；DRAFT保存草稿而非仅填表。

来源：S02、S07；完整链接见来源索引。

### B042 · P1 · 需求差距 · 采集宝贝信息页面仅本地记录

模块：统计。关联实施：T109, T111, T112。

**源码证据**：ListingInfoCollectView创建时save/record并说明不会真实抓取。

**复现/核查**：点击采集后查手机任务与指标数据库。

**修复指导**：统一collect命令+批次ingest+历史快照+Web查询。

**验收**：两次采集有两份时间点，null和0区分，结果可抽样核对。

来源：S22；完整链接见来源索引。

### B043 · P1 · 需求差距 · 水印配置/历史只存本机浏览器

模块：水印。关联实施：T051, T052, T053。

**源码证据**：PostWatermarkView.saveConfig调用本地save/pushHistory，成功文字为本机浏览器。

**复现/核查**：A存水印，B查询；检查真实任务是否引用水印后素材。

**修复指导**：持久化WatermarkProfile修订与Derivative资产；任务固定profileRevision/outputAssetId。

**验收**：跨浏览器一致，变更不影响旧任务，原图保留。

来源：S23；完整链接见来源索引。

### B044 · P1 · 需求差距 · 池后端与任务快照消费链尚需补齐

模块：资源池。关联实施：T054, T055, T056, T057。

**源码证据**：现有任务配置以地址池一至六等文本选项表示，无稳定poolId/itemId契约。

**复现/核查**：不同浏览器改池后比较配置；检查任务是否记录真实选中项。

**修复指导**：统一ResourcePool/PoolItem/DevicePoolBinding；创建任务记录实际选中值与版本。

**验收**：跨端一致；旧任务不因池编辑变化；缺池明确报错。

来源：S17、S18；完整链接见来源索引。

### B045 · P1 · 需求差距 · 已读移动/API链路未形成订单同步闭环

模块：订单。关联实施：T105, T106, T107, T108。

**源码证据**：operations有同步闲鱼订单入口；本轮已读mobile routes/schema无订单batch结果；全库仍需检索。

**复现/核查**：在T001真实仓库搜索Order/SyncRun/ingest并实测页面入口。

**修复指导**：先复用发现的领域代码，否则新增同步run、订单upsert、APK采集与分页管理页。

**验收**：默认全部/指定N、重复同步幂等、状态历史及错误可追踪。

来源：S20、S05、S06；完整链接见来源索引。

### B046 · P1 · 需求差距 · 现有授权任务表单仅“立即执行”选项

模块：定时。关联实施：T017, T018。

**源码证据**：XianyuSimple/Extra/PostPublish的schedule select只有立即执行；创建还是本地。

**复现/核查**：打开定时选择器、检查持久化计划与后端触发。

**修复指导**：复用Temporal+outbox新增预约/周期定义与独立任务生成；重复触发去重。

**验收**：时区/错过触发/重复消息/离线均有定义与测试。

来源：S15、S16、S13；完整链接见来源索引。

### B047 · P1 · 需求差距 · 自动化allowlist不能直接当全手机远控规则

模块：远控。关联实施：T034, T035, T036。

**源码证据**：ensureReady只允许Companion/闲鱼，但用户要操作手机其它页面。

**复现/核查**：想从网页点Home/打开其它App，现有接口无能力。

**修复指导**：自动化仍按平台allowlist；人工REMOTE会话独立授权坐标/系统导航，不开放shell。

**验收**：可人工操作桌面；未持REMOTE lease一律拒绝写动作。

来源：S28、S21；完整链接见来源索引。

### B048 · P1 · 需求差距 · APK安装门槛与截图能力门槛不同

模块：兼容。关联实施：T008, T030。

**源码证据**：build.gradle minSdk=29；无障碍takeScreenshot需更高系统能力，不能将可安装等同可投屏。

**复现/核查**：在实际Note9上读取SDK，测试现有截屏路径。

**修复指导**：保持实际设备基线；MediaProjection实现视频，不靠SDK30截图硬门禁；能力分别探测。

**验收**：设备报告安装/视频/控制/输入能力各自结果。

来源：S30、S28、S32；完整链接见来源索引。

### B049 · P1 · 待验证约束 · 不能承诺进程重启后无感恢复投屏授权

模块：视频/授权。关联实施：T030, T033。

**源码证据**：Android官方要求每个MediaProjection会话取得用户同意，token不可复用。

**复现/核查**：授权后停止capture/重启进程，再试旧token。

**修复指导**：区分浏览器断线和采集会话终止；前者重连同采集，后者显示NEEDS_LOCAL_CONSENT。

**验收**：拒绝/撤销授权不崩溃；不自动点击系统授权绕过同意。

来源：S32、S37；完整链接见来源索引。

### B050 · P1 · 待验证约束 · 普通后台App不能任意读系统剪贴板

模块：剪贴板。关联实施：T037。

**源码证据**：Android10+限制后台剪贴板读取；用户需要复制粘贴不能仅承诺无条件双向同步。

**复现/核查**：在闲鱼前台、Companion后台读取剪贴板测试。

**修复指导**：远控文本以ACTION_SET_TEXT为主；自定义IME需用户启用；提供手动分享/粘贴通道并声明能力。

**验收**：受支持路径完成中文输入与复制；无权读取显示不可用，不返回假空成功。

来源：S33；完整链接见来源索引。

### B051 · P1 · 待验证约束 · 后台发布APK不等于系统允许静默安装

模块：APK更新。关联实施：T043。

**源码证据**：PackageInstaller可能要求STATUS_PENDING_USER_ACTION；未确认Device Owner。

**复现/核查**：在个人普通手机安装新APK，记录回调。

**修复指导**：验签下载+系统安装器+用户确认；业务后台发布和安装确认分离；热Recipe更新不冒充APK更新。

**验收**：签名错误拒绝；需确认显示状态；旧版本任务与数据可恢复。

来源：S34、S30；完整链接见来源索引。

### B052 · P1 · 需求差距 · 已有自动化包管理需接到Companion本地版本生命周期

模块：Recipe发布。关联实施：T019, T040, T041, T042。

**源码证据**：services.py已有register_automation/签名/promotion；本地执行仍以固定step+locator为主。

**复现/核查**：发布一个新包，验证目标Companion是否下载/验签/激活/上报版本。

**修复指导**：复用已有包/签名/审批模型；补phone recipe manifest与手动发布、兼容验证和回退。

**验收**：未点击发布不生效；运行中固定旧版本；篡改包拒绝。

来源：S02、S27、S29；完整链接见来源索引。

### B053 · P1 · 需求差距 · 目录blocked/已下线文案不能当真实功能验收

模块：闲鱼/范围。关联实施：T004, T102。

**源码证据**：operations blockedTerms含签到/抵扣/推广/好评；PostPublish声称闲鱼帖子已下线，未真机验证。

**复现/核查**：核对31个闲鱼目录项并在实际App探测相关入口。

**修复指导**：已确认范围逐项实现；发布/删除帖子先做可用性验证；不存在则记录NOT_SUPPORTED证据，不静默剔除或假成功。

**验收**：31项都有实现任务或可验证受阻原因。

来源：S20、S13；完整链接见来源索引。

### B054 · P1 · 待复现风险 · 租约过期直接回排队缺外部提交核对

模块：任务/重领。关联实施：T024, T025。

**源码证据**：mobile claim把过期active改QUEUED；旧终态有本地防重，但进程/实例切换与未知提交结果仍需核对。

**复现/核查**：发布点击后断网且租约过期，换实例或恢复领取。

**修复指导**：副作用前持久化commit intent；不确定结果进RECONCILING，禁止盲目再次点击发布/付款/删除。

**验收**：故障注入下无自动重复提交；无法判断时等待人工。

来源：S04、S26；完整链接见来源索引。

### B055 · P1 · 待复现风险 · revision_no分配缺显式并发锁/前置版本条件

模块：帖子/并发。关联实施：T067。

**源码证据**：add_revision读取next_revision_no后insert，函数内未锁ContentItem或接expectedRevision。

**复现/核查**：两个请求并发给同content追加revision，检查冲突/500/覆盖。

**修复指导**：锁content或乐观compare-and-swap；409业务冲突，不暴露IntegrityError。

**验收**：并发只有一次有效提交，revision连续且API返回稳定。

来源：S02；完整链接见来源索引。

### B056 · P1 · 待复现风险 · 批量改价缺版本条件和行锁

模块：商品/并发。关联实施：T059。

**源码证据**：batch_update_product_price查询后更新price/revision，未用expectedRevision或with_for_update。

**复现/核查**：单项编辑与批量改价并发，比较最终price/revision。

**修复指导**：按id固定顺序锁行并校验预期版本；定义冲突后整批回滚。

**验收**：无丢失更新/重复revision；冲突返回逐项诊断。

来源：S02；完整链接见来源索引。

### B057 · P2 · 静态确认 · 同名文件按basename匹配可能串图

模块：导入/媒体。关联实施：T065。

**源码证据**：ProductImportView将目录文件以file.name为字典key；不同子目录同名会覆盖。

**复现/核查**：a/1.jpg与b/1.jpg同时导入且对应不同商品。

**修复指导**：使用规范化相对路径；重名不能确定时要求映射，禁止最后一个覆盖。

**验收**：两商品关联正确文件hash；缺图不标完整导入成功。

来源：S11；完整链接见来源索引。

### B058 · P1 · 待复现风险 · CSV未处理以公式字符开头的用户字段

模块：导出/安全。关联实施：T070。

**源码证据**：XianyuPublishGoodsView.exportCsv仅双引号转义；标题/描述可为用户输入。

**复现/核查**：标题以=、+、-、@开头后导出，用安全测试表格验证是否被当公式。

**修复指导**：统一CSV文本安全编码；下载文件不执行公式；不改变数据库原文。

**验收**：恶意公式按纯文本打开；引号、换行、中文正确。

来源：S14；完整链接见来源索引。

### B059 · P2 · 静态确认 · 任务列表固定最多200条且无翻页

模块：任务/历史。关联实施：T013, T028。

**源码证据**：mobile_service.list_tasks order_by(created_at.desc()).limit(200)。

**复现/核查**：创建201条任务，尝试查最早一条。

**修复指导**：提供cursor/limit及device/platform/account/state过滤；长期历史可访问。

**验收**：201条均可分页找到，稳定排序不漏不重。

来源：S04；完整链接见来源索引。

### B060 · P2 · 待复现风险 · 素材下载整对象读入内存

模块：媒体/大文件。关联实施：T046, T116。

**源码证据**：download_media拿stored.content并整体hash、返回bytes；视频量大时需要内存压测。

**复现/核查**：并发10个大视频下载，记录API峰值RSS/阻塞。

**修复指导**：对象存储流式下载或授权短链+客户端校验；大小/超时/并发限额；不要把视频流经JSON/base64。

**验收**：并发下载内存有界，取消释放资源，hash校验不取消。

来源：S04；完整链接见来源索引。

### B061 · P2 · 复核纠正 · 旧稿“预览无自动续期”表述不准确

模块：旧稿修正。关联实施：T001。

**源码证据**：DeviceDetailView.pollPreview在inactive时会startPreview重建；应审查间隙/竞态，不说完全没有续期。

**复现/核查**：阅读pollPreview 123-126附近并观察跨TTL行为。

**修复指导**：撤回旧I040原结论；新方案实时视频会话独立管理，不重复开无依据Bug。

**验收**：本文件不再要求修一个已经存在的自动重建逻辑。

来源：S21；完整链接见来源索引。

### B062 · P2 · 复核纠正 · 旧稿部分路径与目录数量错误

模块：旧稿修正。关联实施：T001, T004。

**源码证据**：实际文件在apps/web/src/data，不是lib；闲鱼目录31项，违禁词30、教程31。

**复现/核查**：比对目录树与operations-catalog。

**修复指导**：本表全部修正为实际data路径；功能覆盖以31项为准。

**验收**：智能体按路径可找到文件；31项没有漏掉末项或错位。

来源：S20、S01；完整链接见来源索引。

### B063 · P2 · 待验证约束 · 本轮不能证明全部构建/运行/安全缺陷已穷尽

模块：代码覆盖。关联实施：T001, T002, T120。

**源码证据**：公开main源码静态核查；容器git clone DNS失败；无Android真机、无实际API/DB运行。

**复现/核查**：在真实仓库执行基线命令与全目录扫描，记录未读/未跑项。

**修复指导**：不得将47或本表数量声称全部Bug；把新失败补入此Sheet，保留证据与严重度。

**验收**：有可重复构建日志、全库覆盖矩阵与真机证据才允许结案。

来源：S31、S01；完整链接见来源索引。


## 7. 按依赖排序的120项实施任务


### 阶段 A 基线与身份

#### T001 · P0 · 锁定代码并跑真实基线

前置任务：无。模块：工程。初始状态：未开始。

代码位置：`README.md；AGENTS.md；package.json；pyproject.toml；mobile/companion`

**实施步骤**

1. 记录git rev-parse HEAD；与本次b394475比较并生成差异清单。
2. 读取AGENTS/README，不直接升级依赖；复制环境模板时不用真实密钥入库。
3. 按README准备Python3.12+/Node22+/pnpm10.15+/JDK17或21/SDK35。
4. 执行pip install -e ".[dev]"与pnpm install --frozen-lockfile。
5. 执行ruff format --check .、ruff check .、pyright、mypy、pytest -q。
6. 读取package.json的真实scripts后依次跑lint、typecheck、test、build和e2e；Android在工程目录执行./gradlew test lint assembleDebug；缺脚本记录实际替代命令。
7. 无Android SDK/设备或依赖安装失败时写阻塞原因，不填通过。
8. 保存docs/phase1/baseline.md，逐命令记录退出码和原始日志。

**接口/数据契约**：基线失败与后续回归分开记录；本次没有实际运行上述工程命令。

**必须执行的验收**
1. 干净环境能复跑同一SHA。
2. 失败项逐条入01代码审阅。
3. 不把mock或编译成功写成真机发布成功。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B061, B062, B063；需求：工程基线；来源：S31、S01。

#### T002 · P0 · 全仓覆盖和问题补录

前置任务：T001。模块：工程。初始状态：未开始。

代码位置：`apps/{web,studio}；services/*；edge/gateway；mobile/{companion,dpc}；packages/*；infra；tests`

**实施步骤**

1. 按文件夹列出语言、入口、依赖和测试，生成覆盖矩阵。
2. 全仓检索localStorage、mock、TODO、pass、NotImplemented、except Exception及硬编码成功。
3. 检查API路由→service→DB→outbox→APK的每个真实调用链。
4. 复核鉴权、tenant过滤、上传、SQL、密钥日志、反序列化和依赖版本风险。
5. 针对本表待复现项补Postgres并发及契约回归测试。
6. 列出未读目录、未运行测试、无硬件功能，不假设已覆盖。
7. 新发现按B新增编号记录位置、触发、修复、验收。
8. 一期外问题记录但不自动扩展一期开发范围。

**接口/数据契约**：覆盖率指已审阅文件/已执行测试，不能用“全仓无报错”替代业务验收。

**必须执行的验收**
1. 每个一级目录都有审阅状态。
2. 新旧Bug可追溯。
3. 一期外代码变更有明确原因。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B063；需求：工程基线；来源：S31、S01。

#### T003 · P0 · 写分层ADR并确定复用边界

前置任务：T001。模块：架构。初始状态：未开始。

代码位置：`docs/adr（新增一期ADR）；services/control-api；services/temporal-worker；packages/automation-sdk`

**实施步骤**

1. 盘点已有租户、账号、设备租约、PublishPlan/Snapshot、commit ledger、自动化包签名和outbox。
2. 保留Control API模块化服务，不为百台设备新增无必要微服务。
3. 业务任务由云端创建；APK下载已发布Recipe并本地跑状态图，云端不循环下发每一步。
4. 复用Temporal负责预约/周期触发；DB为任务事实，Redis只用于可替换信令分发。
5. 视频走MediaProjection/WebRTC/TURN；指令、媒体文件、实时视频分别传输。
6. 写唯一任务与唯一设备写锁约定，防止新旧执行链同时下发。
7. 声明Root/Device Owner非一期默认前提，普通系统授权不能绕过。
8. ADR列字段/API新增位置与旧路径迁移开关。

**接口/数据契约**：旧PublishPlan/Target/提交账本不得另造并行发布事实；Edge仅开发诊断。

**必须执行的验收**
1. 同一设备不存在两套独立写锁。
2. 有新旧功能开关及回滚路线。
3. 所有任务能定位唯一状态来源。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R07, R18；来源：S31、S02、S03。

#### T004 · P1 · 逐字段盘点及31项闲鱼目录覆盖

前置任务：T001。模块：范围。初始状态：未开始。

代码位置：`apps/web/src/data/operations-catalog.ts；views/OperationView.vue或实际动态页面分发入口（全库定位）`

**实施步骤**

1. 读取31个闲鱼titles并保留原operationId，记录具体渲染页面。
2. 按原始一期清单列产品6项、商品3项、帖子、小红书、订单、采集。
3. 逐页面提取v-model字段、类型、枚举、默认值和按钮语义。
4. 形成field-map.json：UI字段→DTO→快照字段→Recipe消费→验收用例。
5. 主/副闲鱼切换与新单平台单账号需求冲突时禁用旧多开选项并注明原因。
6. 已下线发布/删除帖子不可静默剔除，转可用性验证任务。
7. 同名地址池/水印/采集入口映射共享服务，禁止重复建库。
8. CI断言每个一期可编辑字段已映射或明确受阻，不能静默忽略。

**接口/数据契约**：字段仅存库不算发布实现；平台不支持的字段须保留数据并给出明确不支持原因。

**必须执行的验收**
1. 31项均有处理归属。
2. 没有开启但未消费的字段。
3. 旧blocked不作为永不实现的依据。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B053, B062；需求：R16, R19, R20；来源：S20、S18、S17。

#### T005 · P1 · 生产API真相与真实登录态

前置任务：T001, T003。模块：Web。初始状态：未开始。

代码位置：`apps/web/src/api/product-catalog.ts；api/post-catalog.ts；stores/session.ts；env.d.ts`

**实施步骤**

1. 新增显式api/mock环境模式并默认生产api。
2. 移除404/501隐式切本地；禁止错误后继续副作用请求。
3. 统一ApiError(code,message,requestId,fieldErrors)。
4. 复用或新增GET /api/v1/me，session从真实身份加载。
5. can()读权限集合，dev stub仅测试开发构建。
6. 业务缓存只在API成功后失效刷新；保留用户未提交表单但不伪造已保存。
7. 清点相关localStorage键，迁移工具单独处理。
8. 补生产404、401、409、500及刷新恢复测试。

**接口/数据契约**：UI权限只改善体验，后端必须独立鉴权；生产API缺失不能自动写本地。

**必须执行的验收**
1. 断API保存失败且无业务本地新增。
2. 低权限不能远控/发版。
3. 清空localStorage不丢真实业务数据。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B004, B040；需求：R18；来源：S08、S09、S24。

#### T006 · P1 · 统一设备/文件/版本发布权限

前置任务：T003。模块：安全。初始状态：未开始。

代码位置：`services/control-api/src/cloudctl_api/auth.py；services.py；mobile_routes.py；packages/domain权限定义`

**实施步骤**

1. 复用tenant和actor模型，列device.read/control、task.create、recipe.publish、data.delete权限。
2. 所有设备、任务、媒体、订单查询必须带tenant并验证资源关系。
3. Companion凭据只能访问自身任务与绑定账号，不可用操作者API。
4. 新增审计动作：接管、恢复、换绑、发布版本、删除数据。
5. 网页令牌不放查询URL或公开媒体地址；日志脱敏。
6. 写两个tenant和同tenant两设备的越权测试。
7. 写入操作保留幂等键和requestId。
8. 旧权限兼容映射写迁移说明，不能直接去掉现有鉴权。

**接口/数据契约**：一期单租户运行也必须过跨租户测试；后续二期不需重建所有主键。

**必须执行的验收**
1. 跨tenant请求404/403。
2. 设备A不能读B任务/素材。
3. 发版必须操作者身份及权限。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B040；需求：R18；来源：S02、S04、S05。

#### T007 · P1 · 设备注册、重绑与凭据撤销

前置任务：T006。模块：设备。初始状态：未开始。

代码位置：`services/control-api/src/cloudctl_api/mobile_service.py、db.py；mobile/companion/app/src/main/java/com/company/cloudctl/companion/security/与network/`

**实施步骤**

1. 复核现有enrollment一次性码、有效期和token摘要机制并复用。
2. 同device注册新instance时锁设备并撤销其它活跃binding。
3. 增加唯一活跃binding约束或active_binding_id事实字段。
4. 重新绑定递增controlEpoch，旧token和旧会话立即失效。
5. Companion用安全存储保存凭据，不在日志打印。
6. 补在线/失联/未授权状态，不用手机可达IP做身份。
7. 暴力尝试注册码限速，错误不泄露账号信息。
8. 迁移时重复活跃binding先列冲突报告再处理。

**接口/数据契约**：POST /api/v1/mobile/enrollments与/companion/v2/enroll沿用；新字段须向后兼容。

**必须执行的验收**
1. 重绑后旧token401。
2. 并发注册只有一个活跃实例。
3. 手机通过SIM能注册和心跳。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B035；需求：R02；来源：S04、S03、S05。

#### T008 · P1 · 自动探测真实设备系统与能力

前置任务：T007。模块：APK。初始状态：未开始。

代码位置：`mobile/companion/app/src/main/java/com/company/cloudctl/companion/device/LocalHealthCollector；service/CompanionSyncService.kt；services/control-api/src/cloudctl_api/mobile_schemas.py`

**实施步骤**

1. 上报manufacturer/model、SDK_INT、Android版本、ROM摘要及Companion版本。
2. 分别探测无障碍、gesture、截图、MediaProjection状态、输入方式和可用存储。
3. 网络只上报WIFI/CELLULAR/UNKNOWN等必要信息，不伪造延迟/信号。
4. 后端存lastSeen和capabilitiesVersion，Web显示未知/过期状态。
5. 用实际Note9采集报告，不通过机型猜Android版本。
6. 保持当前minSdk29基线待实测，不擅自抬到30以上。
7. 缺权限时给手机本地引导与Web提示，不自动批准系统授权。
8. 增加设备能力JSON fixture与前后端契约测试。

**接口/数据契约**：heartbeat增加可选字段兼容旧APK；capability不可用需reasonCode。

**必须执行的验收**
1. 实际Note9有设备报告。
2. 断开权限后任务前置校验失败。
3. WiFi/蜂窝切换真实反映。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B048；需求：R06；来源：S30、S25、S06。

#### T009 · P1 · 平台包/版本/账号能力自动探测

前置任务：T008。模块：App兼容。初始状态：未开始。

代码位置：`mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/TargetLocatorRegistry.kt；services/control-api/src/cloudctl_api/mobile_service.py、db.py`

**实施步骤**

1. 通过PackageManager读取闲鱼、小红书实际包名、versionCode/versionName。
2. 将包可见性queries写Manifest并在真机核对。
3. 服务端复用Device.target_app_versions并存probe时间，不再让用户手填。
4. 引入TargetAppRegistry包名、平台、所需权限、兼容Recipe范围。
5. 无安装/无授权/未知页面分别返回错误，不一律TASK_FAILED。
6. 平台UI变更用签名Recipe更新，不保证未测版本自动兼容。
7. 创建和真正执行任务时各校验一次，避免排队期间升级漂移。
8. 未知版本允许只读探测，禁止不可逆动作盲跑。

**接口/数据契约**：版本只是适配选择与证据，不作为用户必须知道的产品输入。

**必须执行的验收**
1. 卸载/升级后正确上报。
2. 官方单开小红书可注册。
3. 未知包本地和后端都拒绝。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B021, B022, B023；需求：R17；来源：S04、S29、S28。

#### T010 · P1 · 每平台唯一账号与换绑事务

前置任务：T009, T006。模块：账号。初始状态：未开始。

代码位置：`services/control-api/src/cloudctl_api/services.py bind_account_device；mobile_service.py account_status；db.py`

**实施步骤**

1. 复用PlatformAccount/AccountDeviceBinding；增加platform和bindingVersion或等价约束。
2. 事务锁device，确保同device同platform仅一条BOUND；两个平台可并存。
3. 绑定需APK本地识别登录账号，无法识别时标未核验，不编造账号ID。
4. 换绑先暂停/取消该平台未完任务，再更新绑定；旧绑定记录保留。
5. 创建任务冻结accountId和bindingVersion；执行前重新比对。
6. accounts/status只返回当前设备BOUND账号的必要字段。
7. 订单和发布实例按accountId查询而非按当前device归属。
8. 添加绑定/解绑/重绑/并发冲突及审计测试。

**接口/数据契约**：不保存平台登录密码；secretRef如旧模型必填，调整为适用授权方式的可选字段。

**必须执行的验收**
1. 1闲鱼+1小红书通过。
2. 两个闲鱼账号不能同时BOUND。
3. 换绑后旧排队任务ACCOUNT_CHANGED。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B033, B034；需求：R10；来源：S02、S04、S03。

#### T011 · P1 · 账号换绑后的数据归属与旧任务阻断

前置任务：T010。模块：历史。初始状态：未开始。

代码位置：`发布/订单/统计模型；账号页面；任务创建服务`

**实施步骤**

1. 内容库Product/Post作为租户资产，不强制绑定某个账号。
2. 已发布Listing、订单、指标及任务快照绑定原accountId。
3. 保存deviceIdAtExecution与bindingVersion用于追溯。
4. 换绑不批量UPDATE历史accountId，不根据当前设备动态归属。
5. 账号归档不级联删除订单/证据；删除走统一用户删除流程。
6. 周期任务固定账号；换绑后暂停该计划，不能自动跟随新账号。
7. Web支持按历史账号查数据并标已解绑。
8. 写甲→乙换绑后查询和周期触发用例。

**接口/数据契约**：账号历史保留不等于永不允许删除；用户删除有独立权限与引用策略。

**必须执行的验收**
1. 甲订单依然属于甲。
2. 乙无法误执行甲任务。
3. 历史设备与当前绑定都可解释。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B034；需求：R10, R13；来源：S02、S03。


### 阶段 B 任务与执行

#### T012 · P0 · 高层指令与强类型参数契约

前置任务：T003, T009, T004。模块：协议。初始状态：未开始。

代码位置：`contracts/phase1（新增）；packages/api-contracts；services/control-api/src/cloudctl_api/mobile_schemas.py；APK parser`

**实施步骤**

1. 定义CommandV1：taskId、attemptId、commandType、deviceId、accountId、bindingVersion。
2. 加入snapshot{id,sha256}、recipe{versionId,sha256,engineMinVersion}、targetPackage、requiredCapabilities。
3. 加入lease{controlEpoch,expiresAt}及mediaDeliveryId，不传长期下载密钥；本地用单调时钟维护租约截止。
4. 按commandType做discriminated union参数schema，未知字段和动作拒绝。
5. 保留旧steps读取兼容开关，新业务不再云端生成低层点击循环。
6. 生成TS/Python/Kotlin同一组合法和非法fixture。
7. 定义协议协商与UNSUPPORTED_PROTOCOL/RECIPE错误。
8. 任何v1变更先更新schema和fixtures再改实现。

**接口/数据契约**：手机只消费冻结参数和已发布本地Recipe；动态任意shell/DEX/JS执行均不在协议中。

**必须执行的验收**
1. 三端解析同fixture一致。
2. 错设备/错账号/错schema拒绝。
3. 云端命令不含未授权执行代码。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B021；需求：R07；来源：S06、S29、S27。

#### T013 · P0 · 统一业务任务API与唯一状态源

前置任务：T012, T010。模块：后端。初始状态：未开始。

代码位置：`services/control-api/src/cloudctl_api/db.py、services.py、mobile_service.py；新增platform_tasks.py/routes`

**实施步骤**

1. 新增PlatformTask映射现有MobileTask尝试；发布任务引用现有PublishPlan/Target而非复制发布账本。
2. 统一TaskState：QUEUED/WAITING_MATERIALS/PREFLIGHT/RUNNING/PAUSE_REQUESTED/PAUSED_WAITING_USER/RESUME_CHECK/RECONCILING/CANCEL_REQUESTED及终态；AUTO/REMOTE是独立控制模式。
3. 创建任务事务冻结账号、指令、参数，idempotencyKey同内容返回原任务。
4. 同key不同内容409；批量设备创建独立taskId，可共享batchId筛选。
5. 新增list/detail/cancel/retry API与游标分页，不固定只取200条；retry仅可判定安全失败，不确定提交先核对。
6. 只有状态机服务能写状态；Web与APK不可随意PATCH成功。
7. 完成/失败/取消重复回调应幂等，不可覆盖既有不同终态。
8. 保留createdBy、attempt、scheduledFor和停滞原因用于排障。

**接口/数据契约**：新增/api/v1/platform-tasks；原/api/v1/mobile/tasks为底层兼容，不另建业务队列。 终态限定SUCCEEDED/FAILED/CANCELLED/EXPIRED；REMOTE不是业务任务终态。

**必须执行的验收**
1. 双击只建1任务。
2. 201条历史可分页查全。
3. 跨设备并行、同设备仅顺序执行。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B059；需求：R09；来源：S04、S03、S02。

#### T014 · P1 · 步骤事件、错误和结构化结果

前置任务：T013。模块：协议/后端。初始状态：未开始。

代码位置：`contracts/phase1/events/results；services/control-api/src/cloudctl_api/mobile_schemas.py、mobile_service.py`

**实施步骤**

1. 事件含taskId、attemptId、sequence、stateId/stepId、eventType、occurredAt、receivedAt。
2. 错误含code、safeMessage、locatorRef、appVersion、recipeVersion和evidenceRefs。
3. 每个command定义resultType/schemaVersion；发布、批量操作、订单、采集各不同。
4. 大列表不塞complete，使用batch ingest结果引用。
5. 重复sequence+同payload返回成功，异payload冲突；处理缺口补传。
6. 加入pause/resume/reconcile相关事件，不用FAILED代替暂停。
7. 接口限制body大小且敏感字段不进普通日志。
8. Web事件流使用现有events/outbox模式加游标重连。

**接口/数据契约**：UTC保存时间；业务时区仅调度解释；不信任设备时钟作为授权有效期唯一依据。

**必须执行的验收**
1. 不同失败code保持原义。
2. 事件重放不乱序。
3. 错误resultType被422拒绝。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B026, B027, B031；需求：R05；来源：S04、S06、S26。

#### T015 · P1 · 不可变业务快照和资源解析规则

前置任务：T013。模块：一致性。初始状态：未开始。

代码位置：`复用PublishSnapshotRow；新增通用TaskSnapshot或等价结构；services/control-api/src/cloudctl_api/services.py`

**实施步骤**

1. 发布快照包含最终文案、金额、选中池条目、媒体版本/顺序、水印产物与账号绑定版本。
2. 随机选取只在云端创建时做一次并记录种子/结果，APK不再次随机。
3. 已创建任务只读快照，不读取被编辑后的Product/Post最新值。
4. 普通重试复用快照；使用最新内容必须显式创建新任务。
5. 定时计划保存版本化模板；每个触发生成独立快照且记录模板版本。
6. 快照canonical hash服务端计算，手机校验签名/哈希。
7. 被删除资源按软删/引用策略保留可执行版本；真正缺失暂停报错。
8. 为编辑商品/池/水印之后旧任务不变写集成测试。

**接口/数据契约**：默认地址选择：设备池优先、通用池回退；用户可配置。默认规则是设计值，不伪称用户已指定。

**必须执行的验收**
1. 旧任务文案和媒体hash不漂移。
2. 相同任务重试不重新随机。
3. 快照可以独立复现要执行的内容。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R07, R19；来源：S02、S03。

#### T016 · P0 · 所有设备写操作共用fencing租约

前置任务：T013, T007。模块：并发安全。初始状态：未开始。

代码位置：`services/control-api/src/cloudctl_api/mobile_service.py claim；services.py acquire_lease；db.py DeviceLeaseRow；APK执行门禁`

**实施步骤**

1. 事务锁device并按enqueueSeq取队头，复用DeviceLeaseRow；队头未就绪/暂停时后项不得越过，取消或到期才释放。
2. 租约ownerType=AUTO/REMOTE，递增epoch；同device只有一个writer。
3. claim前检查maintenance、active binding、当前账号与能力。
4. 领取后立即启动续租，包括素材下载和页面准备阶段。
5. APK在每个写动作前检查本地单调时钟期限/epoch/cancelToken。
6. 租约过期本地立即停止写；旧设备/旧进程不能因离线继续控制。
7. 过期且已发生commit intent转RECONCILING，不能直接当可重试发布。
8. Postgres并发和网络隔离测试覆盖新旧执行链。

**接口/数据契约**：设计初值lease60秒/续租15秒，需配置与压测；暂停只读不需要自动化writer，但设备逻辑队列仍阻塞到恢复/取消。

**必须执行的验收**
1. 同设备并发100次claim仅1writer。
2. 旧epoch命令拒绝。
3. maintenance禁止AUTO。
4. 下载期间不丢租。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B025, B036, B037；需求：R04, R09；来源：S04、S02、S03。

#### T017 · P1 · 预约和周期产生独立任务

前置任务：T013, T015。模块：调度。初始状态：未开始。

代码位置：`services/temporal-worker；services/outbox-dispatcher；新增schedule模型/API`

**实施步骤**

1. 复用Temporal定时能力；Schedule含timezone、onceAt或RRULE、enabled、templateRevision。
2. 每次触发唯一键scheduleId+scheduledFor+deviceId，重复投递只产生一个任务。
3. 一次性到点入FIFO；设备离线保留队列，过startDeadline改EXPIRED不补发旧发布。
4. 周期漏触发默认只补最新一期，其余记SKIPPED；策略可配置。
5. 同设备原任务暂停时后续排队，不绕过原任务自动执行。
6. 模板固定accountId/bindingVersion；换绑后暂停计划。
7. 保存UTC触发时间及原IANA时区；显式处理夏令时重复/缺失小时。
8. enable/disable/delete只影响未来触发，已生成任务独立显示。

**接口/数据契约**：设计默认：发布startDeadline到点后30分钟；订单/采集可更宽。参数可调，不当用户已确认SLA。

**必须执行的验收**
1. 重复消息不重复建任务。
2. 时区/DST测试。
3. 关闭计划不再触发。
4. 10设备生成10独立任务。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B046；需求：R09；来源：S31、S02。

#### T018 · P1 · 统一立即/预约/周期表单

前置任务：T017, T005。模块：Web。初始状态：未开始。

代码位置：`apps/web/src/components/ScheduleEditor.vue（新增）；所有一期任务表单`

**实施步骤**

1. 封装IMMEDIATE/ONCE/RECURRING组件，显示浏览器检测的时区并允许修改。
2. 预约校验未来时间，周期显示接下来3次执行时间。
3. 显示账号、设备、模板版本与错过触发处理，不藏默认行为。
4. 各页面删除只含立即执行的旧select。
5. 一次提交返回独立任务列表或scheduleId；避免按钮连点重复创建。
6. 调度历史来自后端，支持停用/恢复和错误状态。
7. 显示离线排队与等待人工的区别。
8. 组件测试覆盖空时间、跨日、时区和API错误。

**接口/数据契约**：不新增优先级UI；批量入口只是便捷创建独立任务。

**必须执行的验收**
1. 刷新后预约仍在。
2. 10台创建结果显示10 taskId。
3. 每页使用同一调度DTO。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B046；需求：R09；来源：S15、S16、S13。

#### T019 · P0 · 定义可签名的手机本地状态图包

前置任务：T012, T003。模块：Recipe。初始状态：未开始。

代码位置：`contracts/phase1/recipe-manifest.schema.json（新增）；packages/automation-sdk`

**实施步骤**

1. manifest定义id/version/hash/signingKeyId、minEngineVersion、platform/app范围、commandTypes。
2. 状态图定义stateId、entryGuard、action、postcondition、success/failure/pause分支。
3. 动作限定内置tap/input/scroll/extract/wait/launch/media等白名单。
4. 循环必须maxIterations/maxDuration；变量类型受schema约束。
5. 定义safeCheckpoint、resumeGuard、commitActionId与结果映射。
6. 明确这是设备本地解释执行的签名数据包，不是云端逐步控制。
7. 校验未知动作、无出口循环、超长输入、危险权限、路径穿越。
8. 用正常/损坏/越权/旧引擎包做签名与结构校验fixture。

**接口/数据契约**：原生新能力需要APK升级；页面和流程变化可更新数据Recipe；不开放任意远程代码执行。

**必须执行的验收**
1. 伪造/篡改/不兼容包拒绝。
2. 状态图有界。
3. 全部动作在APK白名单中。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B052；需求：R08；来源：S02、S27、S29。

#### T020 · P0 · 本地Recipe解释器与平台注册

前置任务：T019, T009。模块：APK。初始状态：未开始。

代码位置：`mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/（新增RecipeEngine/RecipeRegistry/RecipeContext）`

**实施步骤**

1. 解析签名manifest和state graph，启动时选择task固定recipe hash。
2. 执行循环在手机内进行，云端断线不转成云端逐步点击。
3. 每个action调用安全UI原语，前后检查lease/cancel/pause和目标package。
4. 支持typed变量、条件、有限列表迭代及结构化extract。
5. 平台自动化只允许已注册包；人工远控不复用此平台限制。
6. 等待使用可取消协程和monotonic deadline，不用固定大sleep。
7. 所有事件写本地outbox，检查点与副作用journal分开。
8. 用fake UI编写分支/超时/循环上限/未知页面单元测试。

**接口/数据契约**：旧low-level steps用兼容adapter，不继续扩成第二套主引擎。

**必须执行的验收**
1. 同命令独立本地完成流程。
2. 循环不会无限跑。
3. 未知页面进WAITING_USER。
4. 错recipe hash拒绝。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B022；需求：R07, R11；来源：S27、S28、S29。

#### T021 · P1 · 执行生命周期、启动和下载错误修复

前置任务：T020, T016, T014。模块：APK。初始状态：未开始。

代码位置：`mobile/companion/app/src/main/java/com/company/cloudctl/companion/service/CompanionSyncService.kt；automation/CloudCtlAccessibilityService.kt`

**实施步骤**

1. 把素材准备、账号核验、App启动、执行纳入同一try/finally状态机。
2. claim后启动租约续期，不等视频下载完成。
3. 新增launchTargetApp并等待前台包；系统禁止后台拉起时回报需用户处理。
4. 已知弹窗匹配白名单处理，未知截图暂停；禁止猜坐标点关闭。
5. CancellationException独立传播；业务失败保留ExecutorFailure.code。
6. finally释放资源但不删除未上传证据/检查点。
7. 进程重启只恢复已持久化状态，不能直接把未知提交重跑。
8. 检测锁屏/存储不足/授权关闭，记录准确停滞原因。

**接口/数据契约**：常亮执行是用户环境，不等于永不崩溃；不承诺自动解锁PIN或绕过系统权限。

**必须执行的验收**
1. 手机桌面能启动平台。
2. 下载异常不卡RUNNING。
3. 取消不伪装失败。
4. 缺权限不会盲跑。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B024, B025, B026；需求：R06, R11；来源：S25、S28、S26。

#### T022 · P1 · 独立事件和结果上传协程

前置任务：T014, T021。模块：APK。初始状态：未开始。

代码位置：`mobile/companion/app/src/main/java/com/company/cloudctl/companion/data/AutomationStore.kt；service/CompanionSyncService.kt；network/`

**实施步骤**

1. 将flushOutbox从任务主循环解耦为独立上传job。
2. 按task+sequence保持顺序；不同task的重试不互相永久饿死。
3. 保存typed terminal result，替换result空JSON。
4. 失败信息按大小截断与敏感数据脱敏，不丢原code。
5. 网络退避带jitter；401停发并提示重授权；重试不重复副作用。
6. 回调ACK持久化后才删除/标记已交付。
7. 证据上传引用与事件顺序协同，未上传标pending。
8. 测试进程在发送前/后、ACK前/后崩溃的四个切点。

**接口/数据契约**：仅日志可最终一致；设备控制租约和不可逆动作门禁不能等日志慢慢补。

**必须执行的验收**
1. 长任务运行时Web及时收到steps。
2. 重连顺序正确。
3. 成功结果不是{}。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B027, B028, B031；需求：R05；来源：S25、S26。

#### T023 · P0 · 持久化可恢复检查点

前置任务：T020, T022, T015。模块：APK恢复。初始状态：未开始。

代码位置：`mobile/companion/app/src/main/java/com/company/cloudctl/companion/data/AutomationStore.kt；automation/RecipeContext`

**实施步骤**

1. 新增checkpoint表taskId+attemptId+revision，含stateId/stepId、变量、目标itemId、循环游标。
2. 记录snapshotHash/recipeHash/accountId/bindingVersion和预期页面指纹。
3. 在动作成功且postcondition核验后事务写检查点与step event。
4. 写动作前另存intent，不能只靠最后step序号猜完成。
5. 暂停保存环境摘要并清理悬空gesture；保留当前页面。
6. 重启读取检查点后进入RESUME_CHECK，不把所有RUNNING变FAILED_RESTART。
7. 对变量/正文和敏感字段按本地安全存储策略处理。
8. 测试中途重启与循环第N项恢复，已完成item不重做。

**接口/数据契约**：检查点不是屏幕截图；必须包含能判定恢复安全性的业务状态。

**必须执行的验收**
1. 同taskId从检查点继续。
2. 第N项恢复不重做前N-1项。
3. 版本不匹配停下。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B029, B030；需求：R05；来源：S26、S27。

#### T024 · P0 · 发布/消耗/删除提交门禁

前置任务：T023, T016。模块：副作用安全。初始状态：未开始。

代码位置：`复用发布commit ledger；APK新增ActionJournal；服务端操作结果账`

**实施步骤**

1. 对publish/delete/review/推广消耗等定义稳定actionKey=task+目标+动作版本。
2. 最终按钮前持久化INTENT及目标参数hash，验证lease和账号。
3. 同actionKey存在APPLIED时只核验，不再次点击。
4. INTENT后未确认结果记UNKNOWN，不直接按失败重试。
5. 本地与云端分别保存提交证据和状态，断网时不能依靠云端“保证一次”。
6. 真正确认成功才APPLIED；平台ID不可得时返回证据及待核对状态。
7. 批量每item独立journal，部分成功任务可继续剩余项。
8. 模拟点击后丢ACK/进程退出/换绑，测试无自动二次提交。

**接口/数据契约**：不宣称第三方UI严格exactly-once；采用可判定防重+不确定结果核对。

**必须执行的验收**
1. 点击发布后断网不自动再发。
2. 预算/参数变化必须重新确认。
3. 已有成功item不重复处理。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B029, B054；需求：R05, R16；来源：S31、S04、S26。

#### T025 · P1 · 不确定外部结果核对

前置任务：T024。模块：恢复。初始状态：未开始。

代码位置：`新增ReconciliationService；平台Recipe核对分支；Web任务详情`

**实施步骤**

1. UNKNOWN进入RECONCILING并暂停普通重试。
2. 按account、目标itemId、时间、快照摘要及平台可见结果核对。
3. 查到唯一结果写APPLIED并恢复后续；明确未提交才允许重新操作。
4. 结果相似但不能唯一确认时等待人工，不靠标题相同认定。
5. 人工确认必须选择已成功/未成功/继续等待并填写证据。
6. 记录核对操作者和时间，保留原attempt history。
7. 订单/采集重复上传只做幂等upsert，不按发布核对逻辑重跑UI。
8. 增加“发布已成功但complete丢失”的E2E用例。

**接口/数据契约**：确认未成功不是无证据强制重试；平台没有可靠身份时保留不确定状态。

**必须执行的验收**
1. 未知状态不会自动变成功。
2. 有结果可收敛。
3. 所有人工核对可审计。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B054；需求：R05；来源：S31、S26。

#### T026 · P0 · 暂停请求与安全停止握手

前置任务：T023, T016。模块：接管。初始状态：未开始。

代码位置：`PlatformTask状态机；APK RecipeContext cancel/pause token；控制API`

**实施步骤**

1. 新增POST task:pause，状态RUNNING→PAUSE_REQUESTED。
2. APK收到控制消息后在安全点停止新动作、取消等待，保存checkpoint。
3. 最后gesture完成/取消后回ACK，状态PAUSED_WAITING_USER。
4. 后台只有收到安全停止ACK才转移writer给REMOTE。
5. 超时只能等待租约失效后确认停止，不能让两端同时写。
6. 已过commit intent进入RECONCILING，仍可看屏但恢复按核对规则。
7. 取消单独走CANCEL_REQUESTED/CANCELLED，取消后不提供继续原任务。
8. 暂停阻塞本设备FIFO，防止下一任务把现场覆盖。

**接口/数据契约**：控制消息可独立于长任务主循环接收；只读观看不触发pause。

**必须执行的验收**
1. 自动任务运行时看屏不暂停。
2. 接管前自动化确已停。
3. 暂停后后续队列不越过。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R04, R05；来源：S04、S27、S26。

#### T027 · P0 · 交还控制权并继续原任务

前置任务：T026, T025, T011。模块：恢复。初始状态：未开始。

代码位置：`POST task:resume；APK ResumeValidator；任务详情按钮`

**实施步骤**

1. REMOTE结束先停止接收旧epoch控制消息并释放远控lease。
2. 复核原task仍暂停、account/binding/snapshot/recipe版本一致。
3. APK读取当前页面，执行resumeGuard；只有确定安全才从检查点继续。
4. 人工已完成当前动作则核验postcondition并推进；未知则停在待人工。
5. 新的AUTO lease拥有新epoch，旧远控动作即使迟到也拒绝。
6. 仍用原taskId，增加resumeCount与审计记录，不从步骤1重跑。
7. 账号换了、资产删了或Recipe不兼容时明确阻止继续。
8. 写“编辑页中断→人工回到正确页→原任务继续发布”真机用例。

**接口/数据契约**：可以自动回到安全锚点，但不能为恢复随意丢弃人工内容或重复提交。

**必须执行的验收**
1. 处理后继续同taskId。
2. 旧远控命令不落地。
3. 无法判定不盲目恢复。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B029, B030；需求：R05；来源：S26、S27。

#### T028 · P1 · 统一任务队列、详情与恢复入口

前置任务：T013, T014, T026, T027, T018。模块：Web。初始状态：未开始。

代码位置：`apps/web/src/views/TaskQueue/TaskDetail（按现有路由复用）；新增共用任务组件`

**实施步骤**

1. 列表从后端分页，支持设备/平台/账号/状态/时间过滤。
2. 显示独立taskId、等待原因、当前步骤、版本和队列位置。
3. 详情呈现快照、steps、typed result、错误与证据。
4. 暂停/接管/继续/取消/核对结果各自独立按钮和权限。
5. 网络断线显示状态过期，不继续显示伪实时进度。
6. 周期计划和已经生成的任务区分，不混作同一状态。
7. 事件流断线按cursor补拉，防止漏终态。
8. 页面刷新和清localStorage后可恢复所有任务记录。

**接口/数据契约**：长期任务历史可查；无父任务状态；batchId仅过滤。

**必须执行的验收**
1. 所有任务页复用同状态组件。
2. 暂停与失败视觉区分。
3. 刷新不丢历史。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B059；需求：R05, R09；来源：S04、S20。


### 阶段 C 视频与远控

#### T029 · P0 · 设备主动联网的WebRTC会话服务

前置任务：T006, T007。模块：信令/TURN。初始状态：未开始。

代码位置：`control-api新增RealtimeSessionService；复用edge-hub连接职责；部署TURN`

**实施步骤**

1. 创建rtc_session表：tenant/device/viewer、状态、过期时间和sessionEpoch，不存视频帧。
2. 实现鉴权WSS信令：offer/answer/ICE/close；手机主动建立出站连接。
3. 浏览器请求会话必须有device:view权限；控制权另行申请，不因看视频获得控制。
4. 接入TURN短期凭据，配置UDP以及TCP/TLS中继路径；凭据不写前端源码。
5. 信令按sessionId+epoch路由，禁止A设备消息进入B会话。
6. 设置心跳、断线重连、会话回收；多实例通过共享会话目录定位设备。
7. 部署文档写明公网证书、端口、防火墙、TURN公网地址和出口带宽。
8. 在两端不在同一LAN的环境测试直连和强制relay，不把内网成功当蜂窝验收。

**接口/数据契约**：POST /devices/{id}/rtc-sessions；WSS signaling；TURN REST短期凭据。接口名称为建议，优先复用现有路由规范。

**必须执行的验收**
1. SIM网络可建立relay视频。
2. 跨租户信令403。
3. TURN凭据过期不可继续新建会话。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B038；需求：R02, R03；来源：S35、S36、S31。

#### T030 · P0 · MediaProjection实时采集与前台服务

前置任务：T008, T029。模块：Android视频。初始状态：未开始。

代码位置：`mobile/companion/app/src/main/java/com/company/cloudctl/companion/新增screen/ScreenCaptureService.kt；AndroidManifest.xml；授权Activity`

**实施步骤**

1. 按设备SDK实现MediaProjection授权入口，明确用户可见授权状态。
2. target35声明正确前台服务类型/权限并显示持续通知；按官方启动顺序实现。
3. 用户授权后建立一次capture session，持有VirtualDisplay和编码输入Surface。
4. 用WebRTC视频源传帧，不JPEG/base64写数据库；默认720p约20fps仅为可调设计值。
5. 处理屏幕旋转与尺寸变化，发viewportVersion/width/height/rotation。
6. 会话存活时浏览器重连复用现有采集，不重复消费授权token。
7. 用户撤销/进程死亡后停止并上报NEEDS_CAPTURE_CONSENT；不得承诺静默恢复授权。
8. 记录Redmi Note9实际SDK/ROM；测试授权、拒绝、停止、旋转、重连。

**接口/数据契约**：CaptureState=IDLE/NEEDS_CONSENT/ACTIVE/STOPPED/ERROR；真实能力上报。

**必须执行的验收**
1. 有授权可连续视频。
2. 拒绝授权不崩溃不假在线。
3. 进程死亡后重新授权路径明确。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B038, B048, B049；需求：R03, R06；来源：S32、S37、S30。

#### T031 · P1 · WebRTC连接、编码和弱网自适应

前置任务：T030, T029。模块：Android网络。初始状态：未开始。

代码位置：`mobile/companion/app/src/main/java/com/company/cloudctl/companion/新增realtime/PeerSessionManager.kt`

**实施步骤**

1. 集成锁定版本WebRTC库并记录许可证与ABI体积；禁止不固定版本下载。
2. 按sessionEpoch创建PeerConnection，验证服务端签发的会话许可。
3. 绑定MediaProjection视频轨，协商可用硬件编码，失败提供明确降级原因。
4. 配置可调整分辨率、fps、码率上下限，流畅优先但不无上限耗流量。
5. 上报连接类型、RTT、丢包、发送fps/码率和采集时间，不伪造数字。
6. ICE失败做有限重启与relay回退，暂停状态有明确UI。
7. 无观看者按生命周期释放/停止发送，不能百台一直高码率推流。
8. 测试移动网络切换、信令断连、TURN临时不可用与编码器失败。

**接口/数据契约**：RealtimeStatsV1；视频媒体走WebRTC，任务与素材仍走既有HTTPS通道。

**必须执行的验收**
1. 强制relay可用。
2. 网络恢复不重启自动任务。
3. 无viewer时无持续高码率上传。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R01, R02, R03；来源：S36、S35、S32。

#### T032 · P0 · 可复用实时播放器与设备切换隔离

前置任务：T031。模块：Web视频。初始状态：未开始。

代码位置：`apps/web/src/views/DeviceDetailView.vue；新增components/DeviceLiveScreen.vue`

**实施步骤**

1. 用video轨替换一期主投屏img轮询，旧截图只作为故障诊断而非验收替代。
2. 组件固定持有deviceId/sessionId/epoch；路由切换先关旧会话并清video.srcObject。
3. 异步响应校验epoch，A设备迟到帧/回调不能显示或关闭B会话。
4. 显示真实连接状态、最后帧时间、网络质量；卡住显示stale。
5. 自动重连只恢复观看，不自动恢复写控制权。
6. 处理竖横屏和object-fit留白，输出当前内容区域与viewportVersion。
7. 页面销毁/切隐藏页遵循会话保活策略，释放track/listener。
8. 模拟快速切设备与延迟answer，验证无串屏。

**接口/数据契约**：DeviceLiveScreen提供只读默认模式；控制通过独立租约能力传入。

**必须执行的验收**
1. 连续切A/B不串屏。
2. 断网显示卡顿而不是假实时。
3. 主界面真实视频。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B038, B039；需求：R03, R04；来源：S21、S36。

#### T033 · P1 · 长时间观看、重连和授权状态闭环

前置任务：T032, T030。模块：会话生命周期。初始状态：未开始。

代码位置：`RealtimeSessionService；APK CaptureService；Web设备状态组件`

**实施步骤**

1. 明确capture session与browser viewing session是两种生命周期。
2. 短时浏览器断线保留已授权采集服务一段可配置grace；无viewer停止发送。
3. capture仍存活时重建peer，避免误要求重复授权。
4. capture已死亡/被系统回收时上报需现场授权，不绕过系统权限。
5. 同时观看同设备允许只读；只有一个写控制租约。
6. 会话过期只关视频连接，不取消自动化任务。
7. 长期观看统计内存/编码资源；每次stop释放surface/track/peer。
8. 长任务连续观看30分钟，断开浏览器再连及手机撤销授权各留证据。

**接口/数据契约**：会话TTL/grace为配置；长期云端素材保留不代表永久维持录屏服务。

**必须执行的验收**
1. 30分钟观看不因120秒预览过期中断。
2. 重连不多建capture。
3. 授权丢失明确可见。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B049；需求：R03, R04；来源：S32、S21。

#### T034 · P0 · 独立写控制权和时效命令协议

前置任务：T026, T029, T016。模块：远控协议。初始状态：未开始。

代码位置：`新增RemoteControlSession；contracts/RemoteCommandV1；control lease服务`

**实施步骤**

1. 申请REMOTE写权先调用安全暂停，收到ACK后签发新的controlEpoch。
2. DataChannel用可靠有序通道发送操作，但每个命令仍校验seq/ttl/epoch。
3. 定义tap/swipe/longPress/text/back/home/recents；坐标0..1且附viewportVersion。
4. 服务端/设备双侧记录当前有效writer，撤销时立即失效旧epoch。
5. 网络恢复不重放旧点击；过期操作ACK=EXPIRED。
6. 只读viewer没有控制token；远控需用户显式点击开始。
7. 控制权丢失自动停止发送，自动任务仍按暂停状态等待，不悄悄续跑。
8. 写contract测试：重复seq、过期、越权、旧epoch、旋转旧viewport全部拒绝。

**接口/数据契约**：RemoteCommand{sessionId,controlEpoch,seq,ttlMs,viewportVersion,action,args}；RemoteAck{seq,status,executedAt}。

**必须执行的验收**
1. 看屏不占writer。
2. 旧epoch命令无法落地。
3. 点击后断网不在重连时补点击。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B047；需求：R04, R05；来源：S36、S04。

#### T035 · P0 · 手势和系统键能力

前置任务：T034, T020。模块：Android远控。初始状态：未开始。

代码位置：`mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/CloudCtlAccessibilityService.kt；新增RemoteCommandExecutor.kt`

**实施步骤**

1. 入口先验控制token、epoch、seq、ttl和viewport，再执行任何手势。
2. 坐标转换基于当前显示区域/旋转/边界，拒绝越界。
3. 实现dispatchGesture点按、滑动、长按，记录完成/取消回调。
4. 实现系统Back/Home/Recents；权限不足返回明确错误。
5. 人工远控允许用户操作其它App，不复用闲鱼专属automation allowlist误拦截。
6. 自动化执行仍严格限定recipe允许平台；两条权限边界不可混淆。
7. 每次旋转抬高viewportVersion，旧坐标命令丢弃。
8. 在Note9真机竖横屏、导航栏、键盘出现场景执行九宫格点击测试。

**接口/数据契约**：通用远控原语受REMOTE许可；自动化原语受command/platform许可。

**必须执行的验收**
1. 可Home并操作其它App。
2. 竖横屏映射正确。
3. AUTO未暂停无法远控。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B047；需求：R04, R12；来源：S28、S36。

#### T036 · P0 · 屏幕操作面板与交还自动化

前置任务：T035, T032, T027。模块：Web远控。初始状态：未开始。

代码位置：`apps/web/src/components/DeviceLiveScreen.vue；新增RemoteControlPanel.vue`

**实施步骤**

1. 获取REMOTE前默认禁用所有写操作，保留观看。
2. 按video实际内容矩形而非容器尺寸归一化鼠标坐标，消除letterbox偏差。
3. pointer down/move/up区分tap、swipe和长按，限制发送频率。
4. 提供Back/Home/Recents、文本输入、结束接管按钮。
5. 显示命令ACK/超时；不能用按钮动画冒充手机已执行。
6. 旋转、stale画面或无控制权时停止坐标发送。
7. 人工处理后“交还并继续”调用resume，不新建task。
8. 关闭页面释放REMOTE，原任务保持待恢复，不在无人确认下自动继续。

**接口/数据契约**：独立按钮：仅观看／暂停并接管／交还并继续原任务／取消任务。

**必须执行的验收**
1. 浏览器缩放不误点。
2. 接管后原taskId可恢复。
3. 关页不偷偷续跑。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B047；需求：R04, R05, R12；来源：S21。

#### T037 · P1 · 明确能力边界的输入与复制粘贴

前置任务：T035, T036。模块：文字/剪贴板。初始状态：未开始。

代码位置：`mobile/companion/app/src/main/java/com/company/cloudctl/companion/input/；Web RemoteControlPanel`

**实施步骤**

1. 优先Accessibility ACTION_SET_TEXT对可编辑节点写入，支持中文和换行。
2. 需要复杂键盘时设计用户启用的Companion IME，不能静默切换输入法。
3. 电脑粘贴先以显式text命令发送，不依赖后台读系统剪贴板。
4. 手机到电脑复制仅在Android允许读取的前台/默认IME上下文执行。
5. 无法读取剪贴板返回CAPABILITY_UNAVAILABLE，并提供显式分享/输入框通道。
6. 不后台持续监听密码/验证码，不把全部剪贴板写日志。
7. 文本输入绑定目标焦点与当前viewport，失焦拒绝或提示重新选择。
8. 测试中文、emoji、长文本、密码字段拒绝和Android剪贴板限制。

**接口/数据契约**：ClipboardBridge是显式用户动作；不承诺所有App的双向实时剪贴板。

**必须执行的验收**
1. 中文文本可写。
2. 受限复制清楚提示。
3. 日志不泄露剪贴板内容。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B050；需求：R12；来源：S33、S28。

#### T038 · P1 · 设备卡片、能力和任务观察接入

前置任务：T028, T032, T036, T008。模块：设备主页。初始状态：未开始。

代码位置：`apps/web/src/设备列表视图与DeviceDetailView.vue；device API`

**实施步骤**

1. 设备列表显示真实online/lastSeen/network/targetApps/当前账号/当前任务。
2. 移除固定Wi-Fi延迟和信号强度文案；不可获得显示未知。
3. 每张卡只按用户打开才启动视频，不一次打开全部手机视频。
4. 任务详情复用同一播放器和步骤时间轴。
5. 将权限缺失、版本待适配、需要录屏授权分别显示。
6. 账号解绑/换绑跳转真实绑定接口并显示历史归属说明。
7. 加入排队数量、暂停等待人工原因；不伪造空闲状态。
8. 清localStorage、断API、断手机分别测试真实空态和错误态。

**接口/数据契约**：GET device detail返回capabilities、accounts、activeTask、networkTelemetry和captureState。

**必须执行的验收**
1. 任务中能实时看屏。
2. SIM网络显示真实类型。
3. 缺权限可定位。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R01, R03, R04；来源：S21、S24。


### 阶段 D 版本与发布

#### T039 · P1 · 自动探测版本的定位器采样与回归

前置任务：T009, T020, T023。模块：适配实验室。初始状态：未开始。

代码位置：`mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/TargetLocatorRegistry.kt；新增测试采样工具；版本包fixtures/`

**实施步骤**

1. 读取实际已安装闲鱼/小红书版本，不要求用户提供。
2. 建立pageState语义名，locator优先resourceId/层级/类型，多策略文本作后备。
3. 为每个关键页面保存脱敏树、截图、应用版本和屏幕状态fixture。
4. 实现locator probe runner，列出匹配数与歧义，不允许多匹配默认点第一个。
5. 未知页面暂停；仅经审核的已知弹窗有处理分支。
6. 输入框、最终发布、支付/消耗/删除按钮必须有明确postcondition。
7. 版本包声明支持范围与页面指纹，不能一个中文描述适配所有未来版本。
8. 生成真机认证记录，未实测版本只标待验证。

**接口/数据契约**：LocatorSet{platform,appVersionRange,pageStates,selectors,postconditions}；脚本新版本须回归fixture。

**必须执行的验收**
1. 多匹配拒绝盲点。
2. App升级后安全暂停。
3. 真机采样可重复运行。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B023；需求：R07, R11；来源：S29、S28。

#### T040 · P0 · 复用现有签名/晋级的人工发布流程

前置任务：T019, T006, T039。模块：后端版本。初始状态：未开始。

代码位置：`复用AutomationVersion/package_signature/promotions；新增部署关联与验证结果`

**实施步骤**

1. 盘点现有模型和签名验证路径，优先扩展，不建同义版本表。
2. 包内含schema、recipe、locator、最小engineVersion、兼容App范围和文件hash。
3. 状态DRAFT→VALIDATED→READY→PUBLISHED；校验失败不可发布。
4. 新增上传/验证/发布/撤回接口，Publish必须独立权限且记录操作者。
5. 智能体仅能提交草稿或验证，不能绕过人工点击自动发布。
6. 指定设备或设备组创建各自部署记录；保留每机ACK。
7. 运行/暂停任务固定原recipeHash；撤回阻止新任务选择，不强删旧包。
8. 防重放和签名key轮换有文档；私钥不进仓库/日志/文件附件。

**接口/数据契约**：PublishRequest{versionId,targetDeviceIds,idempotencyKey}；已发布包不可原地修改。

**必须执行的验收**
1. 未点击发布设备不获生效指令。
2. 篡改包拒绝。
3. 每次发布可审计。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B052；需求：R08；来源：S31、S03。

#### T041 · P1 · 版本查看、验证结果和手动发布按钮

前置任务：T040。模块：Web版本。初始状态：未开始。

代码位置：`apps/web/src/新增自动化版本管理页（复用已有版本工作台）`

**实施步骤**

1. 展示版本号、差异、兼容范围、验证结果和签名状态。
2. 默认新上传状态草稿；按钮文案明确“发布到所选设备”。
3. 点击前显示设备列表、正在运行任务及何时生效。
4. 用户确认后发Publish API，生成审计记录。
5. 每设备显示已下载/已验证/待空闲/已激活/失败。
6. 提供撤回与回退到已验证旧recipe版本，不修改运行任务。
7. 权限不足隐藏写按钮，后端仍校验。
8. 测试智能体上传后等待用户、部分设备离线、失败重试。

**接口/数据契约**：不提供自动发布开关作为一期默认；用户要求B流程。

**必须执行的验收**
1. 后台点发布才推送。
2. 离线设备可补领。
3. 能追踪每机版本。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B052；需求：R08；来源：S31。

#### T042 · P1 · 签名校验、空闲激活与版本回退

前置任务：T040, T023。模块：APK版本。初始状态：未开始。

代码位置：`mobile/companion/app/src/main/java/com/company/cloudctl/companion/新增updates/RecipePackageManager.kt；AutomationStore`

**实施步骤**

1. 主动拉取已为本设备发布的部署记录，不接受随意URL执行。
2. 流式下载临时文件并验证manifest签名/所有文件hash/租户和目标兼容性。
3. 防zip路径穿越/超大小/解压炸弹，包不可含未许可可执行代码。
4. 校验engineVersion和App版本；不兼容上报待升级而非强制激活。
5. 原子安装到version目录；只有无运行和暂停任务引用时切active指针。
6. 运行/暂停任务始终使用创建时recipeHash，恢复不得跨版本。
7. 回退指针到保留的已验证版本；升级失败不破坏旧版本。
8. 向云端回报downloaded/verified/active及错误，测试断电与损坏包。

**接口/数据契约**：版本激活是原子指针切换；历史包保留到所有引用任务结束及保留规则允许删除。

**必须执行的验收**
1. 下载中断旧版可用。
2. 暂停任务升级后仍可恢复旧版。
3. 无签名包不执行。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B052；需求：R05, R08；来源：S31、S26。

#### T043 · P1 · 整包更新与系统安装确认

前置任务：T042, T008。模块：APK升级。初始状态：未开始。

代码位置：`复用APK发布/下载设施；Companion PackageInstaller安装入口`

**实施步骤**

1. 核查现有APK更新机制并复用签名/版本元数据。
2. 产物固定applicationId与签名证书，versionCode递增；不要自动换签名。
3. 云端人工发布APK版本，记录目标设备与最低recipe engine兼容性。
4. 手机下载校验APK签名/hash/包名/versionCode。
5. 仅在任务安全暂停/空闲时调用系统安装流程，保护本地DB迁移。
6. 需要用户确认时上报AWAITING_INSTALL_CONFIRMATION，并允许投屏协助可操作环节。
7. 不承诺无Root/设备所有者条件下静默安装或强制降级。
8. 更新后验证注册身份、队列、检查点和已授权能力，失败给恢复说明。

**接口/数据契约**：APK安装受Android系统政策；Recipe回退不等于Android APK可任意降级。

**必须执行的验收**
1. 新APK可升级且保留数据。
2. 用户拒绝有状态。
3. 升级不重复执行已提交动作。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B051；需求：R08；来源：S34、S30。


### 阶段 E 素材与资源池

#### T044 · P0 · 统一上传组件替代data/blob业务字段

前置任务：T005。模块：Web素材。初始状态：未开始。

代码位置：`apps/web/src/新增api/media-assets.ts与components/MediaAssetUploader.vue；ProductEdit/PostEditor`

**实施步骤**

1. 先从现有routes读取create/upload/complete契约并生成TS类型。
2. 文件选择只创建临时预览；上传后业务值只保存assetId。
3. 支持图片/视频、顺序、封面、进度、取消、重试和上传失败显示。
4. 保存前验证所有引用asset已complete；禁止把blob/data URL交业务API。
5. 上传大文件使用现有分块/直传能力；没有则按后端契约实现，不把视频base64塞JSON。
6. 刷新页面通过授权URL重新预览，卸载组件revoke临时URL。
7. 统一MIME/大小提示，后端做最终验证，保留原文件名仅作展示。
8. 测试刷新、换浏览器、断点失败和相同文件重复引用。

**接口/数据契约**：MediaRef{assetId,kind,mime,size,sha256,order,cover}；临时previewUrl不持久化。

**必须执行的验收**
1. DB中无data/blob素材。
2. 跨浏览器媒体可用。
3. 上传失败不能伪保存成功。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B007, B015；需求：R12；来源：S10、S12、S02。

#### T045 · P1 · 复用MediaAsset并完善引用和访问校验

前置任务：T044, T006。模块：媒体后端。初始状态：未开始。

代码位置：`现有MediaAsset/ObjectStore/ContentRevisionMedia/ProductMedia/MediaDerivative服务`

**实施步骤**

1. 保留现有媒体模型，补状态VALIDATING/READY/FAILED必要能力。
2. 服务端验证实际MIME、尺寸/时长、大小和hash，不信前端文件后缀。
3. 只有READY可被商品/帖子/快照引用。
4. 产品/帖子修订维护媒体顺序和封面FK；禁止引用其它租户资产。
5. 下载用鉴权代理或短期授权URL，不生成永久公开链接。
6. 删除前检查产品/帖子/任务/派生引用；默认归档，不立即物理清除。
7. 长期保存原件；临时未完成上传可按显式清理策略移除。
8. 测试共享资产、对象丢失、元数据失配和中断complete幂等。

**接口/数据契约**：主素材长期保留可手删；临时上传清理与业务原件保留区分。

**必须执行的验收**
1. 未完成媒体不能发布。
2. 共享引用不误删。
3. 越权下载403。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R12, R13；来源：S03、S02、S31。

#### T046 · P0 · 按任务和设备绑定素材下发

前置任务：T045, T015, T007。模块：素材授权。初始状态：未开始。

代码位置：`services/control-api/src/cloudctl_api/mobile_service.py；新增MediaDelivery关联模型/migration`

**实施步骤**

1. 建deliveryId→tenant/device/task/assetSet/expiry/state关联，不再只回显ID。
2. 任务创建后按冻结asset集合授权，普通文件推送有独立delivery用途。
3. manifest/download每次校验设备身份、delivery归属、asset membership及有效期。
4. 断线重试可刷新下载授权，但不能扩大asset集合。
5. 取消或设备换绑按策略撤销未开始delivery；运行任务安全暂停。
6. 下载接口支持stream/range；限制并发/字节速率，避免大视频阻塞心跳。
7. 记录访问审计不含敏感公开URL。
8. 复现A设备读取B资产并确认新策略403。

**接口/数据契约**：MediaDeliveryManifest含assetId/path或URL/mime/size/sha256；URL不能作为额外授权来源。

**必须执行的验收**
1. 同租户越设备素材访问被拒。
2. 合法断点重试成功。
3. 过期被拒。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B032, B060；需求：R12；来源：S04、S05。

#### T047 · P0 · 续租期间流式下载与任务媒体清单

前置任务：T046, T016, T021。模块：APK素材。初始状态：未开始。

代码位置：`mobile/companion/app/src/main/java/com/company/cloudctl/companion/现有媒体下载协调器；任务文件缓存`

**实施步骤**

1. 领取任务后先启动续租，再进入下载阶段。
2. 每任务私有目录；按assetId写temp，流式下载，不把大视频整体读入内存。
3. 检查size/hash后atomic rename并保存本地manifest。
4. 文件存在且hash相符则复用；不相符重下并隔离损坏文件。
5. 所有下载异常进入统一可恢复任务状态，不留RUNNING僵尸。
6. 取消/暂停/失租能中止下载；失租后不得继续UI动作。
7. 限制本地磁盘占用，临时拷贝可清理但云端原件不受影响。
8. 在限速、500、checksum错、磁盘满四场景测试。

**接口/数据契约**：LocalMediaManifest{taskId,snapshotHash,assetId,localPath,hash,ready}。

**必须执行的验收**
1. 大视频下载不断租。
2. 中断重试不选半文件。
3. 内存不随视频大小线性增长。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B025；需求：R12；来源：S25、S04。

#### T048 · P0 · 确定性选取本任务图片与视频

前置任务：T047, T039。模块：APK相册。初始状态：未开始。

代码位置：`mobile/companion/app/src/main/java/com/company/cloudctl/companion/新增media/TaskMediaAlbum.kt；平台picker helpers`

**实施步骤**

1. 通过MediaStore将任务素材暴露为唯一任务相册/显示名，保留asset→contentUri映射。
2. 按snapshot顺序导入，并保存导入时间和条目ID。
3. 各App picker按实际版本验证可见相册与排序；禁止默认第N张就是任务素材。
4. 选择后核对数量、缩略图顺序或可得标识，不能核验时暂停。
5. 视频/图文分支按平台支持规则预检。
6. 发布失败保留排障素材；任务完成清本机临时相册条目可配置。
7. 清理只删Companion自己建立的MediaStore条目，不删用户原图库。
8. 预置100张旧图和重复文件名，真机测试多图顺序与视频。

**接口/数据契约**：PickerAdapter属于版本化recipe；无法稳定定位则待适配，不能盲目点击图库索引。

**必须执行的验收**
1. 有旧图库仍只选任务素材。
2. 顺序正确。
3. 不会误删用户照片。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R12；来源：S29、S28。

#### T049 · P1 · 电脑上传并推送手机文件箱

前置任务：T046, T047, T036。模块：文件推送。初始状态：未开始。

代码位置：`新增FilePush任务用途与手机文件箱UI；复用MediaAsset`

**实施步骤**

1. 网页上传后选择设备与允许的媒体用途，创建独立file_delivery任务。
2. 设备后台下载与自动发布材料用同一hash验证管道。
3. 本机文件箱展示文件名/类型/大小/下载状态，支持显式导入相册。
4. 敏感路径不允许由网页指定；限制在App目录/授权MediaStore。
5. 远控中的文件推送不强行抢占自动化UI，可只后台下载。
6. 提供删除本机临时副本操作，区分删除云端原素材。
7. 禁止任意APK执行、shell命令或越权文件浏览。
8. 测试图片视频推送、重传、磁盘满与换设备隔离。

**接口/数据契约**：FilePush{assetIds,deviceId,destination=APP_BOX|MEDIA_ALBUM}；非任意文件系统远程访问。

**必须执行的验收**
1. 电脑图片视频可到指定手机。
2. 跨设备隔离。
3. 删除本机不误删云端。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R12；来源：S04。

#### T050 · P1 · 截图与失败现场上传查看

前置任务：T045, T014, T022。模块：任务证据。初始状态：未开始。

代码位置：`新增TaskEvidence元数据；对象存储上传；APK EvidenceUploader；任务详情`

**实施步骤**

1. Evidence记录task/device/account/step/time/hash/mime/size与asset引用。
2. 复用私有对象存储上传，未完成标pending，上传完成再附可读引用。
3. 自动化关键提交前后、失败、未知页和人工暂停生成截图。
4. 树摘要脱敏并限制大小；不采集密码/验证码文本。
5. 事件携带evidenceId；Web授权读取并显示拍摄时间。
6. 弱网后台补传不阻塞安全停机；无法截图也保留失败原因。
7. 证据长期保存，用户删除按审计与引用规则处理。
8. 模拟上传后ACK丢失与截图失败，任务状态仍正确。

**接口/数据契约**：直播不是录制；任务证据/用户保存截图是明确持久化对象。

**必须执行的验收**
1. 网页可看具体step截图。
2. 失败无截图仍可诊断。
3. 跨租户403。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B028；需求：R05, R12, R13；来源：S27、S26、S02。

#### T051 · P1 · 持久化现有水印全部有效字段

前置任务：T045, T010。模块：水印配置。初始状态：未开始。

代码位置：`services/control-api/src/cloudctl_api/新增watermark profile服务；apps/web/src/views/PostWatermarkView.vue字段映射`

**实施步骤**

1. 逐项清点当前UI文字/图片水印、昵称/用户名、位置、透明度、尺寸等字段。
2. 定义WatermarkProfile及不可变revision，imageLogo引用MediaAsset。
3. 接口CRUD/启停/复制/预览，字段白名单与数值范围验证。
4. 动态账号字段来自任务绑定账号快照，不取设备后来换绑的昵称。
5. 模板编辑不覆盖已被任务引用的revision。
6. 不支持的视频水印字段明确标待实现，不静默套用图片处理。
7. 删除profile只归档，保留旧任务所需配置。
8. 写每个UI字段→schema→处理器映射表并测试。

**接口/数据契约**：WatermarkProfileRevision{text/image/variables,position,scale,opacity,margin,...}。

**必须执行的验收**
1. 换浏览器配置一致。
2. 改水印不改旧任务。
3. 未知变量拒绝。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B043；需求：R19；来源：S23、S03。

#### T052 · P1 · 复用派生媒体工作流生成确定素材

前置任务：T051, T015。模块：水印处理。初始状态：未开始。

代码位置：`现有MediaDerivative/outbox worker；新增watermark renderer`

**实施步骤**

1. transformHash包含sourceHash/profileRevision/渲染后账号文本/处理器版本。
2. 有相同READY derivative则复用；没有则通过现有job/outbox生成。
3. 保留原图，输出作为新MediaAsset；正确处理EXIF旋转/透明背景。
4. 文本过长、字体缺失、素材过大返回明确错误，不输出空白图。
5. 任务进入WAITING_MATERIALS，所有输出READY后才进入设备FIFO执行。
6. 视频水印按一期实际UI范围实现独立转码job；未做的模式不允许提交。
7. 处理失败可重试相同transformHash，禁止每次生成重复对象。
8. 固定测试样本做像素/尺寸/文字位置验收及原图hash不变测试。

**接口/数据契约**：最终TaskSnapshot冻结outputAssetIds；水印不是APK发布时随机处理。

**必须执行的验收**
1. 同输入输出可复用。
2. 原图不变。
3. 处理失败任务不错误开跑。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B043；需求：R19；来源：S31、S23、S03。

#### T053 · P1 · 水印页面接配置与真实预览

前置任务：T052。模块：Web水印。初始状态：未开始。

代码位置：`apps/web/src/views/PostWatermarkView.vue；新增watermark API client`

**实施步骤**

1. 读取服务端profiles而非本地默认列表。
2. 保存调用后端revision接口，上传logo走MediaAsset。
3. 预览请求真实derivative并显示生成中/失败。
4. 文案区分示例预览与绑定账号最终渲染。
5. 商品发布配置选择profileId/revision，不提交浏览器缓存图片。
6. 冲突返回409提示刷新，不无条件覆盖。
7. 一次性旧本地配置导入需确认并展示差异。
8. 跨浏览器编辑和任务使用输出图验收。

**接口/数据契约**：所有当前启用水印控件须映射后端字段；不支持项不可假保存。

**必须执行的验收**
1. 配置和预览真实可恢复。
2. 发布使用预览所对应规则。
3. 生产不写水印localStorage。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B043；需求：R19；来源：S23。

#### T054 · P1 · 资源池和设备绑定后端模型

前置任务：T006, T010。模块：资源池。初始状态：未开始。

代码位置：`services/control-api/src/cloudctl_api/新增ResourcePool/PoolItem/DevicePoolBinding；migration`

**实施步骤**

1. Pool含tenant/type/name/revision/enabled/selectionMode；Item含valueJson/weight/order/enabled。
2. type限定ADDRESS/DESCRIPTION/TAG；每类payload单独校验。
3. 设备地址绑定FK到device+pool，校验租户/type。
4. CRUD支持expectedRevision，归档不硬删历史快照。
5. 选择器在服务端执行并冻结selectedItemId和值；APK不重新抽签。
6. 设备地址优先、无设备池用通用池是本方案默认，可配置，不称用户强制规则。
7. 随机选择使用任务seed；轮询用事务计数防并发重复。
8. 测试同租户多浏览器、一致性、禁用池、空池和跨租户引用。

**接口/数据契约**：PoolSelectionSnapshot{poolId,poolRevision,itemId,itemRevision,resolvedValue,selectionSeed}。

**必须执行的验收**
1. 旧任务池内容不漂移。
2. 跨设备绑定正确。
3. 空池不能随机生成假地址。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B044；需求：R19；来源：S20、S02。

#### T055 · P1 · 地址池编辑、绑定与任务选用

前置任务：T054。模块：通用/设备地址。初始状态：未开始。

代码位置：`apps/web/src/通用地址池、XianyuDeviceAddressPoolView等实际页面；后端address resolver`

**实施步骤**

1. 盘点现有地区层级/详细地址/名称等字段并保留类型。
2. 通用地址CRUD全部调API；设备池增加真实设备选择与绑定。
3. 后端验证省市区/地址字段结构，不把字符串拼接当平台定位成功。
4. 发布创建时执行设备池优先/通用fallback并写快照。
5. 无地址或平台不支持设定时创建阶段明确提示，不盲选地图。
6. 任务详情展示实际选中地址与来源池。
7. 移除正常流程localStorage读写，旧数据走专门迁移。
8. 测试A/B设备池不同、空设备池fallback、已创建任务不随改池变化。

**接口/数据契约**：地址是业务数据；手机执行按可见平台入口设置，不改GPS/不伪造定位系统。

**必须执行的验收**
1. 跨浏览器一致。
2. 设备池优先可配置。
3. 实际选择可追溯。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B044；需求：R19；来源：S20。

#### T056 · P1 · 描述模板后端化与变量渲染

前置任务：T054。模块：描述池。初始状态：未开始。

代码位置：`apps/web/src/XianyuDescriptionPoolView.vue；后端description resolver`

**实施步骤**

1. 将当前描述条目/启停/排序字段映射DESCRIPTION item。
2. CRUD/批量导入调用API，不本地记录成功。
3. 变量只允许已列明product/account字段，不执行模板代码。
4. 渲染后trim与长度校验，未知变量返回fieldError。
5. 创建任务冻结最终文本与所用条目revision。
6. 前端预览显示最终渲染示例，但任务时后端重新按快照字段渲染。
7. 多条随机/轮询按池配置，失败重试不换文本。
8. 测试模板并发修改、emoji、超长及变量缺失。

**接口/数据契约**：最终文本进入snapshot；不让APK联网查询“最新描述”。

**必须执行的验收**
1. 同任务重试描述不变。
2. 未知变量拒绝。
3. 模板跨浏览器一致。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B044；需求：R19；来源：S20。

#### T057 · P1 · 标签CRUD与确定性抽取

前置任务：T054。模块：标签池。初始状态：未开始。

代码位置：`apps/web/src/XianyuTagPoolView.vue；后端tag resolver`

**实施步骤**

1. 标签条目trim/去空/规范化，保留用户显示文本。
2. CRUD/排序/批量导入调API，重复标签按规范键提示。
3. 选择数量与池可用数量校验，不能不足时无限循环。
4. 按seed取标签，冻结顺序与itemId。
5. 平台限制由对应recipe兼容配置提供，后端校验。
6. 标签输入与正文拼接区分，不能重复加两次#。
7. 保存失败不本地fallback。
8. 测试中文、同名不同空格、禁用、数量超出。

**接口/数据契约**：SelectedTagsSnapshot保留原文本与平台渲染文本。

**必须执行的验收**
1. 任务标签稳定。
2. 重复标签不误增。
3. 无可用标签给明确错误。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B044；需求：R19；来源：S20。


### 阶段 F 产品与帖子

#### T058 · P0 · 修复价格类型和商品分组外键

前置任务：T001, T003。模块：商品数据库。初始状态：未开始。

代码位置：`services/control-api/src/cloudctl_api/db.py；现有migration目录；services.py商品分组逻辑`

**实施步骤**

1. 备份并统计price值格式、attributes.groupName和旧membership异常。
2. 新增price_cents BIGINT，用Decimal回填；非法记录隔离报告，不能静默置0。
3. 新建ProductGroup与ProductGroupMembership，product_id FK→product，不复用content_id。
4. 加tenant+name唯一键、membership唯一键、关联索引和FK。
5. 从可确定groupName迁移分组；category被污染但无法判定时保留原值并报告。
6. 迁移分阶段：增列/回填/双读校验/切写，备份回滚脚本齐备。
7. 同步商品DTO、仓储和查询类型，不用Python float处理金额。
8. 在SQLite开启FK和Postgres上测试upgrade及已有数据迁移。

**接口/数据契约**：price_cents为数值事实；兼容旧price输出时由Decimal格式化；商品分组和内容分组分表。

**必须执行的验收**
1. 价格20至100区间正确。
2. 商品分组不再引用帖子ID。
3. 脏值报告可追踪。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B001, B002, B008；需求：R19；来源：S03、S02。

#### T059 · P0 · CRUD、分页和批量事务一致性

前置任务：T058, T045, T006。模块：商品API。初始状态：未开始。

代码位置：`services/control-api/src/cloudctl_api/services.py商品服务与routes/schemas`

**实施步骤**

1. list提供稳定id排序的cursor/limit及搜索、状态、分组、数值价格条件。
2. 一次批量加载当前页媒体/分组，消灭每商品额外查询。
3. 统一price/stock/title/category校验，0值不被truthiness过滤。
4. PUT支持expectedRevision，冲突409且返回最新revision。
5. 单删与批删共用引用保护，锁行后预检再事务归档。
6. 权限/冲突/500不得回退成逐项删除；批量返回blockedIds或明确原子结果。
7. 复制保留媒体引用顺序、分组和定义允许复制的字段，生成新ID。
8. 测试并发修改、活跃发布引用、tenant隔离与1000条分页。

**接口/数据契约**：分页pageSize上限100为设计默认；batch API同一事务或显式逐项状态，不隐式部分成功。

**必须执行的验收**
1. 100商品页SQL常数级。
2. 单删批删保护一致。
3. 非法金额库存拒绝。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B002, B003, B016, B056；需求：R19；来源：S02、S03、S08。

#### T060 · P1 · 分组CRUD与批量membership接通

前置任务：T058, T059。模块：商品分组。初始状态：未开始。

代码位置：`apps/web/src/data/product-groups.ts及分组页；后端ProductGroup routes`

**实施步骤**

1. 新增GET/POST/PUT/archive product-groups，复用真实tenant身份。
2. 批量分组支持明确add/remove/set模式；全部目标同tenant。
3. 更名仅改group.name，禁止改Product.category。
4. 删除组归档并解除membership，不删除商品。
5. 前端改API client，所有列表/创建/更名/分组调用后端。
6. 分组筛选按groupId，不以同名字符串拼接。
7. 增加并发重名、重复add幂等、跨租户ID测试。
8. 两浏览器同步CRUD并核对数据库关系。

**接口/数据契约**：ProductGroupMembership(group_id,product_id)唯一；前端显示名不作主键。

**必须执行的验收**
1. FK开启批量分组成功。
2. 更名不改类别。
3. 跨浏览器分组一致。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B001, B011；需求：R19；来源：S19、S02、S03。

#### T061 · P0 · 编辑页完整字段持久化

前置任务：T059, T060, T044, T054, T051。模块：普通宝贝。初始状态：未开始。

代码位置：`apps/web/src/views/ProductEditView.vue；api/product-catalog.ts`

**实施步骤**

1. 按field-map列全标题/描述/规格/媒体/标签/价格成本/库存/发货相关/备注等已有字段。
2. 核心字段强类型，其它扩展字段用版本化attributes schema，禁止任意无校验JSON。
3. 新建路由清current.id与旧SPU；异步加载加epoch防串商品。
4. 图片视频统一assetId和顺序；groupId与category独立。
5. 提交expectedRevision，409保留未提交表单并提示合并，不自动覆盖。
6. 描述/标签/地址/水印默认配置存引用，发布任务才冻结具体取值。
7. 一期外按钮明确未接入；不因存了字段就称自动发货等二期功能完成。
8. 保存后刷新/换浏览器，逐字段比对读取与任务快照。

**接口/数据契约**：ProductEditorV2 field-map需附源码实际字段名，不能仅完成title/price就宣布整页完成。

**必须执行的验收**
1. 编辑转新建不覆盖旧记录。
2. 媒体可被手机使用。
3. 所有一期启用字段有roundtrip测试。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B007, B008, B009；需求：R19；来源：S10、S08。

#### T062 · P1 · 真实列表、筛选、复制和批量操作

前置任务：T059, T060。模块：商品管理。初始状态：未开始。

代码位置：`apps/web/src/商品列表视图；api/product-catalog.ts`

**实施步骤**

1. 列表查询参数传后端，不先拉全量浏览器筛选。
2. 批量选择支持当前页明确范围，跨页选择必须显示数量。
3. 批删/调价/分组调用单批API，不在catch中逐项补删。
4. 复制调用后端或保留原媒体ID，不能mediaAssetIds=[]。
5. API成功再刷新；错误显示requestId、blockedIds和字段错误。
6. 归档后列表状态一致，清缓存不能让已删数据复活。
7. 空组、价格0、小数边界和分页游标变化测试。
8. 验证1000商品首屏只取一页，网络请求与页大小无N+1。

**接口/数据契约**：前端缓存仅优化读取，不是商品事实库。

**必须执行的验收**
1. 409后不继续删除。
2. 复制有媒体。
3. 价格筛选正确。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B005, B006, B016；需求：R19；来源：S08、S02。

#### T063 · P1 · 导入预检与行级结果格式

前置任务：T059, T045。模块：导入契约。初始状态：未开始。

代码位置：`新增ImportBatch/ImportRowResult；ProductImportView字段映射`

**实施步骤**

1. 列出当前CSV/XLS/XLSX字段与别名、必填列、分组和媒体引用格式。
2. 定义预检请求schema和rowNo/column/fieldErrors，不直接落商品。
3. 金额用Decimal、数量非负整数，禁止公式求值和任意Excel宏。
4. 文件夹素材以相对路径匹配，不能只用basename覆盖同名图片。
5. 图片URL与本地文件分开来源；外链需受控ingest而非直接塞attributes。
6. 定义commit模式与批次上限，超过时拆子批并明确可部分成功。
7. idempotencyKey绑定规范化文件hash+mapping+mode，重试不重复。
8. 生成含错误/重复文件名/多图/视频/分组的标准测试样例。

**接口/数据契约**：ImportPreview{batchId,validRows,rowErrors,assetPlan}；ImportCommit引用已验证版本。

**必须执行的验收**
1. 第50行错误可定位。
2. 同名不同目录不覆盖。
3. 无媒体不假称成功。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B010；需求：R19；来源：S11、S02。

#### T064 · P1 · 批次幂等、媒体导入与事务提交

前置任务：T063, T060, T046。模块：导入后端。初始状态：未开始。

代码位置：`新增import service；现有products:import和media ingest扩展`

**实施步骤**

1. 持久化batch状态UPLOADED/VALIDATED/IMPORTING/COMPLETE/FAILED，保存输入hash。
2. 先完成媒体上传/校验，再允许提交引用；失败行报告原因。
3. 远程URL导入做协议白名单、DNS/IP私网和重定向检查、大小超时限制，防SSRF。
4. 每个受控子批事务创建商品/组/membership/media refs，使用唯一batch+rowKey。
5. 组不存在是否创建由请求显式参数决定，禁止隐式跨tenant建组。
6. 同idempotencyKey重复请求返回已有结果，不重跑成功行。
7. 返回created/updated/skipped/failed及每行productId，不只总数。
8. 测试并发重复导入、中断重启、内网URL、媒体hash错与事务回滚。

**接口/数据契约**：大文件可分批，但UI必须显示各批已提交事实；不能承诺跨无限行全局事务。

**必须执行的验收**
1. 重复导入不重复商品。
2. 无错误外键。
3. 内网URL被拒。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B010；需求：R19；来源：S02、S11。

#### T065 · P1 · 预览、提交和错误清单

前置任务：T064。模块：Web导入。初始状态：未开始。

代码位置：`apps/web/src/views/ProductImportView.vue；新增api/import-batches.ts`

**实施步骤**

1. 前端解析用于预览，服务端再次验证并返回batchId。
2. 展示列映射、相对文件路径、重复/缺失素材和逐行错误。
3. 用户确认后提交batch，不循环catalog.save。
4. 展示真实服务端进度和created/failed数量。
5. 中断刷新可按batchId恢复；重试只处理可重试失败项。
6. 下载错误清单必须转义公式前缀；原文件保留或删除按保留政策。
7. group创建使用真实API/批次选项，不调用本地createProductGroup。
8. 100行含第50行错误、同名图、重试和换浏览器E2E。

**接口/数据契约**：操作成功来自ImportBatch终态，不是本地for循环结束。

**必须执行的验收**
1. 刷新可恢复进度。
2. 错误能定位行。
3. 所有媒体形成asset引用。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B010, B057；需求：R19；来源：S11。

#### T066 · P1 · 一次性迁移旧浏览器数据

前置任务：T060, T054, T051。模块：旧数据迁移。初始状态：未开始。

代码位置：`apps/web/src/新增本地数据迁移工具；各资源import API`

**实施步骤**

1. 枚举实际localStorage键和schema版本，仅读取不立即删除。
2. 用户手动选择导出备份/预览迁移，不自动把任意本地数据当可信租户资源。
3. 后端验证所有字段并生成新ID映射；关联池/组/产品按映射更新。
4. data URL图片可转文件重新上传；已失效blob视频标缺失并要求重新提供。
5. 按browser migrationId+hash幂等导入，冲突提供跳过/另存处理。
6. 成功后写迁移标记，生产主路径不再读取旧键。
7. 旧本地任务仅导入为“历史模拟记录”，不得执行或计作真实成功。
8. 输出迁移成功/失败/缺素材清单，保留回退备份。

**接口/数据契约**：不可恢复blob不能伪造素材；数据导入不是任务补发。

**必须执行的验收**
1. 重复迁移不重复。
2. 模拟任务不被执行。
3. 缺失视频明确报告。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R19；来源：S08、S09、S19。

#### T067 · P0 · 内容修订、标题和真实归档

前置任务：T003, T045, T006。模块：帖子后端。初始状态：未开始。

代码位置：`services/control-api/src/cloudctl_api/services.py内容revision/group/archive；post schemas`

**实施步骤**

1. 复用ContentItem/Revision/ContentRevisionMedia/ContentGroup，不另建重复post事实表。
2. revision保存title/body/tags/media order/cover/videoMode及既有编辑字段。
3. 新增revision同事务同步列表摘要title/latestRevisionId。
4. expectedRevision冲突409；已创建发布任务只引用旧不可变revision。
5. list直接返回最新摘要、封面、组，服务端分页，消灭N+1 HTTP。
6. archive_content是真实删除语义；批量预检引用保护及权限。
7. ContentGroup CRUD/membership有真实API，组删除不删帖子。
8. 测试改标题/回滚历史/并发修改/归档刷新/媒体引用。

**接口/数据契约**：PostRevisionV2为发布输入；列表title不是另一套可不同步真相。

**必须执行的验收**
1. 列表详情revision标题一致。
2. 删除不复活。
3. 分页只需常数请求。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B012, B013, B014, B055；需求：R17；来源：S09、S02、S03。

#### T068 · P1 · 完整编辑器与媒体资产接入

前置任务：T067, T044。模块：帖子编辑。初始状态：未开始。

代码位置：`apps/web/src/views/PostEditorView.vue；api/post-catalog.ts`

**实施步骤**

1. 逐字段读取field-map，图文/视频模式、标题、正文、标签、封面均映射revision。
2. 选媒体使用统一上传组件；编辑保存只传assetId和顺序。
3. 保存带expectedRevision；新建清旧ID，切路由取消迟到读取。
4. 超规格媒体/未完成上传阻止保存或明确草稿状态。
5. 列表返回最新revisionId，发布只选已保存revision。
6. 分组用真实ContentGroup API，不本地分组。
7. 视频刷新后由服务端URL读取，不能保留blob业务值。
8. 两浏览器编辑冲突、多图排序、换视频、封面关联roundtrip测试。

**接口/数据契约**：只编辑不等于发布；发布动作单独有明确任务创建。

**必须执行的验收**
1. 刷新媒体可用。
2. 标题不回退。
3. 编辑后发布引用正确revision。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B015；需求：R17；来源：S12、S09。

#### T069 · P1 · 列表、分组和删除真实接通

前置任务：T067。模块：帖子管理。初始状态：未开始。

代码位置：`apps/web/src/帖子列表与分组视图；api/post-catalog.ts；data/post-groups.ts`

**实施步骤**

1. list直接消费服务端summary，不逐条get detail。
2. 分页/搜索/groupId传后端并保留筛选URL。
3. 删除调用archive API，成功后使列表缓存失效。
4. 分组CRUD/批量membership使用ContentGroup，删除组不改title。
5. 批量操作显示明确范围，冲突/引用阻止时不给假成功。
6. 生产去除saveLocal/filter式删除。
7. 旧模拟任务记录与真实帖子分开，不影响发布选择器。
8. 100条列表请求数、删除刷新、跨浏览器分组测试。

**接口/数据契约**：后端contents/groups为唯一真相；前端store仅缓存。

**必须执行的验收**
1. 删除后服务端归档。
2. 分组一致。
3. 无N+1详情请求。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B012, B014；需求：R17；来源：S09、S02。

#### T070 · P1 · CSV/Excel文本转义与导入边界

前置任务：T063, T067。模块：导出安全。初始状态：未开始。

代码位置：`导入导出共用serializer；商品/订单导出接口`

**实施步骤**

1. 文本字段以=,+,-,@或控制符开头时按目标格式安全转义。
2. 真正数值字段保持数值类型，不把所有负数当文本。
3. Excel不执行上传文件公式/宏，解析仅取允许数据。
4. 文件名、路径、content-disposition去除路径穿越/CRLF。
5. 导出按tenant权限且敏感字段脱敏。
6. 大导出流式或异步对象产物，避免一次拉全量内存。
7. 增加SUM/HYPERLINK/制表符等恶意单元测试。
8. 文档说明导出显示转义但业务原文不被悄悄改写。

**接口/数据契约**：导出安全处理作用于序列化层，不修改原始商品文案。

**必须执行的验收**
1. Excel打开无外部公式执行。
2. 金额仍可计算。
3. 越权字段不导出。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B058；需求：R19, R14；来源：S11、S02。


### 阶段 G 小红书发布

#### T071 · P0 · 单一发布笔记命令与所有入口复用

前置任务：T067, T012, T015, T046, T010。模块：命令/快照。初始状态：未开始。

代码位置：`新增xhs.publish_note参数schema与工厂；PostPublishView；授权任务入口`

**实施步骤**

1. 两处发布入口统一commandType=xhs.publish_note，不重复做任务系统。
2. 参数postRevisionId/deviceId/accountBindingId/mode/options/idempotencyKey强类型。
3. 任务创建检查账号、App探测、能力、已发布recipe、媒体READY。
4. 冻结title/body/tags/cover/media顺序/模式和recipeHash。
5. 设备一个小红书账号，无多开字段；不让用户手填App版本。
6. 按现有UI列所有发布设置并逐项映射；不支持字段明确拒绝。
7. 创建独立任务并进入同设备FIFO，与闲鱼互斥。
8. 返回taskId/snapshotHash/recipeVersion，不返回本地模拟ID。

**接口/数据契约**：xhs.publish_note.v1；result含mode、平台可得noteId/url、时间与证据；不可得字段null+reason。

**必须执行的验收**
1. 两入口生成同类真实任务。
2. 双击幂等。
3. 改帖不改变旧快照。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B017；需求：R07, R17；来源：S13、S06、S04。

#### T072 · P1 · 启动、账号核验与发布页归一化

前置任务：T071, T039, T021。模块：APK准备。初始状态：未开始。

代码位置：`版本包xiaohongshu/publish_note及页面状态定义`

**实施步骤**

1. launch官方小红书并等待前台目标包。
2. 核对当前账号与bindingVersion，不存平台密码。
3. 按已采样pageState从首页/我/其它已知页进入发布入口。
4. 已知普通提示按审核分支处理；登录/验证/未知页暂停留现场。
5. 已有编辑页先识别是否本任务检查点，不随意清空人工草稿。
6. 每步有超时/重试上限和postcondition，不能无限返回。
7. 进入发布前记录appVersion/recipeHash/evidence。
8. 从桌面、其它App、个人页、编辑中断四起点真机测试。

**接口/数据契约**：账号识别只采最小必要字段；未知状态返回PAUSED_WAITING_USER而非乱点。

**必须执行的验收**
1. 桌面起点可启动。
2. 账号错时不发布。
3. 未知弹窗可接管。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R10, R11, R17；来源：S29、S28。

#### T073 · P0 · 多图选择与标题正文标签填入

前置任务：T072, T048, T023。模块：图文笔记。初始状态：未开始。

代码位置：`xiaohongshu/publish_note图文分支及input helpers`

**实施步骤**

1. 按IMAGE模式进入相册，定位任务相册。
2. 按snapshot顺序选择图片，核对数量和预览，失败停下。
3. 等待处理完成进入编辑页，不使用固定sleep当唯一判断。
4. 逐项输入title/body并读回可得文本；中文emoji和换行校验。
5. 标签按真实UI添加且防重复#；封面按snapshot选择。
6. 当前UI已启用的可见性等设置逐字段消费，不擅自默认。
7. 每个可恢复阶段保存检查点，内容填好但未发布时可接管恢复。
8. 截图保存最终提交前页面，交给final commit分支。

**接口/数据契约**：图文Recipe不包含未经commit_guard保护的最终发布点击。

**必须执行的验收**
1. 有旧图库仍选对。
2. 文案标签读回一致。
3. 中断后不重新选重复图片。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R05, R17；来源：S13、S29。

#### T074 · P1 · 视频选择、处理等待和封面

前置任务：T072, T048, T023。模块：视频笔记。初始状态：未开始。

代码位置：`xiaohongshu/publish_note视频分支`

**实施步骤**

1. 后端按目标recipe支持格式/时长预检，不臆造所有版本通用限制。
2. 选择唯一任务视频并验证媒体身份。
3. 等待客户端处理/转码页面状态，设置可配置总超时。
4. 处理进度可见时上报；进度不可见不编百分比。
5. 进入编辑后填title/body/tags并应用可支持封面。
6. 处理中暂停需保存阶段；恢复先判断是否已完成处理，不能重新导入。
7. 超时保存证据，选择人工接管或可判定重试，不误报发布失败可直接重发。
8. 真机测试受支持视频、过规格、处理慢、弱网四种。

**接口/数据契约**：VIDEO模式为一期素材能力；平台不支持的格式明确错误，不能静默丢弃视频。

**必须执行的验收**
1. 真实视频笔记可发布。
2. 转码慢不假成功。
3. 恢复不重复导入。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R12, R17；来源：S12、S13。

#### T075 · P0 · 发布/草稿成功判断和恢复

前置任务：T073, T074, T024, T025, T050。模块：最终提交。初始状态：未开始。

代码位置：`xiaohongshu/publish_note final分支；typed result mapper`

**实施步骤**

1. 提交前验证同账号/租约/recipeHash和最终页面内容。
2. DIRECT写action intent再点发布；DRAFT仅走保存草稿路径。
3. 等待明确成功后置条件或在列表核验结果，不把按钮点击当成功。
4. 可取得noteId/url则保存，取不到以null+reason和证据报告。
5. 点击后断网/崩溃进入RECONCILING，不自动重复发布。
6. resume先判断已提交/仍编辑/未知，按同task恢复。
7. 结果带媒体数、快照hash、模式、时间、证据和实际可得平台标识。
8. 连续运行及断点注入测试，人工确认结果必须审计。

**接口/数据契约**：draft保存和实际发布两种结果不能混用；未知提交结果不是FAILED可随意重试。

**必须执行的验收**
1. DIRECT真实发布。
2. DRAFT不误发布。
3. 丢complete不重复发。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R05, R17；来源：S13、S26。

#### T076 · P0 · 选择帖子设备、下发和看执行

前置任务：T071, T075, T028, T038。模块：Web发布。初始状态：未开始。

代码位置：`apps/web/src/views/PostPublishView.vue；小红书授权发布入口`

**实施步骤**

1. 读取真实已保存post revision和设备账号状态。
2. 即时/预约/周期用统一schedule组件；每设备单独任务。
3. 提交前展示内容摘要、媒体和账号；生成稳定idempotencyKey。
4. 调用真实create API，删除仅save/record local任务路径。
5. 进入任务详情显示队列、当前步骤、投屏、失败证据。
6. 未知页面提供暂停接管与继续原任务。
7. 成功显示实际结果；缺平台ID不能伪造链接。
8. 刷新与第二浏览器查询同任务，完整图文和视频E2E。

**接口/数据契约**：发布页不自行生成点击步骤；云端不逐步控制小红书UI。

**必须执行的验收**
1. 电脑创作→手机发布→网页结果闭环。
2. 定时可用。
3. 观看不影响执行。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B017；需求：R03, R09, R17；来源：S13。


### 阶段 H 闲鱼全功能

#### T077 · P0 · 所有闲鱼任务工厂和页面字段映射

前置任务：T012, T013, T039, T020, T010。模块：统一接入。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue；XianyuExtraTaskView.vue；后端XianyuCommandFactory`

**实施步骤**

1. 按operations-catalog原ID保留31项入口并登记commandType或共享模块。
2. 为simple/extra每个kind写独立params schema，不能一个无约束options包所有功能。
3. 逐v-model映射UI→DTO→快照→Recipe动作→结果测试。
4. 创建时验证账号、绑定版本、兼容recipe、执行范围、预算和操作确认。
5. 即时/定时/周期共用调度，单设备FIFO；多设备生成独立task。
6. 前端共用真实任务列表与状态，不调用record*作为事实。
7. 涉及删除/消耗/评价使用明确确认和item级commit guard。
8. CI枚举全部kind，没有映射/测试的入口保持待实现，不允许假成功。

**接口/数据契约**：xianyu.*.v1参数按动作分型；选择“只打开页面”必须返回OPEN_ONLY而非执行成功。

**必须执行的验收**
1. 所有kind有schema和路由映射。
2. 旧blocked功能纳入开发。
3. 不启用无实现字段。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B019, B020；需求：R07, R09, R16；来源：S15、S16、S17、S20。

#### T078 · P0 · 完整商品发布快照与接口

前置任务：T077, T061, T052, T055, T056, T057, T046。模块：发布商品。初始状态：未开始。

代码位置：`xianyu.publish_goods factory；apps/web/src/data/xianyu-publish-goods.ts`

**实施步骤**

1. 盘点当前publish表单全部字段，含发布模式/目标/文案/地址/标签/媒体/规格等。
2. 读取商品revision与绑定账号；构造最终title/description/price等。
3. 服务端选地址/描述/标签条目并冻结选中值。
4. 按水印profile生成或等待derivative，冻结最终assetIds。
5. 区分DIRECT/DRAFT及其它现有模式，未支持模式拒绝而非忽略。
6. 创建MediaDelivery和独立任务，关联既有PublishPlan/Target/提交账本。
7. 响应autoPublish/tapsPublish由真实模式生成，移除硬编码false。
8. 测试创建后改产品/池/账号绑定，旧任务不漂移且错误换绑被阻止。

**接口/数据契约**：XianyuPublishSnapshotV1记录productRevision、resolved文案/地址/标签、outputAssets、mode、bindingVersion。

**必须执行的验收**
1. 快照可独立解释发什么。
2. UI字段不丢。
3. 响应与真实发布行为一致。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B018, B041；需求：R16, R19；来源：S14、S18、S07、S02。

#### T079 · P0 · 启动闲鱼、媒体选择和字段填写

前置任务：T078, T021, T048, T023。模块：发布商品。初始状态：未开始。

代码位置：`版本化xianyu/publish_goods recipe及locator fixtures`

**实施步骤**

1. 拉起闲鱼并核验当前账号，从已知页面归一化到发布入口。
2. 遇已知提示处理，验证码/登录/未知页面暂停保留现场。
3. 定位任务相册并按快照顺序选图/视频，核对数量与身份。
4. 填写最终标题/描述/价格等基础字段并读回。
5. 按快照设置地址/标签/规格及现有UI支持选项，不能APK再随机。
6. 每一阶段保存检查点与当前商品身份，人工返回可校验恢复。
7. 平台不支持的选项返回UNSUPPORTED_OPTION与证据，不悄悄略过。
8. 到最终确认页截屏，提交交commit步骤，不在helper里隐藏点击发布。

**接口/数据契约**：发布填写与最终提交明确分离；所有定位引用已发布版本包。

**必须执行的验收**
1. 从桌面自动拉起。
2. 选图无错。
3. 输入字段与快照一致。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R05, R16；来源：S07、S29、S18。

#### T080 · P0 · 直发/草稿、提交判定与结果

前置任务：T079, T024, T025, T050。模块：发布商品。初始状态：未开始。

代码位置：`xianyu/publish_goods final分支；旧dispatch_post_to_xianyu适配`

**实施步骤**

1. 复核目标账号、租约epoch和提交前页面，写稳定action intent。
2. DIRECT只点击一次发布；DRAFT走保存草稿路径。
3. 等待真实成功页/在售或草稿列表核验，不只找toast就全部成功。
4. 可得listingId/url写结果，不可得记录null原因与证据。
5. 点击后断网/进程退出进RECONCILING，不自动重发。
6. 旧low-level dispatch通过统一任务与锁，禁止与新recipe双执行。
7. 响应tapsPublish和结果mode一致；部分填表不当发布成功。
8. 测试DIRECT、DRAFT、二次重试、丢ACK和人工继续。

**接口/数据契约**：XianyuPublishResult{mode,status,listingId?,publishedAt?,snapshotHash,evidenceRefs}。

**必须执行的验收**
1. 实际直发与草稿行为匹配。
2. 不重复发布。
3. 旧API也遵守单writer。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B041；需求：R05, R16；来源：S07、S02、S26。

#### T081 · P1 · 真实下发、排队和执行观察

前置任务：T080, T028, T038。模块：Web发布商品。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuPublishGoodsView.vue；api/xianyu-tasks.ts（新增）`

**实施步骤**

1. 商品/设备/账号选择全部取真实API，不使用示例列表作为提交数据。
2. 显示最终选项和发布模式，校验必填/媒体状态。
3. 共用schedule提交即时/预约/周期配置。
4. POST真实factory，双击用幂等键防重复。
5. 删除“不会下发手机”提示和本地record执行路径。
6. 任务列表显示真实queue/running/pause/result，能打开投屏。
7. 接管后继续原task，失败不一律提供从头重跑。
8. 以真实闲鱼账号图文/视频及池水印任务做端到端验收。

**接口/数据契约**：UI保存发布配置可以有后端模板；配置模板不是已创建执行任务。

**必须执行的验收**
1. 从该页面能真正发布。
2. 刷新有历史。
3. 设置均被消费。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B018；需求：R03, R09, R16；来源：S14、S18。

#### T082 · P1 · 擦亮商品真实执行

前置任务：T077, T023, T024。模块：xy-tasks-03。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.polish`

**实施步骤**

1. 以xy-tasks-03入口为准，字段目标范围、商品过滤条件、数量/轮次/间隔（严格映射原字段）写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 进入实际在售管理页，按账号与listingId确定目标；无稳定ID时记录指纹并避免标题猜测。
3. 按页面已定义曝光/想要/收藏等筛选条件生成有上限目标清单，不擅改筛选语义。
4. 逐项查看是否可擦亮；已完成/今日不可操作记SKIPPED并记录原因。
5. 可操作项执行一次擦亮并等待成功后置条件，再写item journal。
6. 列表滚动使用seen IDs和页面fingerprint，达到数量/无更多即止。
7. 暂停保存当前listing与游标；恢复不重做已成功项。
8. 接真实任务状态和result，测试已擦亮、部分不可用、分页和中断。

**接口/数据契约**：xianyu.polish.v1；字段：目标范围、商品过滤条件、数量/轮次/间隔（严格映射原字段）；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 符合条件商品真实擦亮。
2. 已完成不重复。
3. 结果计数与清单一致。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T083 · P1 · 上架商品

前置任务：T077, T023, T024。模块：xy-tasks-04。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.shelf_up`

**实施步骤**

1. 以xy-tasks-04入口为准，字段待上架范围、数量、过滤条件、间隔写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 归一化到已下架/可上架列表，确认不是在售列表。
3. 按listing身份和配置选目标，冻结清单或记录可恢复扫描游标。
4. 检查当前状态，已上架记ALREADY_APPLIED，不再重复提交。
5. 打开商品操作菜单，核对标题/标识后执行上架。
6. 等待在售状态或在售列表中可核验结果，不把菜单关闭当成功。
7. 按item journal和安全检查点处理暂停/断网，不重复成功项。
8. Web真实下发并显示逐项结果；测试已上架、资格不足和确认页中断。

**接口/数据契约**：xianyu.shelf_up.v1；字段：待上架范围、数量、过滤条件、间隔；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 目标商品状态真实变在售。
2. 非目标不受影响。
3. 部分失败可追踪。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T084 · P1 · 下架商品

前置任务：T077, T023, T024。模块：xy-tasks-05。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.shelf_down`

**实施步骤**

1. 以xy-tasks-05入口为准，字段在售范围、过滤条件、数量、间隔写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 进入在售商品列表并验证当前账号。
3. 按配置生成目标清单，预览数量；删除与下架命令严格分开。
4. 逐项打开更多菜单并核对listing身份，已下架记skip。
5. 确认框前写intent和证据，仅确认下架不点相邻删除。
6. 等待状态已下架或列表核验，未知结果进入核对。
7. 保存分页/当前item状态，恢复从未完成目标继续。
8. 真机测试筛选、已下架、下架后丢ACK与人工继续。

**接口/数据契约**：xianyu.shelf_down.v1；字段：在售范围、过滤条件、数量、间隔；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 只下架指定项。
2. 不误删。
3. 丢ACK不盲目二次操作。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T085 · P1 · 删除商品

前置任务：T077, T023, T024。模块：xy-tasks-06。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.delete_goods`

**实施步骤**

1. 以xy-tasks-06入口为准，字段目标范围、数量、确认标志、过滤条件写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 后端冻结待删范围和明确用户确认，不接受默认删全且无提示。
3. 进入目标列表，按稳定身份定位；标题相同多项必须区分。
4. 打开删除菜单，最终确认前截图并写item intent。
5. 确认文字/目标无误才执行一次删除，未知页面停止。
6. 检查目标不存在或明确删除成功；结果不确定等待核对。
7. 任务恢复用item journal跳过已删项，列表位置变化不可按旧index删下一个。
8. 接真实API/result；用测试商品做相邻菜单/重名/断网/暂停验收。

**接口/数据契约**：xianyu.delete_goods.v1；字段：目标范围、数量、确认标志、过滤条件；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 仅删确认目标。
2. 列表重排不误删。
3. 不可逆动作有证据。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T086 · P1 · 绑定闲鱼账号

前置任务：T077, T010, T011, T023。模块：xy-tasks-08。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.bind_account`

**实施步骤**

1. 以xy-tasks-08入口为准，字段deviceId、当前平台账号探测、换绑确认、expectedBindingVersion写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 拉起闲鱼并进入可识别账号页面，不采集密码。
3. 读取最小可用账号标识；仅昵称不唯一时不能直接合并账号。
4. 未登录/验证码暂停等待用户，不自动绕过授权。
5. 云端查找或创建同tenant平台账号，展示当前旧绑定与新身份。
6. 换绑必须确认并事务解除旧绑定/建立新绑定，递增bindingVersion。
7. 保留原账号历史，已排队旧账号任务不自动改为新账号执行。
8. 测试首次绑定、同账号重复绑定、甲换乙以及并存小红书绑定。

**接口/数据契约**：xianyu.bind_account.v1；字段：deviceId、当前平台账号探测、换绑确认、expectedBindingVersion；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 一个闲鱼当前绑定。
2. 旧历史不迁移。
3. 不会泄露密码。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T087 · P1 · 签到鱼币

前置任务：T077, T023, T024。模块：xy-tasks-09。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.coin_checkin`

**实施步骤**

1. 以xy-tasks-09入口为准，字段执行账号、日期/周期、原页面其它有效选项写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 进入鱼币/签到页，读取当前可见签到状态与日期语义。
3. 今日已签到返回ALREADY_APPLIED，并留状态证据。
4. 未签到核对目标按钮，按账号+平台日期定义日级actionKey。
5. 点击一次签到，等待积分/签到状态变化，不承诺固定鱼币数量。
6. 平台活动不存在或需人工步骤时返回可解释状态，不能假加积分。
7. 未知弹窗/验证暂停；恢复先核验今日状态再决定是否需要点击。
8. 取消旧blocked假限制但保留权限/兼容校验，测试已签到和新签到。

**接口/数据契约**：xianyu.coin_checkin.v1；字段：执行账号、日期/周期、原页面其它有效选项；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 已签到不重复。
2. 签到可得结果真实。
3. 平台入口缺失可见。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T088 · P1 · 鱼币抵扣

前置任务：T077, T023, T024。模块：xy-tasks-10。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.coin_discount`

**实施步骤**

1. 以xy-tasks-10入口为准，字段目标商品、抵扣模式不抵扣/10%/20%/30%/只打开页面（以现有枚举为准）写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 参数枚举原样映射，OPEN_ONLY只导航并返回不操作结果。
3. 进入目标商品抵扣设置，读取当前状态与适用资格。
4. 已为期望模式则跳过；不可用记录NOT_ELIGIBLE而不点击邻近菜单。
5. 计算并展示实际会变更的设置；不得把抵扣率当商品价格改动。
6. 提交前证据和item intent；保存后重新读取抵扣状态。
7. 恢复根据已设置状态防重复；账号或商品不符立即暂停。
8. 测试全部现有枚举、已设置、不支持商品和只打开模式。

**接口/数据契约**：xianyu.coin_discount.v1；字段：目标商品、抵扣模式不抵扣/10%/20%/30%/只打开页面（以现有枚举为准）；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 每种模式语义正确。
2. OPEN_ONLY无设置改变。
3. 不误改价格。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T089 · P1 · 鱼币推广

前置任务：T077, T023, T024。模块：xy-tasks-11。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.coin_promote`

**实施步骤**

1. 以xy-tasks-11入口为准，字段商品筛选/排序、推广包或时长、最大鱼币预算、逐项确认写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 后端冻结目标商品、推广参数和预算，预算是明确可验证限制。
3. 进入推广页面读取实际当前可用套餐及成本，不依赖旧硬编码价格。
4. 套餐不匹配、余额不足或价格变化则暂停等待确认，不自动换更贵方案。
5. 最终消耗前截图核验商品/数量/费用，并写稳定action intent。
6. 仅确认一次，等待推广记录/平台状态核验，实际消耗可得才填结果。
7. 断网不确定扣费进RECONCILING，预算按已确认+未知上界保守计算。
8. 用用户授权测试账号验证预算、余额不足、取消和丢ACK，无自动越预算。

**接口/数据契约**：xianyu.coin_promote.v1；字段：商品筛选/排序、推广包或时长、最大鱼币预算、逐项确认；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 不超明确预算。
2. 不确定扣费不重复提交。
3. 套餐变化暂停。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T090 · P1 · 一键小刀（非降价）

前置任务：T077, T023, T024。模块：xy-tasks-12。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.bargain_setting`

**实施步骤**

1. 以xy-tasks-12入口为准，字段打开/关闭/指定小刀参数/只打开页面及目标商品（以原枚举为准）写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 从原字段确认小刀设置语义，与一键降价分别建schema。
3. 进入商品小刀相关设置页并读取当前启停/参数。
4. OPEN_ONLY仅打开；相同设置返回ALREADY_APPLIED。
5. 对需要修改的目标设置开关或数值，不能直接改商品售价冒充小刀。
6. 提交前核对值和商品身份，写intent并保存。
7. 读回设置确认；恢复先查当前状态，避免重复改动。
8. 测试每个现有模式和不支持入口；Web明确显示设置结果而非降价结果。

**接口/数据契约**：xianyu.bargain_setting.v1；字段：打开/关闭/指定小刀参数/只打开页面及目标商品（以原枚举为准）；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 小刀与降价逻辑分开。
2. 设置值读回正确。
3. OPEN_ONLY不操作。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T091 · P1 · 一键降价

前置任务：T077, T023, T024。模块：xy-tasks-13。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.price_cut`

**实施步骤**

1. 以xy-tasks-13入口为准，字段商品范围、按金额或百分比、最低价、数量/间隔写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 明确金额与百分比互斥选择；Decimal计算，限制降价后非负且不低于明确底价。
3. 执行时读取当前实际价格，与任务前置条件对比，变化时暂停或按显式策略重算。
4. 逐目标生成旧价/新价确认与item actionKey，不能以重复执行同百分比继续降价。
5. 进入价格编辑并输入规范金额，读回确认。
6. 提交一次并重新核验实际价格；不确定结果保留核对状态。
7. 恢复使用冻结新价，不基于已经降过的价格再次扣减。
8. 测试金额/百分比/底价/小数/价格被人工改动及断网重复。

**接口/数据契约**：xianyu.price_cut.v1；字段：商品范围、按金额或百分比、最低价、数量/间隔；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 重试不二次降价。
2. 底价有效。
3. 每项旧新价可查。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T092 · P1 · 一键好评

前置任务：T077, T023, T024。模块：xy-tasks-14。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.review_order`

**实施步骤**

1. 以xy-tasks-14入口为准，字段真实已完成订单范围、评价内容、数量、原页面评价选项写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 只处理当前账号真实可评价交易，不创建虚假交易或批量伪造互动。
3. 冻结用户指定评价文本和订单清单；评价文案与自动私信分开。
4. 对原界面可能存在互评/推广私信，不默认群发；非交易必要消息明确不执行。
5. 进入待评价订单并核对订单身份，已评价记skip。
6. 提交前截图/intent，真实评价只提交一次；平台要求人工验证则暂停。
7. 查评价完成状态，丢ACK先核对，恢复不再次评价同订单。
8. 测试买/卖侧可评价订单、已评价、空列表和中断；返回逐订单结果。

**接口/数据契约**：xianyu.review_order.v1；字段：真实已完成订单范围、评价内容、数量、原页面评价选项；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 真实订单评价可追踪。
2. 不重复评价。
3. 不默认发送互评推广私信。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T093 · P1 · 重启闲鱼的权限边界

前置任务：T077, T023, T024。模块：xy-tasks-15。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.relaunch_app`

**实施步骤**

1. 以xy-tasks-15入口为准，字段设备/账号、导航恢复模式、原有等待选项写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 区分可实现的回桌面再拉起与系统强制停止；普通权限不能保证force-stop。
3. 任务前检查没有另一个AUTO writer或未暂停的发布提交。
4. 执行Home并通过允许的launch intent重新进入闲鱼。
5. 等待前台包和首页状态，已知启动弹窗处理，未知暂停。
6. 如需求实际依赖清进程且设备无能力，返回CAPABILITY_UNAVAILABLE，不假称已杀进程。
7. 保持账号登录态与云控身份，不清App数据、不删除缓存冒充重启。
8. 结果明确method=RELAUNCH及实际状态，测试App后台/前台/未安装。

**接口/数据契约**：xianyu.relaunch_app.v1；字段：设备/账号、导航恢复模式、原有等待选项；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 有权限范围内确实重新拉起。
2. 不宣称无权force-stop。
3. 不丢账号数据。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T094 · P1 · 删除动态

前置任务：T077, T023, T024。模块：xy-tasks-16。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.delete_feed`

**实施步骤**

1. 以xy-tasks-16入口为准，字段动态范围、数量/轮次、筛选、明确删除确认写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 进入个人动态而不是商品/帖子列表，确认pageState。
3. 按稳定动态标识或可验证指纹建立待删清单；同内容多项不按标题合并。
4. 逐项进入更多删除菜单，确认目标与用户范围。
5. 最终确认前journal+截图，删除后核验消失。
6. 列表变化重新定位下一item，不按固定行index继续删。
7. 分页设seen/最大轮次；恢复跳过已确认删除项，未知结果先核对。
8. 测试空动态、重名动态、分页与第N项暂停；Web显示实际删除数。

**接口/数据契约**：xianyu.delete_feed.v1；字段：动态范围、数量/轮次、筛选、明确删除确认；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 不误删商品/消息。
2. 分页有界。
3. 每项结果可追踪。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T095 · P1 · 删除消息/处理小红点

前置任务：T077, T023, T024。模块：xy-tasks-17。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.message_action`

**实施步骤**

1. 以xy-tasks-17入口为准，字段messageAction=删除对话框或点开小红点、数量/轮次、筛选写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. schema区分DELETE_CONVERSATION与OPEN_UNREAD，后者不执行删除。
3. 进入消息列表，选符合范围会话，用稳定会话身份记录。
4. OPEN_UNREAD打开并检查已读状态后返回，避免发送任何消息。
5. DELETE核对会话后执行确认删除，提前journal和证据。
6. 返回列表重新识别，防删后重排导致误删邻居。
7. 暂停/恢复保留已处理集合；不确定删除先核对，不重播长按。
8. 测试两种动作、空未读、同名会话及断网，结果按动作分类。

**接口/数据契约**：xianyu.message_action.v1；字段：messageAction=删除对话框或点开小红点、数量/轮次、筛选；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 点红点不删除。
2. 删除范围正确。
3. 不自动发送消息。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T096 · P1 · 删除留言

前置任务：T077, T023, T024。模块：xy-tasks-18。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.delete_comment`

**实施步骤**

1. 以xy-tasks-18入口为准，字段留言目标范围、数量、轮次、确认标志写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 进入实际留言/评论管理入口，区分消息会话。
3. 按商品/留言身份与时间等可见字段定位目标，歧义暂停。
4. 逐留言打开操作菜单，确认是否允许删除。
5. 记录intent后一次确认删除，等待该留言消失或明确成功。
6. 遇无权限/已删除记具体skip，不无限重试。
7. 分页fingerprint与已处理ID防循环；恢复定位原item而非旧位置。
8. 测试多个商品留言、无权删除、分页和中断；返回逐项证据。

**接口/数据契约**：xianyu.delete_comment.v1；字段：留言目标范围、数量、轮次、确认标志；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 不误删会话。
2. 无权不乱点。
3. 恢复不跳错项。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T097 · P1 · 草稿上架

前置任务：T077, T023, T024。模块：xy-tasks-19。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.publish_draft`

**实施步骤**

1. 以xy-tasks-19入口为准，字段草稿选择、数量、发布选项、账号和确认写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 进入草稿列表，读取可得草稿标识并冻结目标。
3. 打开草稿校验内容/媒体与目标，不用列表第一个代替指定草稿。
4. 已有发布结果则先核对，避免把同草稿重复上架。
5. 按允许选项补齐必填项；缺素材/平台验证时暂停。
6. 最终发布走共用commit guard，记录草稿→listing结果映射。
7. 发布后从草稿消失不单独当成功，需在售/成功页核验。
8. 中断恢复先判断已发布还是仍草稿；测试多草稿顺序和丢ACK。

**接口/数据契约**：xianyu.publish_draft.v1；字段：草稿选择、数量、发布选项、账号和确认；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 指定草稿真实上架。
2. 不误发相邻草稿。
3. 重试不重复。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T098 · P1 · 编辑重发

前置任务：T077, T023, T024。模块：xy-tasks-20。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.edit_republish`

**实施步骤**

1. 以xy-tasks-20入口为准，字段目标商品、允许修改字段、地址/文案选项、次数写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 冻结原listing身份和最终修改值，地址/描述池在云端已选定。
3. 进入原商品编辑页，核对是编辑原条目还是平台另建发布路径。
4. 只修改用户勾选字段，未选字段保留，不把空值当清空指令。
5. 读回关键字段并保存检查点，人工介入后再次核验。
6. 最终保存/重发按平台实际路径执行commit guard，旧新listing映射保留。
7. 未知结果先核对，不从头另发一条；结果写真实模式。
8. 测试只改价格/描述/地址、未选字段不变、暂停和重试。

**接口/数据契约**：xianyu.edit_republish.v1；字段：目标商品、允许修改字段、地址/文案选项、次数；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 未选字段不丢。
2. 旧新条目关系可查。
3. 不重复重发。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T099 · P1 · 托管无忧卖

前置任务：T077, T023, T024。模块：xy-tasks-21。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.wuyoumai`

**实施步骤**

1. 以xy-tasks-21入口为准，字段加入/退出/只打开、商品范围、明确条款确认写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 检查当前版本是否有入口和账号/商品资格，不存在返回NOT_SUPPORTED证据。
3. OPEN_ONLY只导航；加入/退出分别读取当前状态。
4. 已处于目标状态记skip，资格不足记录NOT_ELIGIBLE。
5. 涉及新增协议、费用或寄送确认时暂停由用户决定，不自动接受未知条款。
6. 只有已明确授权的设置动作才提交并写item intent。
7. 读回托管状态，无法确认标uncertain，恢复先查状态。
8. 测试加入、退出、只打开、无资格和条款变化，Web不假成功。

**接口/数据契约**：xianyu.wuyoumai.v1；字段：加入/退出/只打开、商品范围、明确条款确认；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 不接受未知条款。
2. 状态核验真实。
3. 不可用入口明确受阻。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T100 · P1 · 快速编辑重发

前置任务：T077, T023, T024。模块：xy-tasks-22。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.fast_republish`

**实施步骤**

1. 以xy-tasks-22入口为准，字段目标范围、快速路径选项、修改字段、数量写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 复用编辑重发参数和item身份核验，不复制一套不兼容规则。
3. 只在当前App版本有已认证快速入口时使用，普通入口回退须明确记录。
4. 批量每item读取并写冻结修改值，保持未勾选字段。
5. 最终保存/发布共用commit guard，不能用速度理由跳过确认。
6. 每item结果立即持久化，上报partial counts，失败不中断已成功事实。
7. 暂停保存当前item；恢复不再处理成功集合。
8. 测试快速入口不存在、列表重排、部分失败和重试。

**接口/数据契约**：xianyu.fast_republish.v1；字段：目标范围、快速路径选项、修改字段、数量；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 快速也不重复提交。
2. 逐项结果可查。
3. 没有入口不盲点。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T101 · P1 · 快速下架商品

前置任务：T077, T023, T024。模块：xy-tasks-23。初始状态：未开始。

代码位置：`apps/web/src/views/XianyuSimpleTaskView.vue或XianyuExtraTaskView.vue（按operation映射）；新增版本化Recipe xianyu.fast_shelf_down`

**实施步骤**

1. 以xy-tasks-23入口为准，字段目标范围、数量/过滤条件、间隔写强类型schema和Web映射；完成租户/账号/版本/范围校验。
2. 复用普通下架目标解析和状态核验，明确本次最大处理数。
3. 当前版本存在批量管理入口则核对所选商品ID/数量，否则用认证逐项路径。
4. 最终下架前冻结已选择清单，防虚拟列表滚动改选中目标。
5. 确认一次并逐目标读取实际状态，不以批量按钮反馈推断全部成功。
6. partial成功分别写item journal，剩余目标可继续。
7. 未知结果核对后再续，不能整批从头下架。
8. 测试全成功/部分失败/已下架/滚动后选择变化及暂停。

**接口/数据契约**：xianyu.fast_shelf_down.v1；字段：目标范围、数量/过滤条件、间隔；结果必须含每item的done/skipped/failed/uncertain与证据，OPEN_ONLY单独状态。

**必须执行的验收**
1. 选择范围准确。
2. partial不假全成功。
3. 成功项不重复。

**交付物**：schema+后端工厂+Web真实调用+已签名Recipe草稿+fixture测试；真机通过并由用户发布后方可标完成。

关联问题：新增实现/联调；需求：R16, R05；来源：S20、S15、S16、S17、S29。

#### T102 · P1 · 发布/删除闲鱼帖子的可用性验证与实现门槛

前置任务：T004, T039, T077。模块：旧帖子功能。初始状态：未开始。

代码位置：`xy-tasks-02/07入口；目标版本页面采样；相应Recipe或能力报告`

**实施步骤**

1. 旧仓库标retired只是历史说明，用户未确认排除；保持两项可追踪。
2. 在实际账号/版本检查是否仍存在用户所说闲鱼帖子发布和删除入口。
3. 记录入口路径、页面截图、版本和日期，不用网页文案替代真机证据。
4. 若存在，分别定义publish_post/delete_post schema并复用媒体、检查点与commit guard。
5. 发布字段按当前真实入口映射；删除必须核对post身份及明确确认。
6. 若平台确无入口，回报NOT_SUPPORTED+证据并在任务表标阻塞，不能标已完成实现。
7. 不得将闲鱼商品发布偷换成帖子发布凑覆盖。
8. 更新31项覆盖表：可实现路径与不可实现证据都保留，避免静默删需求。

**接口/数据契约**：是否平台支持是待真机验证事项，不是向用户再发需求问卷。

**必须执行的验收**
1. 两项都有证据和状态。
2. 有入口完成真实闭环。
3. 无入口不伪造成功。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B053；需求：R16；来源：S20。

#### T103 · P1 · 词库规则后端化与发布前检查

前置任务：T054, T067, T059。模块：违禁词检测。初始状态：未开始。

代码位置：`xy-tasks-30；新增词库revision/scan API；复用现有相关页面`

**实施步骤**

1. 清点当前词库和检测UI字段，建立tenant规则+可版本化基础规则。
2. 保存term/matchMode/severity/enabled，禁止任意执行正则造成无界耗时。
3. 扫描返回命中位置/规则版本/等级，不宣称涵盖所有平台审核规则。
4. 商品/帖子编辑提供提示，最终任务快照创建再扫描最终文案。
5. 阻止级规则不能客户端绕过；可确认级记录用户确认与版本。
6. 已创建任务保留原检测结果，不因词库改动篡改历史。
7. 页面CRUD/检测都调真实API，错误不能返回假“无违禁词”。
8. 测试中文边界、超长文本、恶意模式和规则变更。

**接口/数据契约**：词库检测是辅助业务规则，不是绕过平台审核工具或发布保证。

**必须执行的验收**
1. 命中可定位。
2. 检测失败不视为通过。
3. 版本可追溯。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R16, R19；来源：S20。

#### T104 · P1 · 31项入口和共享功能交付对照

前置任务：T077, T102, T103, T053, T055, T056, T057。模块：目录收敛。初始状态：未开始。

代码位置：`apps/web/src/data/operations-catalog.ts；导航/状态标签；帮助内容`

**实施步骤**

1. 01映射商品发布；02/07映射实际可用性结果；03至23各自真实命令。
2. 24关联宝贝采集，25至29关联通用地址/设备地址/描述/标签/水印共享服务。
3. 30关联违禁词检测；31保留真实版本对应的视频教程，不当成手机执行任务。
4. 旧blocked标签不永久阻挡已实现的签到/推广/好评；权限/预算仍生效。
5. 未完成或平台不可用显示准确状态，不发模拟成功记录。
6. 每个条目关联TaskID与验收证据，CI检查新增菜单未映射。
7. 教程只用真实操作录制/说明，不能引用不存在文件路径。
8. 按31项逐项点击检查路由、权限、后端调用和状态。

**接口/数据契约**：目录项数量与命令数量不同：共享资源/帮助不是新的mobile task。

**必须执行的验收**
1. 31项不漏号。
2. 无假可用按钮。
3. 共享模块不重复存储。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R16, R20；来源：S20。


### 阶段 I 订单与统计

#### T105 · P0 · 完整可见字段与账号归属

前置任务：T011, T006。模块：订单模型。初始状态：未开始。

代码位置：`services/control-api/src/cloudctl_api/新增PlatformOrder/OrderSyncRun/OrderObservation及migration`

**实施步骤**

1. 定义订单业务主键tenant+platform+accountId+platformOrderId；角色字段buyer/seller独立保存。
2. 字段覆盖可见订单号、商品/规格、金额/运费/实付、买卖方、状态时间、物流及正常可见收货信息。
3. 金额用cents、时间带时区；敏感收货字段单独加密与脱敏权限。
4. 未提供/被遮挡/无权限/解析失败存null+reason，不能补0或猜手机号。
5. 保留sourceRole、capturedAt、appVersion、schemaVersion和必要原始可见文本。
6. 订单当前状态可upsert，重要变更保留observation用于历史追踪。
7. 账号解绑不迁移历史；新绑定账号有独立数据空间。
8. 建立分页/时间/状态索引，测试重复ID、换绑和敏感字段授权。

**接口/数据契约**：“全部字段”指正常授权页面可获得字段，不承诺获取平台未开放/隐藏数据。

**必须执行的验收**
1. 订单不串账号。
2. 缺字段与0区分。
3. 敏感信息受控。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B045；需求：R10, R13, R14；来源：S02、S03、S20。

#### T106 · P0 · 全部/指定N及分批幂等入库

前置任务：T105, T012, T014, T017。模块：同步API。初始状态：未开始。

代码位置：`新增order-sync-runs/create/batches/complete；xianyu.sync_orders factory`

**实施步骤**

1. limit=null表示全部；N为正整数；默认按可见订单时间倒序去重计数。
2. 角色默认ALL_VISIBLE为设计默认，UI可筛卖出/买入，不假称用户已经选定角色。
3. 创建run和独立设备task，冻结account/binding、范围、字段版本和排序。
4. batches带runId/batchSeq/items/cursor/hash；相同seq相同hash幂等，不同hash冲突。
5. 每批事务upsert订单并保存游标，敏感字段按策略加密。
6. N按独立订单ID计数，跨页面重复不占额度。
7. 安全页数上限/平台无更多/权限受限分别返回stopReason；部分扫描complete=false。
8. complete校验上传数量和状态，不允许客户端直接报全部成功掩盖漏批。

**接口/数据契约**：OrderSyncParams{scope,limit:null|N,roles,fieldsProfile}；BatchAck{accepted,duplicates,cursor}；Summary{complete,stopReason,uniqueCount}。

**必须执行的验收**
1. 重复batch不重复。
2. N准确。
3. 中断可续且不假全部。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B045；需求：R09, R14；来源：S04、S06。

#### T107 · P0 · 列表+详情采集和断点恢复

前置任务：T106, T039, T023, T022。模块：APK订单。初始状态：未开始。

代码位置：`版本包xianyu/sync_orders；TypedExtract primitives`

**实施步骤**

1. 核验账号后进入所选角色订单列表，逐状态标签按实际页面覆盖。
2. 提取稳定orderId；列表无ID则进详情获取，取不到返回受阻而非用标题当ID。
3. 提取当前正常可见字段，详情页与列表状态冲突记录时间并以明确规则处理。
4. 金额/日期解析保留原文，缺字段null+reason；禁止从隐藏接口绕过限制获取。
5. 每批达到配置量上传并等ACK，再保存下一扫描游标。
6. seen IDs+页面fingerprint防无限滚动，N只数去重订单。
7. 暂停保存当前列表/订单/已ACK游标；恢复不重复已入库批次。
8. 扫描中新增订单导致位置变化时重新去重，达到平台末尾才complete=true；异常留证据。

**接口/数据契约**：大结果走batch ingest，不塞task complete，也不能只上传截图无结构化数据。

**必须执行的验收**
1. 真实2页以上订单字段抽样一致。
2. 指定N精确。
3. 弱网恢复无重复。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B045；需求：R05, R14；来源：S29、S27、S26。

#### T108 · P1 · 查询、同步范围与同步历史

前置任务：T107, T028, T038, T070。模块：订单页面。初始状态：未开始。

代码位置：`apps/web/src/订单管理现有入口或新增OrderList/OrderSyncHistory视图`

**实施步骤**

1. 订单列表用后端分页，支持账号/角色/状态/时间和搜索。
2. 同步按钮默认全部，选择指定数量后传N，不限制为固定50/100选项。
3. 显示本次范围、实际去重数量、缺字段原因及complete/stopReason。
4. 运行中可看手机、暂停接管并继续原run/task。
5. 敏感字段默认遮罩，授权查看和导出留审计。
6. 同步历史显示各批状态/错误；失败可从检查点续，不只能重扫全量。
7. 账号换绑后仍可查看旧账号历史，但不能用新账号重跑旧任务。
8. 测试全部、N、空订单、半途受限和刷新恢复。

**接口/数据契约**：不选择数量=全部；尚未完全扫描必须显示部分完成，不能用已采X条等同全部。

**必须执行的验收**
1. 真实订单可查询。
2. 范围符合用户规则。
3. 敏感信息不公开。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B045；需求：R03, R05, R14；来源：S20。

#### T109 · P0 · 商品身份与历史快照

前置任务：T011, T058。模块：宝贝指标。初始状态：未开始。

代码位置：`services/control-api/src/cloudctl_api/新增PlatformListing/ListingMetricSnapshot/ListingCollectRun`

**实施步骤**

1. listing主键tenant+accountId+platformListingId，Product关联可空。
2. 不按同标题自动认定与本地商品同一个，关联需发布结果或明确人工匹配。
3. 字段尽量涵盖可见标题/价格/状态/浏览/曝光/想要/收藏等并保留扩展schema。
4. 数值保存parsedValue与rawText，未知null+reason，不把未展示当0。
5. 每次采集追加capturedAt快照，当前摘要只是派生最新值。
6. 保留App/recipe版本与采集runId，方便解释平台字段变化。
7. unique run+listing+observation防重复batch造成重复快照。
8. 索引按账号/listing/时间，历史长期可查。

**接口/数据契约**：MetricValue{value,rawText,unit,status,reason}；不是任意缺值填0的宽表。

**必须执行的验收**
1. 两次采集有两个时间点。
2. 同批重传不增加快照。
3. 不同账号同标题不合并。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B042；需求：R10, R13, R15；来源：S03、S22。

#### T110 · P1 · 采集任务和历史查询

前置任务：T109, T012, T014, T017。模块：指标API。初始状态：未开始。

代码位置：`新增listing-collect-runs/batches；metric queries`

**实施步骤**

1. 创建xianyu.collect_listings任务，scope支持可见全部或指定listingIds。
2. 冻结账号、字段版本和筛选，不直接把本地Product ID当平台listing ID。
3. 批次含seq/hash/items/cursor，事务upsert listing并insert snapshot。
4. 重复seq同hash返回ACK，冲突拒绝。
5. 历史查询按account/listing/time分页；常用趋势聚合区分缺值。
6. run记录complete/stopReason、成功/解析失败/未可见数量。
7. 任务complete只带汇总和结果引用，服务端检查批次账。
8. 测试批次重发、跨账号、时间倒序和缺字段查询。

**接口/数据契约**：CollectSummary{complete,seen,accepted,failed,stopReason}；MetricQuery只读历史。

**必须执行的验收**
1. 历史不覆盖。
2. 重复批次幂等。
3. 缺字段统计不混0。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R15；来源：S22、S04。

#### T111 · P0 · 宝贝列表/详情遍历与字段提取

前置任务：T110, T039, T023, T022。模块：APK采集。初始状态：未开始。

代码位置：`版本包xianyu/collect_listings；TypedExtract primitives`

**实施步骤**

1. 进入当前账号对应商品列表，按scope枚举目标。
2. 读取稳定listingId，列表不足则进详情，标识缺失明确报错。
3. 读取当前可见指标；若某指标需独立管理页则增加已认证导航分支。
4. 解析1.2万等展示值时保留原文与精度说明，不能假称精确整数。
5. 每item返回字段可用状态和capturedAt，错误可继续其它项但留证据。
6. 滚动去重、最大扫描界限和页面fingerprint防循环。
7. 每批ACK后保存游标，暂停恢复不重复创建历史快照。
8. 抽样20个商品将手机可见值与云端数据对照，包含0/缺值/缩略单位。

**接口/数据契约**：不采平台未显示的“真实曝光”等猜测数；字段变化由recipe版本处理。

**必须执行的验收**
1. 实际值与手机一致。
2. 缺值不是0。
3. 分页和恢复不丢项。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B042；需求：R05, R15；来源：S22、S29、S26。

#### T112 · P1 · 真实采集入口、最新值与历史

前置任务：T111, T028, T038。模块：统计页面。初始状态：未开始。

代码位置：`apps/web/src/views/ListingInfoCollectView.vue；统计查询组件`

**实施步骤**

1. 创建采集改真实API，不调用local record任务。
2. 选择账号/设备/范围和统一schedule，默认按可见全部执行。
3. 显示当前扫描/已入库/失败/停止原因，不虚构百分比。
4. 列表展示最新capturedAt、指标、raw缩略精度和缺值原因。
5. 每listing可查看历史表与必要简单趋势，避免扩成二期BI。
6. 失败/暂停能看手机和继续原task。
7. 账号换绑不把旧指标显示成新账号数据。
8. 连续两次采集、缺字段、部分失败和刷新E2E。

**接口/数据契约**：既有统计页优先复用；新增指标必须能追溯来源和采集时间。

**必须执行的验收**
1. 采集后能看真实数据。
2. 历史时间点正确。
3. 本地缓存清空不丢。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B042；需求：R03, R09, R15；来源：S22。


### 阶段 J 联调与验收

#### T113 · P1 · 长期保存与显式删除全链路

前置任务：T045, T050, T105, T109, T011。模块：保留/删除。初始状态：未开始。

代码位置：`资源归档/删除服务；对象存储lifecycle；Web删除提示`

**实施步骤**

1. 移除一期业务原件/任务证据固定30天到期删除假设，默认长期保留。
2. 区分云端原件、派生、临时上传、本机缓存、直播缓冲，各有独立政策。
3. 用户删除前列出商品/帖子/任务/证据引用，运行和暂停任务引用不得误删。
4. 默认先归档；物理删除必须明确确认、权限和审计，保留必要任务摘要。
5. 删除涉及账号数据时防止误删其他绑定历史；界面列范围与不可恢复性。
6. 对象存储实际删除和DB标记用outbox可靠协调，失败可重试。
7. 备份保留与删除传播规则写明；不能声称删除后备份立即清除除非实现。
8. 测试共享原图、暂停任务资产、证据删除、恢复和对象删除失败。

**接口/数据契约**：直播默认不录全程；保存截图为明确对象。临时文件清理不等于业务数据到期删除。

**必须执行的验收**
1. 长期数据不被默认清理。
2. 引用资产不误删。
3. 删除有审计。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R13；来源：S03、S31。

#### T114 · P0 · 租户、账号、远控与版本权限测试

前置任务：T006, T042, T046, T034, T108, T113。模块：安全回归。初始状态：未开始。

代码位置：`tests/integration/security；APK contract tests；Web权限测试`

**实施步骤**

1. 建A/B租户和同租户两设备两账号的负向测试数据。
2. 逐API验证tenant过滤、device ACL和当前绑定，不只测前端按钮。
3. 远控只读token不能写，过期token/旧epoch/旧viewport全部拒绝。
4. 媒体delivery越设备、URL重定向私网、对象引用越tenant测试。
5. recipe篡改签名/zip路径穿越/未发布激活/降版本规则测试。
6. 敏感订单/剪贴板/截图访问记录与脱敏测试，日志不得泄露凭证。
7. 危险命令权限与预算/确认参数不能在客户端绕过。
8. 保存测试报告和被测commit，发现漏洞补B编号及回归测试。

**接口/数据契约**：第一期个人使用仍执行tenant边界测试，为二期保留基础。

**必须执行的验收**
1. 负向案例全部拒绝。
2. 日志无敏感泄露。
3. 旧token无控制权。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R18；来源：S31、S04。

#### T115 · P0 · Postgres租约、断网和恢复故障注入

前置任务：T027, T024, T017, T042, T107, T111。模块：并发/故障。初始状态：未开始。

代码位置：`tests/integration/concurrency；APK instrumentation；故障注入脚本`

**实施步骤**

1. 真实Postgres并发100轮双claim，断言每设备最多一个AUTO/REMOTE writer。
2. 大视频限速超过旧lease时长，确认续租先于下载且任务不被第二实例抢走。
3. 最终点击后切网/kill进程/丢complete，检查进入UNKNOWN核对而不重发。
4. 人工接管后注入旧DataChannel消息，确保旧epoch无效。
5. 暂停中到点新任务不得覆盖现场；恢复同taskId。
6. 运行中发布新版recipe、设备换绑、token撤销分别触发正确安全状态。
7. 订单/采集batch ACK前后断线，去重数量和历史快照不变。
8. 将所有故障用例保留可重复脚本与具体taskId证据。

**接口/数据契约**：不能仅用SQLite证明Postgres并发正确；外部UI副作用不宣称严格exactly-once。

**必须执行的验收**
1. 无双writer。
2. 无盲目重复发布。
3. 暂停任务不丢现场。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R05, R09；来源：S04、S25、S26。

#### T116 · P1 · 十台真机与百台模拟容量分开验证

前置任务：T032, T047, T013, T110, T106。模块：容量。初始状态：未开始。

代码位置：`新增负载脚本；metrics仪表；部署容量报告`

**实施步骤**

1. 先写负载模型：在线设备数、并发执行数、同时视频数和单视频码率，不能混为一个百台指标。
2. 一期至少10台实际手机SIM联网执行/观看/下发，记录实际机型/SDK/运营网络。
3. 再用100模拟设备测heartbeat/claim/event/FIFO/调度，报告明确“模拟”。
4. 视频并发按真实可用设备测1/多路，强制TURN时单独计上行/下行带宽与成本。
5. 大视频并发下载观测RSS/DB连接/IO，流式传输内存有界。
6. 建议验收起点：普通网络20fps附近、交互P95≤800ms；为设计目标非无条件保证，定义测量口径。
7. 30分钟稳态+弱网/重连，记录P50/P95、丢帧、队列等待和失败码。
8. 瓶颈只针对证据优化，不为百台预先拆过多服务；扩容步骤写报告。

**接口/数据契约**：fps/延迟为可调设计验收起点，用户只确认流畅；不承诺所有移动网络均达标。

**必须执行的验收**
1. 10台真实与100模拟结果分开。
2. TURN可达。
3. 无持续DB视频帧写入。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B060；需求：R01, R02, R03；来源：S35、S36、S04。

#### T117 · P0 · Redmi基线及平台版本认证

前置任务：T076, T081, T104, T108, T112, T042, T037。模块：真机矩阵。初始状态：未开始。

代码位置：`docs/phase1/device-certification.md；版本包fixtures和真机证据索引`

**实施步骤**

1. 自动记录Redmi Note9及手头其它设备model/SDK/ROM/权限/App版本，不再问用户系统版本。
2. 每台测试安装/注册/心跳/常亮/投屏授权/录屏撤销恢复/手势/中文输入。
3. 闲鱼31项按覆盖表逐个标真实通过/待测/平台不可用，不以fixture单测替代。
4. 小红书图片和视频实际发布，记录taskId与版本和证据。
5. 订单N和全部、指标两次历史、文件推送、复制限制实际验证。
6. 人工未知页暂停→接管其它App→回目标页→同task继续必须真机通过。
7. recipe草稿不生效、手动发布空闲生效、旧任务原版本恢复各测试。
8. 不可用入口留具体证据，未实测项不得填通过或“全兼容”。

**接口/数据契约**：设备型号不等于SDK；支持矩阵由实际测试生成，未知版本进入安全待适配。

**必须执行的验收**
1. 每项可追溯真实task与证据。
2. 不支持如实列。
3. 不要求手工输入App版本。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R06, R08, R16, R17；来源：S32、S30、S29。

#### T118 · P1 · 任务诊断、告警和连接状态

前置任务：T014, T022, T038, T040。模块：运维。初始状态：未开始。

代码位置：`control-api/APK结构化日志；任务详情；告警渠道复用站内通知`

**实施步骤**

1. 统一taskId/deviceId/accountId/command/recipeHash/appVersion/attempt/epoch/requestId日志字段。
2. 统计失败码、时长、排队等待、暂停等待人工、媒体失败、版本激活失败。
3. 设备离线/任务需人工/录屏需授权以站内状态和通知可见。
4. 告警去重和恢复关闭，避免每次heartbeat重复报警。
5. Web任务详情可按事件序列查看证据和当前可执行操作。
6. 不记录密码、完整剪贴板、签名私钥或私有下载token。
7. 日志保留和业务证据保留分开配置，长时间数据按需求可清理但不误删业务对象。
8. 用五类故障验证从Web定位到具体step和版本，无需猜测通用错误码。

**接口/数据契约**：一期不新增外部商业告警平台依赖；站内通知满足等待人工提示。

**必须执行的验收**
1. 失败可定位step。
2. 离线与暂停不同。
3. 日志无秘密。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R05, R11；来源：S25、S26、S21。

#### T119 · P1 · 个人云部署与升级演练

前置任务：T003, T029, T040, T113, T114。模块：部署/回滚。初始状态：未开始。

代码位置：`infra现有部署配置；.env.example；docs/phase1/deploy.md`

**实施步骤**

1. 复用现有服务组合：Web/API/worker/DB/object store/Temporal及必要信令/TURN。
2. 给出域名证书、WSS、TURN公网地址/端口、对象存储CORS和防火墙清单。
3. 配置真实密钥从secret store/env注入，示例只占位。
4. 迁移前备份；迁移后验证数量/FK/价格/账号关系；先内部设备验证再逐批。
5. 新旧执行器开关必须单向受控，禁止同设备双通道派任务。
6. 列版本回退、DB不可逆迁移恢复和待执行任务冻结步骤。
7. 备份恢复演练验证素材对象与数据库引用一致。
8. 部署验收从外部SIM而非办公室LAN进入，检查TLS和relay连通。

**接口/数据契约**：一期单用户UI但保留tenant；不预建注册计费、多客户运维后台。

**必须执行的验收**
1. 干净环境可部署。
2. 备份可恢复。
3. 公网SIM全链路通。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：新增实现/联调；需求：R02, R18；来源：S31、S35。

#### T120 · P0 · 一期端到端完成门槛与交接

前置任务：T114, T115, T116, T117, T118, T119, T065, T066, T113。模块：最终验收。初始状态：未开始。

代码位置：`docs/phase1/acceptance.md；本Excel进度/证据列；release manifest`

**实施步骤**

1. 按需求R01至R20和31项闲鱼覆盖表逐条列验收用例与对应TaskID。
2. 真实10台SIM设备：观看不中断、远控暂停、人工后同task恢复。
3. 普通宝贝六类编辑后刷新可读；导入/分组/批量操作数据库一致。
4. 小红书图文/视频、闲鱼发布及各授权任务有真实执行结果；不可用平台入口明确阻塞不假通过。
5. 订单默认全部/指定N及字段可用性、指标历史两次采集都核对。
6. 手动发布Recipe和APK升级权限边界通过；账号换绑保留历史。
7. P0问题关闭、一期阻塞P1关闭；未测风险保留，不以编码完成等于验收完成。
8. 交付commit、迁移、锁定依赖、自动化测试、真机task/证据索引、部署与回滚；更新本表状态。

**接口/数据契约**：完成定义：代码+测试+真实调用+真机证据。平台不可用项须真实证据并保持阻塞，不能由智能体自行豁免。

**必须执行的验收**
1. 每项需求有证据。
2. 无静默localStorage假成功。
3. 不把未验证写完成。

**交付物**：代码、测试与执行日志；完成后填写commit SHA和证据路径。

关联问题：B063；需求：R01, R02, R03, R04, R05, R06, R07, R08, R09, R10, R11, R12, R13, R14, R15, R16, R17, R18, R19, R20；来源：S01、S31。


## 8. 来源索引

### S01 · repo
https://github.com/candywang98/lamda-yun/commit/b394475c56a07b0ea660531222d182646e1c7e66

### S02 · services
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/services/control-api/src/cloudctl_api/services.py

### S03 · db
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/services/control-api/src/cloudctl_api/db.py

### S04 · mobile
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/services/control-api/src/cloudctl_api/mobile_service.py

### S05 · routes
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/services/control-api/src/cloudctl_api/mobile_routes.py

### S06 · mschema
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/services/control-api/src/cloudctl_api/mobile_schemas.py

### S07 · xybuilder
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/services/control-api/src/cloudctl_api/xianyu_publish.py

### S08 · pcat
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/api/product-catalog.ts

### S09 · postcat
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/api/post-catalog.ts

### S10 · pedit
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/views/ProductEditView.vue

### S11 · pimport
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/views/ProductImportView.vue

### S12 · postedit
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/views/PostEditorView.vue

### S13 · postpub
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/views/PostPublishView.vue

### S14 · xy
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/views/XianyuPublishGoodsView.vue

### S15 · simple
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/views/XianyuSimpleTaskView.vue

### S16 · extra
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/views/XianyuExtraTaskView.vue

### S17 · extrafields
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/data/xianyu-extra-tasks.ts

### S18 · xyfields
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/data/xianyu-publish-goods.ts

### S19 · groups
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/data/product-groups.ts

### S20 · ops
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/data/operations-catalog.ts

### S21 · device
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/views/DeviceDetailView.vue

### S22 · collect
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/views/ListingInfoCollectView.vue

### S23 · watermark
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/views/PostWatermarkView.vue

### S24 · session
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/apps/web/src/stores/session.ts

### S25 · sync
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/mobile/companion/app/src/main/java/com/company/cloudctl/companion/service/CompanionSyncService.kt

### S26 · store
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/mobile/companion/app/src/main/java/com/company/cloudctl/companion/data/AutomationStore.kt

### S27 · executor
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/LocalAutomationExecutor.kt

### S28 · accessibility
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/CloudCtlAccessibilityService.kt

### S29 · locators
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/TargetLocatorRegistry.kt

### S30 · gradle
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/mobile/companion/app/build.gradle.kts

### S31 · readme
https://github.com/candywang98/lamda-yun/blob/b394475c56a07b0ea660531222d182646e1c7e66/README.md

### S32 · projection
https://developer.android.com/media/grow/media-projection

### S33 · clipboard
https://developer.android.com/about/versions/10/privacy/changes#clipboard-data

### S34 · installer
https://developer.android.com/reference/android/content/pm/PackageInstaller.SessionParams#setRequireUserAction(int)

### S35 · turn
https://webrtc.org/getting-started/turn-server

### S36 · webrtc
https://webrtc.org/getting-started/peer-connections

### S37 · fgs
https://developer.android.com/develop/background-work/services/fgs/service-types


## 9. 交付状态说明

本次交付的是审阅与实施规划文件，不代表仓库已经修改。所有120项实施任务初始为未开始，所有未执行的构建/并发/真机验证均需按任务表补齐。最终按T120及其依赖的验收门槛收口；不允许由智能体把未支持项自行豁免为已完成。