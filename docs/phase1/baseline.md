# T001 基线测试报告

## 代码基线

**当前commit SHA**: b394475c56a07b0ea660531222d182646e1c7e66
**对比SHA**: b394475c56a07b0ea660531222d182646e1c7e66
**差异**: 无差异（代码基准一致）

## 环境检查

### 步骤1: Git版本确认
b394475c56a07b0ea660531222d182646e1c7e66


### 步骤2: 环境依赖检查

#### Python版本
Python 3.14.5

#### Node版本
v25.2.1

#### pnpm版本
10.15.0

#### Java版本
openjdk version "21.0.10" 2026-01-20
OpenJDK Runtime Environment Homebrew (build 21.0.10)
OpenJDK 64-Bit Server VM Homebrew (build 21.0.10, mixed mode, sharing)


### 步骤3: Python依赖安装测试

```
Obtaining file:///Users/wangziheng/Desktop/LAMDA%E4%BA%91%E6%8E%A7%E7%B3%BB%E7%BB%9F_%E4%BB%A3%E7%A0%81%E4%BA%A4%E6%8E%A5%E5%8C%85_20260901/cloudctl-source
  Installing build dependencies: started
  Installing build dependencies: finished with status 'done'
  Checking if build backend supports build_editable: started
  Checking if build backend supports build_editable: finished with status 'done'
  Getting requirements to build editable: started
  Getting requirements to build editable: finished with status 'done'
  Installing backend dependencies: started
  Installing backend dependencies: finished with status 'done'
  Preparing editable metadata (pyproject.toml): started
  Preparing editable metadata (pyproject.toml): finished with status 'done'
Collecting alembic==1.19.1 (from cloudctl==0.1.0)
  Downloading alembic-1.19.1-py3-none-any.whl.metadata (7.3 kB)
Requirement already satisfied: asyncpg==0.31.0 in /Library/Frameworks/Python.framework/Versions/3.10/lib/python3.10/site-packages (from cloudctl==0.1.0) (0.31.0)
Collecting boto3==1.43.83 (from cloudctl==0.1.0)
  Downloading boto3-1.43.83-py3-none-any.whl.metadata (6.6 kB)
Collecting cryptography==50.0.1 (from cloudctl==0.1.0)
  Downloading cryptography-50.0.1-cp39-abi3-macosx_11_0_arm64.whl.metadata (4.3 kB)
WARNING: Cache entry deserialization failed, entry ignored
Collecting fastapi==0.141.1 (from cloudctl==0.1.0)
  Using cached fastapi-0.141.1-py3-none-any.whl.metadata (27 kB)
Collecting grpcio==1.83.1 (from cloudctl==0.1.0)
  Downloading grpcio-1.83.1-cp310-cp310-macosx_11_0_universal2.whl.metadata (3.7 kB)
Requirement already satisfied: httpx==0.28.1 in /Library/Frameworks/Python.framework/Versions/3.10/lib/python3.10/site-packages (from cloudctl==0.1.0) (0.28.1)
Collecting opentelemetry-api==1.44.0 (from cloudctl==0.1.0)
  Downloading opentelemetry_api-1.44.0-py3-none-any.whl.metadata (1.4 kB)
Collecting opentelemetry-sdk==1.44.0 (from cloudctl==0.1.0)
  Downloading opentelemetry_sdk-1.44.0-py3-none-any.whl.metadata (1.6 kB)
Collecting prometheus-client==0.26.0 (from cloudctl==0.1.0)
  Downloading prometheus_client-0.26.0-py3-none-any.whl.metadata (2.1 kB)
Collecting protobuf==7.36.0 (from cloudctl==0.1.0)
  Using cached protobuf-7.36.0-cp310-abi3-macosx_10_9_universal2.whl.metadata (595 bytes)
Collecting pydantic-settings==2.15.0 (from cloudctl==0.1.0)
  Downloading pydantic_settings-2.15.0-py3-none-any.whl.metadata (3.9 kB)
Collecting pyjwt==2.13.0 (from pyjwt[crypto]==2.13.0->cloudctl==0.1.0)
  Downloading pyjwt-2.13.0-py3-none-any.whl.metadata (3.4 kB)
Collecting python-multipart==0.0.32 (from cloudctl==0.1.0)
  Downloading python_multipart-0.0.32-py3-none-any.whl.metadata (2.1 kB)
Collecting sqlalchemy==2.0.52 (from sqlalchemy[asyncio]==2.0.52->cloudctl==0.1.0)
  Downloading sqlalchemy-2.0.52-cp310-cp310-macosx_11_0_arm64.whl.metadata (9.6 kB)
Collecting temporalio==1.32.0 (from cloudctl==0.1.0)
  Using cached temporalio-1.32.0-cp310-abi3-macosx_11_0_arm64.whl.metadata (107 kB)
WARNING: Cache entry deserialization failed, entry ignored
Collecting uvicorn==0.52.4 (from uvicorn[standard]==0.52.4->cloudctl==0.1.0)
  Using cached uvicorn-0.52.4-py3-none-any.whl.metadata (6.6 kB)
INFO: pip is looking at multiple versions of cloudctl to determine which version is compatible with other requirements. This could take a while.
ERROR: Ignored the following versions that require a different python version: 17.0 Requires-Python >=3.11; 17.0.1 Requires-Python >=3.11; 17.1 Requires-Python >=3.11; 2.1.0rc1 Requires-Python >=3.11
ERROR: Could not find a version that satisfies the requirement websockets==17.1 (from cloudctl) (from versions: 1.0, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.0, 3.1, 3.2, 3.3, 3.4, 4.0.1, 5.0, 5.0.1, 6.0, 7.0, 8.0, 8.0.1, 8.0.2, 8.1, 9.0, 9.0.1, 9.0.2, 9.1, 10.0, 10.1, 10.2, 10.3, 10.4, 11.0, 11.0.1, 11.0.2, 11.0.3, 12.0, 13.0, 13.0.1, 13.1, 14.0, 14.1, 14.2, 15.0, 15.0.1, 16.0, 16.1, 16.1.1)

[notice] A new release of pip is available: 24.3.1 -> 26.2.1
[notice] To update, run: pip install --upgrade pip
ERROR: No matching distribution found for websockets==17.1
```

退出码: 0


### 步骤4: Node依赖安装测试

```
Scope: all 4 workspace projects
Lockfile is up to date, resolution step is skipped
Already up to date

╭ Warning ─────────────────────────────────────────────────────────────────────╮
│                                                                              │
│   Ignored build scripts: esbuild, vue-demi.                                  │
│   Run "pnpm approve-builds" to pick which dependencies should be allowed     │
│   to run scripts.                                                            │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯

Done in 330ms using pnpm v10.15.0
```

退出码: 0


### 步骤5-8: Python代码质量检查

#### ruff format检查
```
unformatted: File would be reformatted
   --> artifacts/review-20260905/build-plan.py:3:1
    |
2   | import json
    - ROOT=Path(__file__).resolve().parents[2]
    - OUT=ROOT/'docs/v1'
    - items=[]
    - def add(n,title,phase,deps,days,existing,files,steps,checks,accept,block=''):
    -  items.append(dict(id=f'V1-{n:02}',title=title,phase=phase,dependencies=[f'V1-{x:02}' for x in deps],estimate_low=days[0],estimate_high=days[1],status='blocked' if block else 'todo',existing=existing,files=files,steps=steps,verification_commands=checks,acceptance=accept,blocker=block,evidence=f'artifacts/v1/V1-{n:02}/',owner='待分配'))
    - P='services/control-api/src/cloudctl_api/'
    - K='mobile/companion/app/src/main/java/com/company/cloudctl/companion/'
    - add(1,'建立可复现工程基线并修复真实检查失败','M0 基线',[],(1,2),'Python 392 / Web 40 / Studio 16 / APK 41 单测通过；静态检查与部分浏览器用例失败',
    - ['pyproject.toml','.github/workflows/ci.yml','scripts/check-security-boundaries.sh','apps/web/playwright.config.ts','apps/web/e2e/smoke.spec.ts'],
    - ['保存本轮日志作为基线；记录 Python/pnpm/JDK/SDK 版本与依赖清单，建立不包含 lab/凭据的源码 Git 检查点。','按 Ruff/Pyright 日志定位问题；对 Outbox 构造参数、gRPC 方法真实签名逐项核对，禁止只加 type: ignore。','修复 BSD grep 扫描失败：错误必须非零退出；临时夹具覆盖违规 import、设备端口、密钥样式，夹具不含真实密钥。','Playwright 独占端口并验证页面属于 CloudCtl；产品用例只使用产品配置；核对侧栏滚动和页面文案现状后调整真实交互断言。','补完整锁定和安装说明；在干净测试环境验证，而不是删除当前工作虚拟环境。'],
    - ['.venv/bin/python -m pytest -q','.venv/bin/ruff check .','.venv/bin/ruff format --check .','.venv/bin/pyright','pnpm lint','pnpm typecheck','pnpm test','pnpm build','bash scripts/check-security-boundaries.sh','pnpm --filter @cloudctl/web e2e:product'],
    - '上述命令全绿；浏览器 smoke 在独占端口运行且无新增 skip；扫描器故障不能返回成功。')
    - add(2,'冻结 APK 直连主线和 V1 业务范围','M0 基线',[],(.5,1),'ADR 0003 已接受 APK 本地执行，README/旧规则仍描述 LAMDA 主线',
    - ['AGENTS.md','README.md','docs/adr/0003-mobile-local-execution.md','docs/v1/02-实施方案.md'],
    - ['逐条列出旧架构与 ADR 0003 冲突，写新的 ADR 说明适用范围及取代关系。','将设备任务定为 Companion 直连；已有 API 平台执行走服务端；两者共享业务 Target。','保留 LAMDA/Edge 诊断边界，但生产首版不依赖 USB，不同时在手机上跑两个 Runner。','明确闲鱼商品、小红书图文、抖音视频、公众号文章均属于完整 V1；其他竞品目录冻结。'],
    - ['rg -n "Mobile-local|Companion|LAMDA|V1" AGENTS.md README.md docs/adr'],
    - '每种执行方式有唯一所有者、同一提交语义和明确文档入口；无相互矛盾的强制路线。')
    - add(3,'盘点用户真实商品库和素材库','M0 基线',[],(.5,1),'本轮未找到实际来源连接器，库类型、地址、字段和授权未知',
    - ['docs/v1/source-profile.json（新增）','docs/v1/source-mapping.md（新增）'],
    - ['由库管理员提供只读入口，填写实施方案第3节的来源类型、范围、稳定主键、附件获取方式与规模。','只读抽样10商品/20素材，脱敏记录字段名、类型、空值、金额单位、附件顺序和原件可访问性。','确定两个库之间关联键及删除、冲突处理；来源字段默认只读，平台覆盖另存。','拿到真实权限后做一次只读请求并保存脱敏响应结构；未提供入口时保留阻塞，不猜测飞书或数据库。'],
    - ['读取 source-profile.json 并校验必填项；按实际来源官方文档执行只读采样（端点待盘点）'],
    - '真实入口、主键与字段映射确认；原图/视频可读取；凭据只存 secret_ref。','需要用户现有库的只读入口、类型和字段样本')
    - add(4,'恢复真机验收前置条件','M0 基线',[],(.5,1),'OnePlus Android14在线；APK 0.1.0 debug；项目无障碍服务未启用',
    - [K+'MainActivity.kt',K+'service/CompanionSyncService.kt','docs/v1/device-matrix.json（新增）'],
    - ['记录当前手机、APK、四个App版本；核对APK所绑定API环境与本轮源码构建摘要。','在手机系统设置中由用户/授权管理员启用项目无障碍服务；确认通知、前台服务和电池状态。','用现有注册流程绑定受控测试设备，不覆盖其他账号或卸载应用。','运行只读健康/截图任务，核对服务端任务ID与手机日志；记录平台账号指纹但不抄录密码。'],
    - ['adb devices -l','adb -s b0644fb5 shell settings get secure enabled_accessibility_services','./mobile/companion/build-external.sh testDebugUnitTest lintDebug'],
    - '项目服务已启用，HTTPS绑定正确，真实健康任务有回执；不把ADB在线当自动化通过。')
    - add(5,'来源连接器协议和字段映射','M1 来源与内容',[2,3],(1,2),'复用Product/Media/Content领域，不另建业务库',
    - [P+'source_schemas.py（新增）',P+'source_service.py（新增）',P+'db.py','services/control-api/migrations/versions/（新增迁移）'],
    - ['定义 SourceConnection/SourceRecordLink/SyncRun/SyncError 的字段与租户唯一键。','新增连接测试和preview接口，预览只返回规范记录与逐行错误，不写业务商品。','定义 read_page(cursor)、fetch_asset(ref)、normalize_record(record) 协议；只实现盘点确认的一种来源。','映射版本不可变；来源凭据经secret_ref解析，日志脱敏；分页游标只从来源响应取得。'],
    - ['新增 tests/integration/test_source_connections.py：预览不写库、跨租户、权限失效、字段错误','.venv/bin/python -m pytest -q tests/integration/test_source_connections.py'],
    - '一页真实样本可转换为标准数据；错误精确到外部ID/字段；无明文凭据。')
    - add(6,'幂等增量同步与附件入库','M1 来源与内容',[5],(2,3),'已有媒体上传和SHA去重可复用',
    - [P+'source_service.py',P+'media_store.py',P+'services.py','services/outbox-dispatcher/src/cloudctl_outbox/'],
    - ['以tenant+connection+externalId唯一映射；同hash跳过，不同hash新建修订。','分页业务提交后推进游标；来源下载先临时文件校验再注册资产。','对过期附件地址向来源重新取一次；下载失败保留行级错误与重试入口。','来源删除仅tombstone；发布引用不丢失；可选回写单独任务且按targetId幂等。','使用进程中断夹具覆盖游标写入前后崩溃，重复页不得重复创建。'],
    - ['新增 tests/integration/test_source_sync.py','.venv/bin/python -m pytest -q tests/integration/test_source_sync.py tests/integration/test_backend_accounts_media_content.py'],
    - '首轮导入、重复导入、修改、删除和崩溃恢复通过；至少10条真实来源记录与附件一致。')
    - add(7,'Web 来源连接与同步错误界面','M1 来源与内容',[5,6],(1,2),'现有工作台缺来源库连接体验',
    - ['apps/web/src/views/SourceConnectionsView.vue（新增）','apps/web/src/router.ts','packages/api-contracts/typescript/src/'],
    - ['从OpenAPI生成来源接口类型；表单只显示脱敏连接和字段映射。','新增测试连接、预览10条、确认同步、最后同步时间与错误列表。','点击行级错误能显示外部记录ID、字段和修复建议；重试复用syncRun操作键。','刷新页面从API恢复状态，禁止本地假同步进度。'],
    - ['python scripts/export_openapi.py（使用项目虚拟环境）','pnpm contracts','pnpm typecheck','pnpm --filter @cloudctl/web test'],
    - '非技术用户能确认来源、预览映射、启动同步并找到错误记录；页面刷新不丢任务。')
    - add(8,'完善媒体就绪状态和大文件处理','M1 来源与内容',[2],(1,2),'MediaAsset/Upload/Derivative/Tag/Group已存在',
    - [P+'media_store.py',P+'services.py',P+'schemas.py','tests/integration/test_backend_accounts_media_content.py'],
    - ['检查上传完成校验：真实字节、大小、MIME、hash和租户引用必须一致。','定义 PROCESSING/READY/FAILED；查明现有衍生物是否有执行工人，没有则补缩略图/视频元数据活动。','大视频采用流式传输和长度上限；使用100MB测试文件验证峰值内存，不以测试大小代替平台限制。','失败临时文件清理；被计划/商品引用的资产不物理删除。'],
    - ['.venv/bin/python -m pytest -q tests/integration/test_backend_accounts_media_content.py','运行100MB流式上传下载基准并记录峰值内存、耗时'],
    - '仅真实校验完成资产可发布；缩略图/尺寸/时长可显示；hash错误被拒绝。')
    - add(9,'Web 素材选择器与引用提示','M1 来源与内容',[8],(1,2),'目前编辑表单仍需要输入mediaAssetIds',
    - ['apps/web/src/components/MediaPicker.vue（新增）','apps/web/src/views/OperationsView.vue','packages/api-contracts/typescript/src/'],
    - ['提供图片/视频缩略图、标签分组搜索、上传状态与分页。','选择时输出assetId有序数组，不要求用户复制ID；封面单独标识。','显示引用数量，归档时告知具体商品/计划；失败媒体不可选。','沿用现有媒体接口与TanStack Query，不另建本地媒体真相。'],
    - ['pnpm typecheck','新增组件测试：分页、顺序、封面、未就绪禁用','pnpm --filter @cloudctl/web test'],
    - '用户能选图/视频、排序、设封面且保存后重开一致。')
    - add(10,'商品原子保存、不可变修订与资源类型纠正','M1 来源与内容',[1,8],(1.5,3),'Product已存在，Web保存后仍调旧Content下发',
    - [P+'db.py',P+'services.py',P+'schemas.py','apps/web/src/views/OperationsView.vue','tests/integration/test_backend_accounts_media_content.py'],
    - ['先增加失败回归：保存新Product再发往旧Content路径，明确类型不匹配；不使用预制共享ID掩盖。','复用Product行，加不可变ProductRevision并回填当前版本；历史未知版本不可伪造。','商品字段和媒体顺序在一个事务保存，expectedRevision不匹配返回409；金额用Decimal。','改Web只维护productId/productRevision；删除对Content下发的商品调用，待V1-14接入正式Plan入口。','平台覆盖补成色/运费/发货地，使用schema校验；不扩展ERP。'],
    - ['.venv/bin/python -m pytest -q tests/integration/test_backend_accounts_media_content.py','pnpm --filter @cloudctl/web e2e:product','pnpm typecheck'],
    - '新增/编辑/图片排序原子一致；并发409；Product不会再作为Content查询；旧发布快照可读。')
    - add(11,'内容包与平台覆盖编辑','M1 来源与内容',[9],(1,2),'已有ContentRevision和媒体关联',
    - [P+'content_payload.py',P+'schemas.py','apps/web/src/views/OperationsView.vue','tests/unit/test_content_payload.py'],
    - ['复用ContentRevision，定义图文、单视频、公众号文章三类结构。','每平台保存title/body/media/cover/hashtags覆盖；不改共享原始素材。','公众号HTML清洗，图片只引用本租户资产；标题超限阻断而非截断。','保存新修订并提供按平台预览；未支持组合明确标不支持。'],
    - ['.venv/bin/python -m pytest -q tests/unit/test_content_payload.py','pnpm --filter @cloudctl/web test'],
    - '同一内容可形成三种合法平台预览；编辑覆盖不会污染其他平台或旧修订。')
    - add(12,'账号能力、身份核对与设备绑定','M2 发布核心',[2,4],(1.5,3),'已有账号记录与设备绑定，不等同真实平台授权',
    - [P+'db.py',P+'services.py',P+'mobile_service.py',K+'automation/TargetLocatorRegistry.kt'],
    - ['读取现有account/binding实体，扩展channel/scope/status/verifiedAt/identityFingerprint，不复制账号表。','区分ANDROID登录指纹与API OAuth scope；未支持/过期/撤销分别返回稳定码。','提交前核对当前账号指纹及绑定设备，遇到切号/登录失效阻断。','Web显示授权来源、最后检查时间与恢复入口；Token保留服务端secret_ref。'],
    - ['新增 tests/integration/test_account_capabilities.py','.venv/bin/python -m pytest -q tests/integration/test_account_capabilities.py','真机核对一个账号并模拟身份不一致（不自动切换账号）'],
    - '账号名相同不当成同一账号；失效、错号、错设备都不能申请提交许可。')
    - add(13,'统一目标状态机与错误合同','M2 发布核心',[2],(1,2),'已有PublishState和MobileTask状态，不能直接互相复制',
    - ['packages/domain/src/cloudctl_domain/',P+'schemas.py',P+'mobile_schemas.py','contracts/'],
    - ['列出现有所有状态及调用方，写新旧映射表与允许转移矩阵。','加入PREPARED/DRAFT_SAVED/平台接收/审核中/公开成功语义，决定兼容存储方式。','定义失败是否可重试及提交边界，UNKNOWN只允许查询/人工对账。','增加模式PREPARE_ONLY/SAVE_DRAFT/PUBLISH；契约同步到Python/TS/Kotlin。'],
    - ['.venv/bin/python -m pytest -q tests/unit/test_backend_domain.py tests/contracts/test_openapi_contract.py','pnpm contracts','pnpm typecheck'],
    - '非法倒退转移被拒绝；填表SUCCEEDED不能使Target变公开成功。')
    - add(14,'计划校验、快照冻结与Product发布入口','M2 发布核心',[10,11,12,13],(2,3),'Plan/Snapshot/Target/Approval/Outbox表已有',
    - [P+'services.py',P+'routes.py',P+'schemas.py',P+'db.py','tests/integration/test_backend_control_api.py'],
    - ['扩展现有Plan合同以source.kind分派ProductRevision/ContentRevision，避免重复Plan体系。','校验source租户、媒体READY、账号能力、设备绑定、平台格式并生成previewHash。','同事务写Plan/Target/不可变快照/审批/outbox；每个目标保存不同platform覆盖。','Idempotency-Key同摘要返回原资源，异摘要409；禁用Date.now作为网络重试的新key。','记录快照hash、账号指纹、媒体顺序、执行器版本；提交后编辑不改变快照。'],
    - ['.venv/bin/python -m pytest -q tests/integration/test_backend_control_api.py tests/integration/test_backend_accounts_media_content.py','新增Product到Plan到Target集成用例'],
    - '新商品通过正式发布入口建计划；重复请求只有一个Plan；来源修改不影响冻结内容。')
    - add(15,'复用Outbox编排并验证PostgreSQL互斥','M2 发布核心',[14],(1.5,3),'Temporal/Outbox已有；本轮未证明真PostgreSQL和历史replay',
    - ['services/temporal-worker/src/cloudctl_worker/','services/outbox-dispatcher/src/cloudctl_outbox/',P+'mobile_service.py','tests/replay/'],
    - ['消费既有outbox为Target选择API或APK执行器；同event_id仅处理一次。','固定账号再设备的锁顺序，PG租约fence递增；API目标不伪造deviceId。','在临时PostgreSQL数据库跑实际Alembic升级及并发领取，不操作现有线上库。','准备真实Temporal历史并用Replayer验证；单元AST检查保留但不冒充replay。'],
    - ['.venv/bin/python -m pytest -q tests/integration/test_backend_outbox.py tests/replay','在隔离测试PostgreSQL上执行alembic upgrade head/current及新增并发测试'],
    - '并发领取仍单Runner；Outbox至少一次投递不重复业务；有PG和真实历史重放日志。')
    - add(16,'APK任务协议持久化与恢复补齐','M2 发布核心',[13,15],(1.5,3),'AutomationStore、CloudTaskClient、SyncService已存在',
    - [K+'automation/AutomationTask.kt',K+'data/AutomationStore.kt',K+'network/CloudTaskClient.kt',K+'service/CompanionSyncService.kt'],
    - ['扩展版本化任务合同包含targetId/snapshotHash/accountFingerprint/channel；未知版本拒绝。','核对taskId+canonical digest的持久化去重，重复相同内容返回旧回执，异内容拒绝。','状态先落本地DB再ACK，事件携带唯一ID/序号；旧fence不可继续执行。','进程恢复按PREPARING/COMMIT_STARTED分支，准备可恢复，提交已开始只对账。'],
    - ['./mobile/companion/build-external.sh testDebugUnitTest lintDebug','新增AutomationStore进程恢复/异摘要/旧fence测试'],
    - '重启不会丢任务或重复最终动作；未知协议失败关闭。')
    - add(17,'任务绑定的媒体授权与流式投递','M2 发布核心',[8,14,16],(1.5,3),'已有下载校验/MediaStore导出；当前仅限制到租户',
    - [P+'mobile_service.py',P+'mobile_routes.py',K+'media/MediaDelivery.kt',K+'data/MediaDeliveryCoordinator.kt'],
    - ['新增delivery grant绑定target/task/device/manifestHash/到期，下载请求必须属于清单。','按snapshot中媒体ID和hash生成manifest，不接受设备随意指定同租户资产。','流式下载.part，长度/hash校验后原子安装；缓存命中必须重验绑定与hash。','在本地持久化URI映射，重复领取复用；失败和取消只删除本任务产物。'],
    - ['.venv/bin/python -m pytest -q tests/integration/test_mobile_task_api.py','./mobile/companion/build-external.sh testDebugUnitTest','真机100MB视频传输及断网/hash错误验收'],
    - '同租户其他任务媒体无法下载；重复投递不重复导出；坏文件不进入平台。')
    - add(18,'闲鱼精确选图，消除索引盲选','M3 闲鱼',[4,17],(2,4),'现有gallery_select_N只按第N个选择节点',
    - [P+'xianyu_publish.py',K+'automation/TargetLocatorRegistry.kt',K+'automation/CloudCtlAccessibilityService.kt',K+'media/MediaGalleryExporter.kt'],
    - ['采集当前闲鱼选择器UI结构；记录相机入口、相册筛选、文件可见信息和排序。','建立assetId/hash/URI到可验证选项的映射，优先受控相册和唯一标识。','编译选择步骤前验证所有素材已导出；选后核对顺序/封面/数量和图像身份。','混入30张旧图及一张新干扰图验证；没有可靠映射时转USER_ACTION_REQUIRED，不再用索引兜底。'],
    - ['.venv/bin/python -m pytest -q tests/unit/test_xianyu_publish_recipe.py','./mobile/companion/build-external.sh testDebugUnitTest','OnePlus+闲鱼7.27.90执行A/B/C素材和干扰图验收'],
    - '实际选中A/B/C且顺序一致；不确定时不提交。')
    - add(19,'闲鱼完整商品预填和预览证据','M3 闲鱼',[10,12,18],(1.5,3),'已有描述/价格配方，缺完整字段回读',
    - [P+'xianyu_publish.py',K+'automation/TargetLocatorRegistry.kt','contracts/xianyu-publish-text.example.json'],
    - ['根据实际UI补标题/描述/价格/成色/运费/发货地，字段存在性由当前类目决定。','每次打开面板和确认字段都有后置条件；输入后读回Decimal价格和运费。','显式处理键盘、草稿恢复和权限弹窗；账号检查失败立即暂停。','结束上传预览截图与摘要，标PREPARED而非发布成功；保留用户确认入口。'],
    - ['.venv/bin/python -m pytest -q tests/unit/test_xianyu_publish_recipe.py','真机单商品三图字段读回、草稿恢复、必填缺失验收'],
    - '商品、媒体、价格、运费和账号可逐项核对，预填不触发最终发布。')
    - add(20,'最终提交许可与最多一次执行','M3 闲鱼',[13,16,19],(2,4),'数据库CommitIntent存在，APK最终发布协议未闭环',
    - [P+'services.py',P+'mobile_service.py',P+'db.py',K+'data/AutomationStore.kt',K+'automation/LocalAutomationExecutor.kt'],
    - ['复用CommitIntent，加target唯一约束/一次提交许可；核对现有attempt_no不能允许第二次最终提交。','许可绑定snapshot/审批/账号/fence/到期；过期、错号、取消请求拒绝。','APK先持久化COMMIT_STARTED再点唯一发布节点；该动作不可用通用步骤重试。','分别在许可前、日志落盘后、点击后断网/杀进程，恢复不再次点击。','API Publisher采用同等提交账本语义，避免API失败后自动切APK重复发送。'],
    - ['新增 tests/integration/test_publish_commit_permit.py','.venv/bin/python -m pytest -q tests/integration/test_publish_commit_permit.py','./mobile/companion/build-external.sh testDebugUnitTest','真机提交断点验收（受控内容、用户确认）'],
    - '每Target最多一次提交尝试；重复许可/任务/重启均无重复发布。')
    - add(21,'结果对账、审核状态与人工处理','M3 闲鱼',[20],(1.5,3),'现有MobileTask终态不能证明平台发布结果',
    - [P+'services.py',P+'mobile_service.py','services/temporal-worker/src/cloudctl_worker/',K+'automation/'],
    - ['定义结构化平台回执：externalId/url、平台接收/审核/公开状态、证据hash、账号指纹。','闲鱼按当前账号商品列表/详情核对标题图价格；不以一条toast证明成功。','查询有上限和下次时间；超时无证据转UNKNOWN，人工可附结果链接/原因。','人工标记记录操作者、证据和审计，不暗中触发重发。'],
    - ['新增 tests/integration/test_publish_reconciliation.py','真机成功/平台拒绝/审核中/响应丢失验收'],
    - '填表、已接收、审核中、公开成功、未知严格分开；UNKNOWN不自动重发。')
    - add(22,'Web 一次确认发布向导和结果页','M3 闲鱼',[9,11,14,21],(2,3),'现有发布路由重定向到通用OperationsView',
    - ['apps/web/src/views/PublishWizardView.vue（新增）','apps/web/src/views/PublishPlanView.vue（新增）','apps/web/src/router.ts','packages/api-contracts/typescript/src/'],
    - ['独立路由保留planId/targetId，选来源修订、平台账号、媒体和平台覆盖。','调用validate展示每目标previewHash与阻塞字段；用户一次确认后submit。','保存稳定幂等键直到拿到planId；网络重试复用；新计划才生成新键。','结果页刷新读真实API，显示部分失败/审核/UNKNOWN及证据；重试按钮只允许准备阶段。'],
    - ['pnpm contracts','pnpm typecheck','pnpm --filter @cloudctl/web test','新增真实API+测试数据库的Publish E2E（不拦截所有请求）'],
    - '能从真实Product建计划到查看结果；双击无重复；无mock回执；阶段名称准确。')
    - add(23,'平台权限探测与适配器注册合同','M4 三内容平台',[2,12,13],(1,2),'除闲鱼外未见已接入的移动定位器',
    - ['packages/automation-sdk/src/cloudctl_automation_sdk/',P+'platform_capabilities.py（新增）','docs/v1/platform-capabilities.json（新增）'],
    - ['记录四平台账号实际授权/scope、渠道、格式、限制、审核方式与文档日期。','定义validate/prepare/before_commit/commit_once/reconcile/cleanup公共合同，禁止API提交后自动切UI。','检查小红书分享SDK是否只唤起分享；公众号需实际后台权限，不能由微信安装推导。','版本未验证/权限未给标UNSUPPORTED或待授权；只阻塞相关平台，不阻塞其他Target。'],
    - ['新增适配器合同测试：未知平台/错误scope/错误channel/过期版本','逐账号保存脱敏权限探测证据'],
    - '每个平台有已证实渠道或明确阻塞；公开资料和账号实际权限分栏。')
    - add(24,'小红书图文发布适配器','M4 三内容平台',[11,17,20,21,23],(3,5),'本机小红书8.50.1；执行器尚未接入',
    - [K+'automation/TargetLocatorRegistry.kt',P+'publishers/xiaohongshu.py（新增）','docs/compatibility/'],
    - ['按V1-23选择实际可用分享/API/UI路线；记录能力限制，不安装未经验证第三方私有API。','完成账号核对、精确多图选择、标题正文话题预填、预览。','共用提交许可，唤起分享仅记prepared；最终提交单次执行。','在本账号笔记页对账，记录审核/公开状态；采集发布成功及未知场景证据。'],
    - ['新增tests/unit/test_xiaohongshu_publisher.py','Android单测及8.50.1真机图文全链路验收'],
    - '指定图文发布到指定账号；有外部结果证据；审核中不显示公开成功。')
    - add(25,'抖音视频发布适配器','M4 三内容平台',[11,17,20,21,23],(3,5),'本机抖音39.6.0；需核查video.create授权',
    - [P+'publishers/douyin.py（新增）',K+'automation/TargetLocatorRegistry.kt','docs/compatibility/'],
    - ['验证实际OAuth scope；有正式权限用API，否则按已授权UI路线实现。','API先上传并保存video_id，UI精确选择指定视频；验证时长/格式/封面，限制来自能力配置。','填写标题/话题/可见范围，生成预览hash；调用共用提交账本。','上传成功不等于发布成功；保存item_id并查询审核/可见状态；请求丢失不再次创建。'],
    - ['新增tests/unit/test_douyin_publisher.py','对真实授权账户进行单视频发布、超限、授权失效和审核状态验收'],
    - '完整视频到指定账号；上传、提交、审核三阶段可追溯；无跨渠道重复。')
    - add(26,'微信公众号文章发布适配器','M4 三内容平台',[11,20,21,23],(3,5),'官方文档正文本轮未取得；账号资格未知',
    - [P+'publishers/wechat_official.py（新增）','docs/v1/wechat-permissions.md（新增）'],
    - ['先从用户公众号后台和官方文档确认草稿/发布/状态查询权限、端点与参数，保存日期；不据第三方博客锁合同。','上传封面和正文图，HTML清洗/内联样式/图片地址替换；生成草稿并预览。','有发布能力才使用共用许可提交，记录publish/article ID和状态；只会创建草稿则标DRAFT_SAVED。','公众号文章发布与粉丝群发分开；无权限则明确阻塞完整发布，按平台后台合法手工流程补验收。'],
    - ['新增tests/unit/test_wechat_official_publisher.py','真实公众号草稿、发布、状态查询与权限不足验收'],
    - '文章发布有可核验URL/ID；只有草稿权限不得把该任务标done。')
    - add(27,'多平台多账号排队与部分失败','M5 完整V1',[15,22,24,25,26],(1.5,3),'已有批次操作骨架，需统一真正的PublishTarget',
    - [P+'services.py','services/temporal-worker/src/cloudctl_worker/','apps/web/src/views/PublishPlanView.vue'],
    - ['同一计划按平台账号展开Target，冻结每个目标内容覆盖。','设备和账号串行；不同设备可并行，默认并发1，配置上限验证。','汇总成功/失败/未知/等待；失败不回滚或重发成功项。','取消只在安全点；恢复后保持原targetId与快照，不创建隐性新目标。'],
    - ['新增tests/integration/test_multi_platform_publish.py','真实四平台受控批次和一个目标失败场景'],
    - '一次确认可排队四平台，部分失败可定位；同设备无并行写；成功项不重复发布。')
    - add(28,'断网重启、无USB和账号异常恢复','M5 完整V1',[27],(2,4),'基础恢复单测已有，真实长链证据不足',
    - [K+'data/AutomationStore.kt',K+'service/CompanionSyncService.kt','docs/v1/hardware-acceptance.md（新增）'],
    - ['手机使用独立网络，断USB并停开发Edge；Web通过HTTPS提交受控计划。','准备中/提交后分别断网和终止进程，核对本地DB与云端事件。','测试权限关闭、锁屏、电量限制、存储不足、App版本变化，显示可恢复原因而非无限重试。','执行24h观察，记录送达率/耗时/未知率和故障；不将一台手机外推所有Android。'],
    - ['实施方案A06-A18真实验收，日志包含设备/版本/task/target/时间和hash'],
    - '无USB任务能独立运行；提交不重复；账号异常暂停；24h报告可复核。')
    - add(29,'Release 构建、部署备份与回滚','M5 完整V1',[1,28],(1.5,3),'当前已装debug APK；服务部署与本地版本未比对',
    - ['mobile/companion/app/build.gradle.kts','infra/','scripts/backup.sh','scripts/restore.sh','docs/runbooks/'],
    - ['配置release signing secret_ref、递增versionCode；产物记录SHA和签名摘要，debuggable=false。','生产认证关闭dev bypass；前端固定角色改为真实会话/权限，API地址和TLS指纹改环境配置；验证租户隔离、API TLS、对象存储和后台任务环境。','在测试部署做PG备份恢复和schema回滚/前滚演练；不在用户真实库试破坏性迁移。','安装同签名升级验证绑定/任务保留，记录回滚可行性，不强制换签名或降级。'],
    - ['release assemble/lint（签名由实际环境注入）','adb shell dumpsys package com.company.cloudctl.companion（验版本与flags）','隔离环境备份恢复及灰度运行检查'],
    - '安装可核对release；部署摘要对应源码；有已演练恢复步骤。')
    - add(30,'完整V1业务验收和来源回写','M5 完整V1',[6,7,27,28,29],(1,2),'完整端到端里程碑本轮验收0/8',
    - ['docs/v1/acceptance-report.md（新增）','docs/v1/tasks.json','docs/v1/03-逐项任务卡.md'],
    - ['从用户真实来源库选新商品/素材，经Web一次确认发往四个已授权目标。','逐目标核对账号、内容、素材、平台结果URL/ID；审核尚未结束的保持进行中。','可选来源回写target结果，失败重试仅回写，不重新发布；不给来源覆盖内容字段。','按八个里程碑更新证据覆盖，只将全部通过者标done；整理操作说明、错误处理和后续范围。'],
    - ['执行实施方案A01-A18；复核所有任务依赖、日志、证据和构建摘要'],
    - '8个完整业务里程碑均有证据；四平台都能明确区分草稿/审核/公开结果；用户能独立操作。')
3   +
4   + ROOT = Path(__file__).resolve().parents[2]
5   + OUT = ROOT / "docs/v1"
6   + items = []
7   +
8   +
9   + def add(n, title, phase, deps, days, existing, files, steps, checks, accept, block=""):
10  +     items.append(
11  +         dict(
12  +             id=f"V1-{n:02}",
13  +             title=title,
14  +             phase=phase,
15  +             dependencies=[f"V1-{x:02}" for x in deps],
16  +             estimate_low=days[0],
17  +             estimate_high=days[1],
18  +             status="blocked" if block else "todo",
19  +             existing=existing,
20  +             files=files,
21  +             steps=steps,
22  +             verification_commands=checks,
23  +             acceptance=accept,
24  +             blocker=block,
25  +             evidence=f"artifacts/v1/V1-{n:02}/",
26  +             owner="待分配",
27  +         )
28  +     )
29  +
30  +
31  + P = "services/control-api/src/cloudctl_api/"
32  + K = "mobile/companion/app/src/main/java/com/company/cloudctl/companion/"
33  + add(
34  +     1,
35  +     "建立可复现工程基线并修复真实检查失败",
36  +     "M0 基线",
37  +     [],
38  +     (1, 2),
39  +     "Python 392 / Web 40 / Studio 16 / APK 41 单测通过；静态检查与部分浏览器用例失败",
40  +     [
41  +         "pyproject.toml",
42  +         ".github/workflows/ci.yml",
43  +         "scripts/check-security-boundaries.sh",
44  +         "apps/web/playwright.config.ts",
45  +         "apps/web/e2e/smoke.spec.ts",
46  +     ],
47  +     [
48  +         "保存本轮日志作为基线；记录 Python/pnpm/JDK/SDK 版本与依赖清单，建立不包含 lab/凭据的源码 Git 检查点。",
49  +         "按 Ruff/Pyright 日志定位问题；对 Outbox 构造参数、gRPC 方法真实签名逐项核对，禁止只加 type: ignore。",
50  +         "修复 BSD grep 扫描失败：错误必须非零退出；临时夹具覆盖违规 import、设备端口、密钥样式，夹具不含真实密钥。",
51  +         "Playwright 独占端口并验证页面属于 CloudCtl；产品用例只使用产品配置；核对侧栏滚动和页面文案现状后调整真实交互断言。",
52  +         "补完整锁定和安装说明；在干净测试环境验证，而不是删除当前工作虚拟环境。",
53  +     ],
54  +     [
55  +         ".venv/bin/python -m pytest -q",
56  +         ".venv/bin/ruff check .",
57  +         ".venv/bin/ruff format --check .",
58  +         ".venv/bin/pyright",
59  +         "pnpm lint",
60  +         "pnpm typecheck",
61  +         "pnpm test",
62  +         "pnpm build",
63  +         "bash scripts/check-security-boundaries.sh",
64  +         "pnpm --filter @cloudctl/web e2e:product",
65  +     ],
66  +     "上述命令全绿；浏览器 smoke 在独占端口运行且无新增 skip；扫描器故障不能返回成功。",
67  + )
68  + add(
69  +     2,
70  +     "冻结 APK 直连主线和 V1 业务范围",
71  +     "M0 基线",
72  +     [],
73  +     (0.5, 1),
74  +     "ADR 0003 已接受 APK 本地执行，README/旧规则仍描述 LAMDA 主线",
75  +     ["AGENTS.md", "README.md", "docs/adr/0003-mobile-local-execution.md", "docs/v1/02-实施方案.md"],
76  +     [
77  +         "逐条列出旧架构与 ADR 0003 冲突，写新的 ADR 说明适用范围及取代关系。",
78  +         "将设备任务定为 Companion 直连；已有 API 平台执行走服务端；两者共享业务 Target。",
79  +         "保留 LAMDA/Edge 诊断边界，但生产首版不依赖 USB，不同时在手机上跑两个 Runner。",
80  +         "明确闲鱼商品、小红书图文、抖音视频、公众号文章均属于完整 V1；其他竞品目录冻结。",
81  +     ],
82  +     ['rg -n "Mobile-local|Companion|LAMDA|V1" AGENTS.md README.md docs/adr'],
83  +     "每种执行方式有唯一所有者、同一提交语义和明确文档入口；无相互矛盾的强制路线。",
84  + )
85  + add(
86  +     3,
87  +     "盘点用户真实商品库和素材库",
88  +     "M0 基线",
89  +     [],
90  +     (0.5, 1),
91  +     "本轮未找到实际来源连接器，库类型、地址、字段和授权未知",
92  +     ["docs/v1/source-profile.json（新增）", "docs/v1/source-mapping.md（新增）"],
93  +     [
94  +         "由库管理员提供只读入口，填写实施方案第3节的来源类型、范围、稳定主键、附件获取方式与规模。",
95  +         "只读抽样10商品/20素材，脱敏记录字段名、类型、空值、金额单位、附件顺序和原件可访问性。",
96  +         "确定两个库之间关联键及删除、冲突处理；来源字段默认只读，平台覆盖另存。",
97  +         "拿到真实权限后做一次只读请求并保存脱敏响应结构；未提供入口时保留阻塞，不猜测飞书或数据库。",
98  +     ],
99  +     ["读取 source-profile.json 并校验必填项；按实际来源官方文档执行只读采样（端点待盘点）"],
100 +     "真实入口、主键与字段映射确认；原图/视频可读取；凭据只存 secret_ref。",
101 +     "需要用户现有库的只读入口、类型和字段样本",
102 + )
103 + add(
104 +     4,
105 +     "恢复真机验收前置条件",
106 +     "M0 基线",
107 +     [],
108 +     (0.5, 1),
109 +     "OnePlus Android14在线；APK 0.1.0 debug；项目无障碍服务未启用",
110 +     [
111 +         K + "MainActivity.kt",
112 +         K + "service/CompanionSyncService.kt",
113 +         "docs/v1/device-matrix.json（新增）",
114 +     ],
115 +     [
116 +         "记录当前手机、APK、四个App版本；核对APK所绑定API环境与本轮源码构建摘要。",
117 +         "在手机系统设置中由用户/授权管理员启用项目无障碍服务；确认通知、前台服务和电池状态。",
118 +         "用现有注册流程绑定受控测试设备，不覆盖其他账号或卸载应用。",
119 +         "运行只读健康/截图任务，核对服务端任务ID与手机日志；记录平台账号指纹但不抄录密码。",
120 +     ],
121 +     [
122 +         "adb devices -l",
123 +         "adb -s b0644fb5 shell settings get secure enabled_accessibility_services",
124 +         "./mobile/companion/build-external.sh testDebugUnitTest lintDebug",
125 +     ],
126 +     "项目服务已启用，HTTPS绑定正确，真实健康任务有回执；不把ADB在线当自动化通过。",
127 + )
128 + add(
129 +     5,
130 +     "来源连接器协议和字段映射",
131 +     "M1 来源与内容",
132 +     [2, 3],
133 +     (1, 2),
134 +     "复用Product/Media/Content领域，不另建业务库",
135 +     [
136 +         P + "source_schemas.py（新增）",
137 +         P + "source_service.py（新增）",
138 +         P + "db.py",
139 +         "services/control-api/migrations/versions/（新增迁移）",
140 +     ],
141 +     [
142 +         "定义 SourceConnection/SourceRecordLink/SyncRun/SyncError 的字段与租户唯一键。",
143 +         "新增连接测试和preview接口，预览只返回规范记录与逐行错误，不写业务商品。",
144 +         "定义 read_page(cursor)、fetch_asset(ref)、normalize_record(record) 协议；只实现盘点确认的一种来源。",
145 +         "映射版本不可变；来源凭据经secret_ref解析，日志脱敏；分页游标只从来源响应取得。",
146 +     ],
147 +     [
148 +         "新增 tests/integration/test_source_connections.py：预览不写库、跨租户、权限失效、字段错误",
149 +         ".venv/bin/python -m pytest -q tests/integration/test_source_connections.py",
150 +     ],
151 +     "一页真实样本可转换为标准数据；错误精确到外部ID/字段；无明文凭据。",
152 + )
153 + add(
154 +     6,
155 +     "幂等增量同步与附件入库",
156 +     "M1 来源与内容",
157 +     [5],
158 +     (2, 3),
159 +     "已有媒体上传和SHA去重可复用",
160 +     [
161 +         P + "source_service.py",
162 +         P + "media_store.py",
163 +         P + "services.py",
164 +         "services/outbox-dispatcher/src/cloudctl_outbox/",
165 +     ],
166 +     [
167 +         "以tenant+connection+externalId唯一映射；同hash跳过，不同hash新建修订。",
168 +         "分页业务提交后推进游标；来源下载先临时文件校验再注册资产。",
169 +         "对过期附件地址向来源重新取一次；下载失败保留行级错误与重试入口。",
170 +         "来源删除仅tombstone；发布引用不丢失；可选回写单独任务且按targetId幂等。",
171 +         "使用进程中断夹具覆盖游标写入前后崩溃，重复页不得重复创建。",
172 +     ],
173 +     [
174 +         "新增 tests/integration/test_source_sync.py",
175 +         ".venv/bin/python -m pytest -q tests/integration/test_source_sync.py tests/integration/test_backend_accounts_media_content.py",
176 +     ],
177 +     "首轮导入、重复导入、修改、删除和崩溃恢复通过；至少10条真实来源记录与附件一致。",
178 + )
179 + add(
180 +     7,
181 +     "Web 来源连接与同步错误界面",
182 +     "M1 来源与内容",
183 +     [5, 6],
184 +     (1, 2),
185 +     "现有工作台缺来源库连接体验",
186 +     [
187 +         "apps/web/src/views/SourceConnectionsView.vue（新增）",
188 +         "apps/web/src/router.ts",
189 +         "packages/api-contracts/typescript/src/",
190 +     ],
191 +     [
192 +         "从OpenAPI生成来源接口类型；表单只显示脱敏连接和字段映射。",
193 +         "新增测试连接、预览10条、确认同步、最后同步时间与错误列表。",
194 +         "点击行级错误能显示外部记录ID、字段和修复建议；重试复用syncRun操作键。",
195 +         "刷新页面从API恢复状态，禁止本地假同步进度。",
196 +     ],
197 +     [
198 +         "python scripts/export_openapi.py（使用项目虚拟环境）",
199 +         "pnpm contracts",
200 +         "pnpm typecheck",
201 +         "pnpm --filter @cloudctl/web test",
202 +     ],
203 +     "非技术用户能确认来源、预览映射、启动同步并找到错误记录；页面刷新不丢任务。",
204 + )
205 + add(
206 +     8,
207 +     "完善媒体就绪状态和大文件处理",
208 +     "M1 来源与内容",
209 +     [2],
210 +     (1, 2),
211 +     "MediaAsset/Upload/Derivative/Tag/Group已存在",
212 +     [
213 +         P + "media_store.py",
214 +         P + "services.py",
215 +         P + "schemas.py",
216 +         "tests/integration/test_backend_accounts_media_content.py",
217 +     ],
218 +     [
219 +         "检查上传完成校验：真实字节、大小、MIME、hash和租户引用必须一致。",
220 +         "定义 PROCESSING/READY/FAILED；查明现有衍生物是否有执行工人，没有则补缩略图/视频元数据活动。",
221 +         "大视频采用流式传输和长度上限；使用100MB测试文件验证峰值内存，不以测试大小代替平台限制。",
222 +         "失败临时文件清理；被计划/商品引用的资产不物理删除。",
223 +     ],
224 +     [
225 +         ".venv/bin/python -m pytest -q tests/integration/test_backend_accounts_media_content.py",
226 +         "运行100MB流式上传下载基准并记录峰值内存、耗时",
227 +     ],
228 +     "仅真实校验完成资产可发布；缩略图/尺寸/时长可显示；hash错误被拒绝。",
229 + )
230 + add(
231 +     9,
232 +     "Web 素材选择器与引用提示",
233 +     "M1 来源与内容",
234 +     [8],
235 +     (1, 2),
236 +     "目前编辑表单仍需要输入mediaAssetIds",
237 +     [
238 +         "apps/web/src/components/MediaPicker.vue（新增）",
239 +         "apps/web/src/views/OperationsView.vue",
240 +         "packages/api-contracts/typescript/src/",
241 +     ],
242 +     [
243 +         "提供图片/视频缩略图、标签分组搜索、上传状态与分页。",
244 +         "选择时输出assetId有序数组，不要求用户复制ID；封面单独标识。",
245 +         "显示引用数量，归档时告知具体商品/计划；失败媒体不可选。",
246 +         "沿用现有媒体接口与TanStack Query，不另建本地媒体真相。",
247 +     ],
248 +     [
249 +         "pnpm typecheck",
250 +         "新增组件测试：分页、顺序、封面、未就绪禁用",
251 +         "pnpm --filter @cloudctl/web test",
252 +     ],
253 +     "用户能选图/视频、排序、设封面且保存后重开一致。",
254 + )
255 + add(
256 +     10,
257 +     "商品原子保存、不可变修订与资源类型纠正",
258 +     "M1 来源与内容",
259 +     [1, 8],
260 +     (1.5, 3),
261 +     "Product已存在，Web保存后仍调旧Content下发",
262 +     [
263 +         P + "db.py",
264 +         P + "services.py",
265 +         P + "schemas.py",
266 +         "apps/web/src/views/OperationsView.vue",
267 +         "tests/integration/test_backend_accounts_media_content.py",
268 +     ],
269 +     [
270 +         "先增加失败回归：保存新Product再发往旧Content路径，明确类型不匹配；不使用预制共享ID掩盖。",
271 +         "复用Product行，加不可变ProductRevision并回填当前版本；历史未知版本不可伪造。",
272 +         "商品字段和媒体顺序在一个事务保存，expectedRevision不匹配返回409；金额用Decimal。",
273 +         "改Web只维护productId/productRevision；删除对Content下发的商品调用，待V1-14接入正式Plan入口。",
274 +         "平台覆盖补成色/运费/发货地，使用schema校验；不扩展ERP。",
275 +     ],
276 +     [
277 +         ".venv/bin/python -m pytest -q tests/integration/test_backend_accounts_media_content.py",
278 +         "pnpm --filter @cloudctl/web e2e:product",
279 +         "pnpm typecheck",
280 +     ],
281 +     "新增/编辑/图片排序原子一致；并发409；Product不会再作为Content查询；旧发布快照可读。",
282 + )
283 + add(
284 +     11,
285 +     "内容包与平台覆盖编辑",
286 +     "M1 来源与内容",
287 +     [9],
288 +     (1, 2),
289 +     "已有ContentRevision和媒体关联",
290 +     [
291 +         P + "content_payload.py",
292 +         P + "schemas.py",
293 +         "apps/web/src/views/OperationsView.vue",
294 +         "tests/unit/test_content_payload.py",
295 +     ],
296 +     [
297 +         "复用ContentRevision，定义图文、单视频、公众号文章三类结构。",
298 +         "每平台保存title/body/media/cover/hashtags覆盖；不改共享原始素材。",
299 +         "公众号HTML清洗，图片只引用本租户资产；标题超限阻断而非截断。",
300 +         "保存新修订并提供按平台预览；未支持组合明确标不支持。",
301 +     ],
302 +     [
303 +         ".venv/bin/python -m pytest -q tests/unit/test_content_payload.py",
304 +         "pnpm --filter @cloudctl/web test",
305 +     ],
306 +     "同一内容可形成三种合法平台预览；编辑覆盖不会污染其他平台或旧修订。",
307 + )
308 + add(
309 +     12,
310 +     "账号能力、身份核对与设备绑定",
311 +     "M2 发布核心",
312 +     [2, 4],
313 +     (1.5, 3),
314 +     "已有账号记录与设备绑定，不等同真实平台授权",
315 +     [
316 +         P + "db.py",
317 +         P + "services.py",
318 +         P + "mobile_service.py",
319 +         K + "automation/TargetLocatorRegistry.kt",
320 +     ],
321 +     [
322 +         "读取现有account/binding实体，扩展channel/scope/status/verifiedAt/identityFingerprint，不复制账号表。",
323 +         "区分ANDROID登录指纹与API OAuth scope；未支持/过期/撤销分别返回稳定码。",
324 +         "提交前核对当前账号指纹及绑定设备，遇到切号/登录失效阻断。",
325 +         "Web显示授权来源、最后检查时间与恢复入口；Token保留服务端secret_ref。",
326 +     ],
327 +     [
328 +         "新增 tests/integration/test_account_capabilities.py",
329 +         ".venv/bin/python -m pytest -q tests/integration/test_account_capabilities.py",
330 +         "真机核对一个账号并模拟身份不一致（不自动切换账号）",
331 +     ],
332 +     "账号名相同不当成同一账号；失效、错号、错设备都不能申请提交许可。",
333 + )
334 + add(
335 +     13,
336 +     "统一目标状态机与错误合同",
337 +     "M2 发布核心",
338 +     [2],
339 +     (1, 2),
340 +     "已有PublishState和MobileTask状态，不能直接互相复制",
341 +     [
342 +         "packages/domain/src/cloudctl_domain/",
343 +         P + "schemas.py",
344 +         P + "mobile_schemas.py",
345 +         "contracts/",
346 +     ],
347 +     [
348 +         "列出现有所有状态及调用方，写新旧映射表与允许转移矩阵。",
349 +         "加入PREPARED/DRAFT_SAVED/平台接收/审核中/公开成功语义，决定兼容存储方式。",
350 +         "定义失败是否可重试及提交边界，UNKNOWN只允许查询/人工对账。",
351 +         "增加模式PREPARE_ONLY/SAVE_DRAFT/PUBLISH；契约同步到Python/TS/Kotlin。",
352 +     ],
353 +     [
354 +         ".venv/bin/python -m pytest -q tests/unit/test_backend_domain.py tests/contracts/test_openapi_contract.py",
355 +         "pnpm contracts",
356 +         "pnpm typecheck",
357 +     ],
358 +     "非法倒退转移被拒绝；填表SUCCEEDED不能使Target变公开成功。",
359 + )
360 + add(
361 +     14,
362 +     "计划校验、快照冻结与Product发布入口",
363 +     "M2 发布核心",
364 +     [10, 11, 12, 13],
365 +     (2, 3),
366 +     "Plan/Snapshot/Target/Approval/Outbox表已有",
367 +     [
368 +         P + "services.py",
369 +         P + "routes.py",
370 +         P + "schemas.py",
371 +         P + "db.py",
372 +         "tests/integration/test_backend_control_api.py",
373 +     ],
374 +     [
375 +         "扩展现有Plan合同以source.kind分派ProductRevision/ContentRevision，避免重复Plan体系。",
376 +         "校验source租户、媒体READY、账号能力、设备绑定、平台格式并生成previewHash。",
377 +         "同事务写Plan/Target/不可变快照/审批/outbox；每个目标保存不同platform覆盖。",
378 +         "Idempotency-Key同摘要返回原资源，异摘要409；禁用Date.now作为网络重试的新key。",
379 +         "记录快照hash、账号指纹、媒体顺序、执行器版本；提交后编辑不改变快照。",
380 +     ],
381 +     [
382 +         ".venv/bin/python -m pytest -q tests/integration/test_backend_control_api.py tests/integration/test_backend_accounts_media_content.py",
383 +         "新增Product到Plan到Target集成用例",
384 +     ],
385 +     "新商品通过正式发布入口建计划；重复请求只有一个Plan；来源修改不影响冻结内容。",
386 + )
387 + add(
388 +     15,
389 +     "复用Outbox编排并验证PostgreSQL互斥",
390 +     "M2 发布核心",
391 +     [14],
392 +     (1.5, 3),
393 +     "Temporal/Outbox已有；本轮未证明真PostgreSQL和历史replay",
394 +     [
395 +         "services/temporal-worker/src/cloudctl_worker/",
396 +         "services/outbox-dispatcher/src/cloudctl_outbox/",
397 +         P + "mobile_service.py",
398 +         "tests/replay/",
399 +     ],
400 +     [
401 +         "消费既有outbox为Target选择API或APK执行器；同event_id仅处理一次。",
402 +         "固定账号再设备的锁顺序，PG租约fence递增；API目标不伪造deviceId。",
403 +         "在临时PostgreSQL数据库跑实际Alembic升级及并发领取，不操作现有线上库。",
404 +         "准备真实Temporal历史并用Replayer验证；单元AST检查保留但不冒充replay。",
405 +     ],
406 +     [
407 +         ".venv/bin/python -m pytest -q tests/integration/test_backend_outbox.py tests/replay",
408 +         "在隔离测试PostgreSQL上执行alembic upgrade head/current及新增并发测试",
409 +     ],
410 +     "并发领取仍单Runner；Outbox至少一次投递不重复业务；有PG和真实历史重放日志。",
411 + )
412 + add(
413 +     16,
414 +     "APK任务协议持久化与恢复补齐",
415 +     "M2 发布核心",
416 +     [13, 15],
417 +     (1.5, 3),
418 +     "AutomationStore、CloudTaskClient、SyncService已存在",
419 +     [
420 +         K + "automation/AutomationTask.kt",
421 +         K + "data/AutomationStore.kt",
422 +         K + "network/CloudTaskClient.kt",
423 +         K + "service/CompanionSyncService.kt",
424 +     ],
425 +     [
426 +         "扩展版本化任务合同包含targetId/snapshotHash/accountFingerprint/channel；未知版本拒绝。",
427 +         "核对taskId+canonical digest的持久化去重，重复相同内容返回旧回执，异内容拒绝。",
428 +         "状态先落本地DB再ACK，事件携带唯一ID/序号；旧fence不可继续执行。",
429 +         "进程恢复按PREPARING/COMMIT_STARTED分支，准备可恢复，提交已开始只对账。",
430 +     ],
431 +     [
432 +         "./mobile/companion/build-external.sh testDebugUnitTest lintDebug",
433 +         "新增AutomationStore进程恢复/异摘要/旧fence测试",
434 +     ],
435 +     "重启不会丢任务或重复最终动作；未知协议失败关闭。",
436 + )
437 + add(
438 +     17,
439 +     "任务绑定的媒体授权与流式投递",
440 +     "M2 发布核心",
441 +     [8, 14, 16],
442 +     (1.5, 3),
443 +     "已有下载校验/MediaStore导出；当前仅限制到租户",
444 +     [
445 +         P + "mobile_service.py",
446 +         P + "mobile_routes.py",
447 +         K + "media/MediaDelivery.kt",
448 +         K + "data/MediaDeliveryCoordinator.kt",
449 +     ],
450 +     [
451 +         "新增delivery grant绑定target/task/device/manifestHash/到期，下载请求必须属于清单。",
452 +         "按snapshot中媒体ID和hash生成manifest，不接受设备随意指定同租户资产。",
453 +         "流式下载.part，长度/hash校验后原子安装；缓存命中必须重验绑定与hash。",
454 +         "在本地持久化URI映射，重复领取复用；失败和取消只删除本任务产物。",
455 +     ],
456 +     [
457 +         ".venv/bin/python -m pytest -q tests/integration/test_mobile_task_api.py",
458 +         "./mobile/companion/build-external.sh testDebugUnitTest",
459 +         "真机100MB视频传输及断网/hash错误验收",
460 +     ],
461 +     "同租户其他任务媒体无法下载；重复投递不重复导出；坏文件不进入平台。",
462 + )
463 + add(
464 +     18,
465 +     "闲鱼精确选图，消除索引盲选",
466 +     "M3 闲鱼",
467 +     [4, 17],
468 +     (2, 4),
469 +     "现有gallery_select_N只按第N个选择节点",
470 +     [
471 +         P + "xianyu_publish.py",
472 +         K + "automation/TargetLocatorRegistry.kt",
473 +         K + "automation/CloudCtlAccessibilityService.kt",
474 +         K + "media/MediaGalleryExporter.kt",
475 +     ],
476 +     [
477 +         "采集当前闲鱼选择器UI结构；记录相机入口、相册筛选、文件可见信息和排序。",
478 +         "建立assetId/hash/URI到可验证选项的映射，优先受控相册和唯一标识。",
479 +         "编译选择步骤前验证所有素材已导出；选后核对顺序/封面/数量和图像身份。",
480 +         "混入30张旧图及一张新干扰图验证；没有可靠映射时转USER_ACTION_REQUIRED，不再用索引兜底。",
481 +     ],
482 +     [
483 +         ".venv/bin/python -m pytest -q tests/unit/test_xianyu_publish_recipe.py",
484 +         "./mobile/companion/build-external.sh testDebugUnitTest",
485 +         "OnePlus+闲鱼7.27.90执行A/B/C素材和干扰图验收",
486 +     ],
487 +     "实际选中A/B/C且顺序一致；不确定时不提交。",
488 + )
489 + add(
490 +     19,
491 +     "闲鱼完整商品预填和预览证据",
492 +     "M3 闲鱼",
493 +     [10, 12, 18],
494 +     (1.5, 3),
495 +     "已有描述/价格配方，缺完整字段回读",
496 +     [
497 +         P + "xianyu_publish.py",
498 +         K + "automation/TargetLocatorRegistry.kt",
499 +         "contracts/xianyu-publish-text.example.json",
500 +     ],
501 +     [
502 +         "根据实际UI补标题/描述/价格/成色/运费/发货地，字段存在性由当前类目决定。",
503 +         "每次打开面板和确认字段都有后置条件；输入后读回Decimal价格和运费。",
504 +         "显式处理键盘、草稿恢复和权限弹窗；账号检查失败立即暂停。",
505 +         "结束上传预览截图与摘要，标PREPARED而非发布成功；保留用户确认入口。",
506 +     ],
507 +     [
508 +         ".venv/bin/python -m pytest -q tests/unit/test_xianyu_publish_recipe.py",
509 +         "真机单商品三图字段读回、草稿恢复、必填缺失验收",
510 +     ],
511 +     "商品、媒体、价格、运费和账号可逐项核对，预填不触发最终发布。",
512 + )
513 + add(
514 +     20,
515 +     "最终提交许可与最多一次执行",
516 +     "M3 闲鱼",
517 +     [13, 16, 19],
518 +     (2, 4),
519 +     "数据库CommitIntent存在，APK最终发布协议未闭环",
520 +     [
521 +         P + "services.py",
522 +         P + "mobile_service.py",
523 +         P + "db.py",
524 +         K + "data/AutomationStore.kt",
525 +         K + "automation/LocalAutomationExecutor.kt",
526 +     ],
527 +     [
528 +         "复用CommitIntent，加target唯一约束/一次提交许可；核对现有attempt_no不能允许第二次最终提交。",
529 +         "许可绑定snapshot/审批/账号/fence/到期；过期、错号、取消请求拒绝。",
530 +         "APK先持久化COMMIT_STARTED再点唯一发布节点；该动作不可用通用步骤重试。",
531 +         "分别在许可前、日志落盘后、点击后断网/杀进程，恢复不再次点击。",
532 +         "API Publisher采用同等提交账本语义，避免API失败后自动切APK重复发送。",
533 +     ],
534 +     [
535 +         "新增 tests/integration/test_publish_commit_permit.py",
536 +         ".venv/bin/python -m pytest -q tests/integration/test_publish_commit_permit.py",
537 +         "./mobile/companion/build-external.sh testDebugUnitTest",
538 +         "真机提交断点验收（受控内容、用户确认）",
539 +     ],
540 +     "每Target最多一次提交尝试；重复许可/任务/重启均无重复发布。",
541 + )
542 + add(
543 +     21,
544 +     "结果对账、审核状态与人工处理",
545 +     "M3 闲鱼",
546 +     [20],
547 +     (1.5, 3),
548 +     "现有MobileTask终态不能证明平台发布结果",
549 +     [
550 +         P + "services.py",
551 +         P + "mobile_service.py",
552 +         "services/temporal-worker/src/cloudctl_worker/",
553 +         K + "automation/",
554 +     ],
555 +     [
556 +         "定义结构化平台回执：externalId/url、平台接收/审核/公开状态、证据hash、账号指纹。",
557 +         "闲鱼按当前账号商品列表/详情核对标题图价格；不以一条toast证明成功。",
558 +         "查询有上限和下次时间；超时无证据转UNKNOWN，人工可附结果链接/原因。",
559 +         "人工标记记录操作者、证据和审计，不暗中触发重发。",
560 +     ],
561 +     [
562 +         "新增 tests/integration/test_publish_reconciliation.py",
563 +         "真机成功/平台拒绝/审核中/响应丢失验收",
564 +     ],
565 +     "填表、已接收、审核中、公开成功、未知严格分开；UNKNOWN不自动重发。",
566 + )
567 + add(
568 +     22,
569 +     "Web 一次确认发布向导和结果页",
570 +     "M3 闲鱼",
571 +     [9, 11, 14, 21],
572 +     (2, 3),
573 +     "现有发布路由重定向到通用OperationsView",
574 +     [
575 +         "apps/web/src/views/PublishWizardView.vue（新增）",
576 +         "apps/web/src/views/PublishPlanView.vue（新增）",
577 +         "apps/web/src/router.ts",
578 +         "packages/api-contracts/typescript/src/",
579 +     ],
580 +     [
581 +         "独立路由保留planId/targetId，选来源修订、平台账号、媒体和平台覆盖。",
582 +         "调用validate展示每目标previewHash与阻塞字段；用户一次确认后submit。",
583 +         "保存稳定幂等键直到拿到planId；网络重试复用；新计划才生成新键。",
584 +         "结果页刷新读真实API，显示部分失败/审核/UNKNOWN及证据；重试按钮只允许准备阶段。",
585 +     ],
586 +     [
587 +         "pnpm contracts",
588 +         "pnpm typecheck",
589 +         "pnpm --filter @cloudctl/web test",
590 +         "新增真实API+测试数据库的Publish E2E（不拦截所有请求）",
591 +     ],
592 +     "能从真实Product建计划到查看结果；双击无重复；无mock回执；阶段名称准确。",
593 + )
594 + add(
595 +     23,
596 +     "平台权限探测与适配器注册合同",
597 +     "M4 三内容平台",
598 +     [2, 12, 13],
599 +     (1, 2),
600 +     "除闲鱼外未见已接入的移动定位器",
601 +     [
602 +         "packages/automation-sdk/src/cloudctl_automation_sdk/",
603 +         P + "platform_capabilities.py（新增）",
604 +         "docs/v1/platform-capabilities.json（新增）",
605 +     ],
606 +     [
607 +         "记录四平台账号实际授权/scope、渠道、格式、限制、审核方式与文档日期。",
608 +         "定义validate/prepare/before_commit/commit_once/reconcile/cleanup公共合同，禁止API提交后自动切UI。",
609 +         "检查小红书分享SDK是否只唤起分享；公众号需实际后台权限，不能由微信安装推导。",
610 +         "版本未验证/权限未给标UNSUPPORTED或待授权；只阻塞相关平台，不阻塞其他Target。",
611 +     ],
612 +     ["新增适配器合同测试：未知平台/错误scope/错误channel/过期版本", "逐账号保存脱敏权限探测证据"],
613 +     "每个平台有已证实渠道或明确阻塞；公开资料和账号实际权限分栏。",
614 + )
615 + add(
616 +     24,
617 +     "小红书图文发布适配器",
618 +     "M4 三内容平台",
619 +     [11, 17, 20, 21, 23],
620 +     (3, 5),
621 +     "本机小红书8.50.1；执行器尚未接入",
622 +     [
623 +         K + "automation/TargetLocatorRegistry.kt",
624 +         P + "publishers/xiaohongshu.py（新增）",
625 +         "docs/compatibility/",
626 +     ],
627 +     [
628 +         "按V1-23选择实际可用分享/API/UI路线；记录能力限制，不安装未经验证第三方私有API。",
629 +         "完成账号核对、精确多图选择、标题正文话题预填、预览。",
630 +         "共用提交许可，唤起分享仅记prepared；最终提交单次执行。",
631 +         "在本账号笔记页对账，记录审核/公开状态；采集发布成功及未知场景证据。",
632 +     ],
633 +     ["新增tests/unit/test_xiaohongshu_publisher.py", "Android单测及8.50.1真机图文全链路验收"],
634 +     "指定图文发布到指定账号；有外部结果证据；审核中不显示公开成功。",
635 + )
636 + add(
637 +     25,
638 +     "抖音视频发布适配器",
639 +     "M4 三内容平台",
640 +     [11, 17, 20, 21, 23],
641 +     (3, 5),
642 +     "本机抖音39.6.0；需核查video.create授权",
643 +     [
644 +         P + "publishers/douyin.py（新增）",
645 +         K + "automation/TargetLocatorRegistry.kt",
646 +         "docs/compatibility/",
647 +     ],
648 +     [
649 +         "验证实际OAuth scope；有正式权限用API，否则按已授权UI路线实现。",
650 +         "API先上传并保存video_id，UI精确选择指定视频；验证时长/格式/封面，限制来自能力配置。",
651 +         "填写标题/话题/可见范围，生成预览hash；调用共用提交账本。",
652 +         "上传成功不等于发布成功；保存item_id并查询审核/可见状态；请求丢失不再次创建。",
653 +     ],
654 +     [
655 +         "新增tests/unit/test_douyin_publisher.py",
656 +         "对真实授权账户进行单视频发布、超限、授权失效和审核状态验收",
657 +     ],
658 +     "完整视频到指定账号；上传、提交、审核三阶段可追溯；无跨渠道重复。",
659 + )
660 + add(
661 +     26,
662 +     "微信公众号文章发布适配器",
663 +     "M4 三内容平台",
664 +     [11, 20, 21, 23],
665 +     (3, 5),
666 +     "官方文档正文本轮未取得；账号资格未知",
667 +     [P + "publishers/wechat_official.py（新增）", "docs/v1/wechat-permissions.md（新增）"],
668 +     [
669 +         "先从用户公众号后台和官方文档确认草稿/发布/状态查询权限、端点与参数，保存日期；不据第三方博客锁合同。",
670 +         "上传封面和正文图，HTML清洗/内联样式/图片地址替换；生成草稿并预览。",
671 +         "有发布能力才使用共用许可提交，记录publish/article ID和状态；只会创建草稿则标DRAFT_SAVED。",
672 +         "公众号文章发布与粉丝群发分开；无权限则明确阻塞完整发布，按平台后台合法手工流程补验收。",
673 +     ],
674 +     [
675 +         "新增tests/unit/test_wechat_official_publisher.py",
676 +         "真实公众号草稿、发布、状态查询与权限不足验收",
677 +     ],
678 +     "文章发布有可核验URL/ID；只有草稿权限不得把该任务标done。",
679 + )
680 + add(
681 +     27,
682 +     "多平台多账号排队与部分失败",
683 +     "M5 完整V1",
684 +     [15, 22, 24, 25, 26],
685 +     (1.5, 3),
686 +     "已有批次操作骨架，需统一真正的PublishTarget",
687 +     [
688 +         P + "services.py",
689 +         "services/temporal-worker/src/cloudctl_worker/",
690 +         "apps/web/src/views/PublishPlanView.vue",
691 +     ],
692 +     [
693 +         "同一计划按平台账号展开Target，冻结每个目标内容覆盖。",
694 +         "设备和账号串行；不同设备可并行，默认并发1，配置上限验证。",
695 +         "汇总成功/失败/未知/等待；失败不回滚或重发成功项。",
696 +         "取消只在安全点；恢复后保持原targetId与快照，不创建隐性新目标。",
697 +     ],
698 +     [
699 +         "新增tests/integration/test_multi_platform_publish.py",
700 +         "真实四平台受控批次和一个目标失败场景",
701 +     ],
702 +     "一次确认可排队四平台，部分失败可定位；同设备无并行写；成功项不重复发布。",
703 + )
704 + add(
705 +     28,
706 +     "断网重启、无USB和账号异常恢复",
707 +     "M5 完整V1",
708 +     [27],
709 +     (2, 4),
710 +     "基础恢复单测已有，真实长链证据不足",
711 +     [
712 +         K + "data/AutomationStore.kt",
713 +         K + "service/CompanionSyncService.kt",
714 +         "docs/v1/hardware-acceptance.md（新增）",
715 +     ],
716 +     [
717 +         "手机使用独立网络，断USB并停开发Edge；Web通过HTTPS提交受控计划。",
718 +         "准备中/提交后分别断网和终止进程，核对本地DB与云端事件。",
719 +         "测试权限关闭、锁屏、电量限制、存储不足、App版本变化，显示可恢复原因而非无限重试。",
720 +         "执行24h观察，记录送达率/耗时/未知率和故障；不将一台手机外推所有Android。",
721 +     ],
722 +     ["实施方案A06-A18真实验收，日志包含设备/版本/task/target/时间和hash"],
723 +     "无USB任务能独立运行；提交不重复；账号异常暂停；24h报告可复核。",
724 + )
725 + add(
726 +     29,
727 +     "Release 构建、部署备份与回滚",
728 +     "M5 完整V1",
729 +     [1, 28],
730 +     (1.5, 3),
731 +     "当前已装debug APK；服务部署与本地版本未比对",
732 +     [
733 +         "mobile/companion/app/build.gradle.kts",
734 +         "infra/",
735 +         "scripts/backup.sh",
736 +         "scripts/restore.sh",
737 +         "docs/runbooks/",
738 +     ],
739 +     [
740 +         "配置release signing secret_ref、递增versionCode；产物记录SHA和签名摘要，debuggable=false。",
741 +         "生产认证关闭dev bypass；前端固定角色改为真实会话/权限，API地址和TLS指纹改环境配置；验证租户隔离、API TLS、对象存储和后台任务环境。",
742 +         "在测试部署做PG备份恢复和schema回滚/前滚演练；不在用户真实库试破坏性迁移。",
743 +         "安装同签名升级验证绑定/任务保留，记录回滚可行性，不强制换签名或降级。",
744 +     ],
745 +     [
746 +         "release assemble/lint（签名由实际环境注入）",
747 +         "adb shell dumpsys package com.company.cloudctl.companion（验版本与flags）",
748 +         "隔离环境备份恢复及灰度运行检查",
749 +     ],
750 +     "安装可核对release；部署摘要对应源码；有已演练恢复步骤。",
751 + )
752 + add(
753 +     30,
754 +     "完整V1业务验收和来源回写",
755 +     "M5 完整V1",
756 +     [6, 7, 27, 28, 29],
757 +     (1, 2),
758 +     "完整端到端里程碑本轮验收0/8",
759 +     ["docs/v1/acceptance-report.md（新增）", "docs/v1/tasks.json", "docs/v1/03-逐项任务卡.md"],
760 +     [
761 +         "从用户真实来源库选新商品/素材，经Web一次确认发往四个已授权目标。",
762 +         "逐目标核对账号、内容、素材、平台结果URL/ID；审核尚未结束的保持进行中。",
763 +         "可选来源回写target结果，失败重试仅回写，不重新发布；不给来源覆盖内容字段。",
764 +         "按八个里程碑更新证据覆盖，只将全部通过者标done；整理操作说明、错误处理和后续范围。",
765 +     ],
766 +     ["执行实施方案A01-A18；复核所有任务依赖、日志、证据和构建摘要"],
767 +     "8个完整业务里程碑均有证据；四平台都能明确区分草稿/审核/公开结果；用户能独立操作。",
768 + )
769 | # Regenerating task cards must not reset accepted work or assignments.
    - existing_path=OUT/'tasks.json'
770 + existing_path = OUT / "tasks.json"
771 | if existing_path.exists():
    -  prior={t['id']:t for t in json.loads(existing_path.read_text())['tasks']}
    -  for task in items:
    -   old=prior.get(task['id'],{})
    -   for field in ('status','owner','blocker','progress_notes','verified_at','acceptance_evidence'):
    -    if field in old:task[field]=old[field]
    - ids={t['id'] for t in items}
772 +     prior = {t["id"]: t for t in json.loads(existing_path.read_text())["tasks"]}
773 +     for task in items:
774 +         old = prior.get(task["id"], {})
775 +         for field in (
776 +             "status",
777 +             "owner",
778 +             "blocker",
779 +             "progress_notes",
780 +             "verified_at",
781 +             "acceptance_evidence",
782 +         ):
783 +             if field in old:
784 +                 task[field] = old[field]
785 + ids = {t["id"] for t in items}
786 | for t in items:
    -  assert all(d in ids and d<t['id'] for d in t['dependencies']),t['id']
    - (OUT/'tasks.json').write_text(json.dumps({'baseline':'2026-09-05','policy':'estimates are person-days, external waits excluded; no implementation task accepted in this review','tasks':items},ensure_ascii=False,indent=2))
    - lines=['# V1 逐项任务卡','', '基线：2026-09-05。所有路径相对 cloudctl-source。新增文件为提案；实施前核对最新代码。', '', '每张卡完成时都要保存实际退出码、测试摘要、变更清单和证据；命令中的自然语言项是待实现验收步骤，不能复制为 shell。所有 Python 命令使用项目 `.venv/bin/python`。', '', '状态：todo/doing/blocked/blocked_hardware/review/done。当前任务没有完成验收，已有能力列仅表示可复用的基础。', '']
787 +     assert all(d in ids and d < t["id"] for d in t["dependencies"]), t["id"]
788 + (OUT / "tasks.json").write_text(
789 +     json.dumps(
790 +         {
791 +             "baseline": "2026-09-05",
792 +             "policy": "estimates are person-days, external waits excluded; no implementation task accepted in this review",
793 +             "tasks": items,
794 +         },
795 +         ensure_ascii=False,
796 +         indent=2,
797 +     )
798 + )
799 + lines = [
800 +     "# V1 逐项任务卡",
801 +     "",
802 +     "基线：2026-09-05。所有路径相对 cloudctl-source。新增文件为提案；实施前核对最新代码。",
803 +     "",
804 +     "每张卡完成时都要保存实际退出码、测试摘要、变更清单和证据；命令中的自然语言项是待实现验收步骤，不能复制为 shell。所有 Python 命令使用项目 `.venv/bin/python`。",
805 +     "",
806 +     "状态：todo/doing/blocked/blocked_hardware/review/done。当前任务没有完成验收，已有能力列仅表示可复用的基础。",
807 +     "",
808 + ]
809 | for t in items:
    -  lines += [f"## {t['id']} · {t['title']}",'',f"- 阶段：{t['phase']}；依赖：{', '.join(t['dependencies']) or '无'}；状态：{t['status']}。",f"- 估算：{t['estimate_low']}–{t['estimate_high']} 人日（非承诺工期）。",f"- 已有基础：{t['existing']}",f"- 文件范围：{'；'.join('`'+x+'`' for x in t['files'])}",f"- 输入条件：{'所有依赖验收完成' if t['dependencies'] else '读完当前审核及实施方案'}。{t['blocker']}",'','实施步骤：','']
    -  lines += [f'{i}. {s}' for i,s in enumerate(t['steps'],1)]
    -  lines += ['','验证要求：','']+['- '+c for c in t['verification_commands']]
    -  lines += ['',f"验收：{t['acceptance']}",'',f"证据目录：`{t['evidence']}`。失败回退：源码回到本卡前检查点；数据库仅在隔离验证后使用本卡迁移的回退/前滚方案；已发生的平台发布不通过重跑任务回退。",'']
    - (OUT/'03-逐项任务卡.md').write_text('\n'.join(lines))
    - print('tasks',len(items),'person-days',sum(x['estimate_low'] for x in items),sum(x['estimate_high'] for x in items))
810 +     lines += [
811 +         f"## {t['id']} · {t['title']}",
812 +         "",
813 +         f"- 阶段：{t['phase']}；依赖：{', '.join(t['dependencies']) or '无'}；状态：{t['status']}。",
814 +         f"- 估算：{t['estimate_low']}–{t['estimate_high']} 人日（非承诺工期）。",
815 +         f"- 已有基础：{t['existing']}",
816 +         f"- 文件范围：{'；'.join('`' + x + '`' for x in t['files'])}",
817 +         f"- 输入条件：{'所有依赖验收完成' if t['dependencies'] else '读完当前审核及实施方案'}。{t['blocker']}",
818 +         "",
819 +         "实施步骤：",
820 +         "",
821 +     ]
822 +     lines += [f"{i}. {s}" for i, s in enumerate(t["steps"], 1)]
823 +     lines += ["", "验证要求：", ""] + ["- " + c for c in t["verification_commands"]]
824 +     lines += [
825 +         "",
826 +         f"验收：{t['acceptance']}",
827 +         "",
828 +         f"证据目录：`{t['evidence']}`。失败回退：源码回到本卡前检查点；数据库仅在隔离验证后使用本卡迁移的回退/前滚方案；已发生的平台发布不通过重跑任务回退。",
829 +         "",
830 +     ]
831 + (OUT / "03-逐项任务卡.md").write_text("\n".join(lines))
832 + print(
833 +     "tasks",
834 +     len(items),
835 +     "person-days",
836 +     sum(x["estimate_low"] for x in items),
837 +     sum(x["estimate_high"] for x in items),
838 + )
    |

unformatted: File would be reformatted
   --> artifacts/review-20260905/build-workbook.py:3:13
    |
2   | from collections import defaultdict
    - import json,re,hashlib
    - from openpyxl import Workbook,load_workbook
    - from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
3   + import json, re, hashlib
4   + from openpyxl import Workbook, load_workbook
5   + from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
6   | from openpyxl.worksheet.datavalidation import DataValidation
7   | from openpyxl.formatting.rule import FormulaRule
8   | from openpyxl.workbook.properties import CalcProperties
    - ROOT=Path(__file__).resolve().parents[2]
    - D=ROOT/'docs/v1'; A=ROOT/'artifacts/review-20260905'
    - tasks=json.loads((D/'tasks.json').read_text())['tasks']
    - checks=[
    -  ['Python 测试','通过','392 passed',0,'pytest.log','本地pytest；不代表真实平台结果'],
    -  ['Web 单测（清理后）','通过','40 passed',0,'web-tests-after-cleanup.log','保留全部有效测试'],
    -  ['Studio 单测','通过','16 passed',0,'web-tests.log','软件测试替身'],
    -  ['TS 类型（清理后）','通过','Web/Studio/合同通过',0,'typecheck-after-cleanup.log','编译类型检查'],
    -  ['Web/Studio 构建','通过','两应用构建通过',0,'build.log','Studio 大包警告'],
    -  ['Companion 单测+lint','通过','41 tests / 14 suites；lint成功',0,'android.log','主机测试，无障碍真机未验收'],
    -  ['Ruff','失败','24 errors',1,'ruff.log','原始静态检查'],
    -  ['格式检查','失败','27 files',1,'format.log','未为审计做批量格式改写'],
    -  ['Pyright','失败','12 errors',1,'pyright.log','Edge/Outbox类型合同待修'],
    -  ['Web lint（清理后）','失败','4 errors',1,'web-lint-after-cleanup.log','原5个，去掉1个无用测试变量'],
    -  ['安全扫描','无效/需重验','退出0，grep报错',0,'security.log','不能视为所有扫描规则通过'],
    -  ['默认E2E','环境污染','4173复用其他项目',1,'e2e.log','不作为本项目失败数量；Studio未运行'],
    -  ['独立端口Web smoke','部分失败','16通过/4失败/8既有跳过',1,'e2e-isolated.log','两处非精确文本定位器；不是已确认滚动故障'],
    -  ['商品专用E2E','通过','1 passed',0,'e2e-product.log','API拦截用例，不是真实数据库到真机'],
    -  ['真机盘点','通过','OnePlus Android14；四App已安装',0,'device.json','项目无障碍服务未启用'],
    -  ['本地API只读访问','通过','OpenAPI 111 paths',0,'live-api-summary.json','部署版本/外部来源未核实'],
    -  ['四平台真实发布','未执行','0/4平台本轮完整验收',None,'','本轮审核没有发布外部内容'],
9   +
10  + ROOT = Path(__file__).resolve().parents[2]
11  + D = ROOT / "docs/v1"
12  + A = ROOT / "artifacts/review-20260905"
13  + tasks = json.loads((D / "tasks.json").read_text())["tasks"]
14  + checks = [
15  +     ["Python 测试", "通过", "392 passed", 0, "pytest.log", "本地pytest；不代表真实平台结果"],
16  +     [
17  +         "Web 单测（清理后）",
18  +         "通过",
19  +         "40 passed",
20  +         0,
21  +         "web-tests-after-cleanup.log",
22  +         "保留全部有效测试",
23  +     ],
24  +     ["Studio 单测", "通过", "16 passed", 0, "web-tests.log", "软件测试替身"],
25  +     [
26  +         "TS 类型（清理后）",
27  +         "通过",
28  +         "Web/Studio/合同通过",
29  +         0,
30  +         "typecheck-after-cleanup.log",
31  +         "编译类型检查",
32  +     ],
33  +     ["Web/Studio 构建", "通过", "两应用构建通过", 0, "build.log", "Studio 大包警告"],
34  +     [
35  +         "Companion 单测+lint",
36  +         "通过",
37  +         "41 tests / 14 suites；lint成功",
38  +         0,
39  +         "android.log",
40  +         "主机测试，无障碍真机未验收",
41  +     ],
42  +     ["Ruff", "失败", "24 errors", 1, "ruff.log", "原始静态检查"],
43  +     ["格式检查", "失败", "27 files", 1, "format.log", "未为审计做批量格式改写"],
44  +     ["Pyright", "失败", "12 errors", 1, "pyright.log", "Edge/Outbox类型合同待修"],
45  +     [
46  +         "Web lint（清理后）",
47  +         "失败",
48  +         "4 errors",
49  +         1,
50  +         "web-lint-after-cleanup.log",
51  +         "原5个，去掉1个无用测试变量",
52  +     ],
53  +     ["安全扫描", "无效/需重验", "退出0，grep报错", 0, "security.log", "不能视为所有扫描规则通过"],
54  +     ["默认E2E", "环境污染", "4173复用其他项目", 1, "e2e.log", "不作为本项目失败数量；Studio未运行"],
55  +     [
56  +         "独立端口Web smoke",
57  +         "部分失败",
58  +         "16通过/4失败/8既有跳过",
59  +         1,
60  +         "e2e-isolated.log",
61  +         "两处非精确文本定位器；不是已确认滚动故障",
62  +     ],
63  +     ["商品专用E2E", "通过", "1 passed", 0, "e2e-product.log", "API拦截用例，不是真实数据库到真机"],
64  +     [
65  +         "真机盘点",
66  +         "通过",
67  +         "OnePlus Android14；四App已安装",
68  +         0,
69  +         "device.json",
70  +         "项目无障碍服务未启用",
71  +     ],
72  +     [
73  +         "本地API只读访问",
74  +         "通过",
75  +         "OpenAPI 111 paths",
76  +         0,
77  +         "live-api-summary.json",
78  +         "部署版本/外部来源未核实",
79  +     ],
80  +     ["四平台真实发布", "未执行", "0/4平台本轮完整验收", None, "", "本轮审核没有发布外部内容"],
81  | ]
    - (A/'verification.json').write_text(json.dumps({'date':'2026-09-05','checks':[dict(zip(['check','result','detail','exitCode','log','limitation'],r)) for r in checks]},ensure_ascii=False,indent=2))
    - capabilities=[
    -  ['来源库连接','未发现完整实现','待确认用户现有库类型及只读入口','V1-03~07','source检索；01审核F10','未验收'],
    -  ['商品领域','已有独立Product/Media及CRUD','Product与Content下发断点、原子保存、历史修订','V1-10/14','db.py；OperationsView.vue','软件基础已有'],
    -  ['素材领域','上传/去重/标签/分组已有','来源同步、处理就绪、可视化选择','V1-08/09','media_store.py；迁移0010','软件基础已有'],
    -  ['内容修订','已有ContentRevision与媒体关联','三平台覆盖、格式校验、公众号HTML','V1-11','content_payload.py；迁移0011','软件基础已有'],
    -  ['账号设备','记录绑定及API已有','真实账号指纹/scope/无障碍权限','V1-04/12','mobile_service.py；device.json','未真实闭环'],
    -  ['手机投递','下载hash校验与相册导出已有','任务级授权/URI与选择项对应/大文件','V1-17/18','MediaDeliveryCoordinator.kt','未真机验收'],
    -  ['发布编排','Plan/Target/Snapshot/Outbox/Intent已有','APK提交保护、统一结果语义、多目标','V1-13~22','db.py；services.py','未真实闭环'],
    -  ['闲鱼','字段预填和选图配方','Web资源断点/选错图/最终提交/对账','V1-18~22','xianyu_publish.py','未真实发布验收'],
    -  ['小红书/抖音/公众号','App已安装；内容基础可复用','执行器与实际账号权限尚待实现/确认','V1-23~26','TargetLocatorRegistry.kt；device.json','未真实发布验收'],
    -  ['上线','调试APK和部署脚本已有','真实会话/release/备份恢复/无USB验证','V1-28~30','build.gradle.kts；session.ts','未验收'],
82  + (A / "verification.json").write_text(
83  +     json.dumps(
84  +         {
85  +             "date": "2026-09-05",
86  +             "checks": [
87  +                 dict(zip(["check", "result", "detail", "exitCode", "log", "limitation"], r))
88  +                 for r in checks
89  +             ],
90  +         },
91  +         ensure_ascii=False,
92  +         indent=2,
93  +     )
94  + )
95  + capabilities = [
96  +     [
97  +         "来源库连接",
98  +         "未发现完整实现",
99  +         "待确认用户现有库类型及只读入口",
100 +         "V1-03~07",
101 +         "source检索；01审核F10",
102 +         "未验收",
103 +     ],
104 +     [
105 +         "商品领域",
106 +         "已有独立Product/Media及CRUD",
107 +         "Product与Content下发断点、原子保存、历史修订",
108 +         "V1-10/14",
109 +         "db.py；OperationsView.vue",
110 +         "软件基础已有",
111 +     ],
112 +     [
113 +         "素材领域",
114 +         "上传/去重/标签/分组已有",
115 +         "来源同步、处理就绪、可视化选择",
116 +         "V1-08/09",
117 +         "media_store.py；迁移0010",
118 +         "软件基础已有",
119 +     ],
120 +     [
121 +         "内容修订",
122 +         "已有ContentRevision与媒体关联",
123 +         "三平台覆盖、格式校验、公众号HTML",
124 +         "V1-11",
125 +         "content_payload.py；迁移0011",
126 +         "软件基础已有",
127 +     ],
128 +     [
129 +         "账号设备",
130 +         "记录绑定及API已有",
131 +         "真实账号指纹/scope/无障碍权限",
132 +         "V1-04/12",
133 +         "mobile_service.py；device.json",
134 +         "未真实闭环",
135 +     ],
136 +     [
137 +         "手机投递",
138 +         "下载hash校验与相册导出已有",
139 +         "任务级授权/URI与选择项对应/大文件",
140 +         "V1-17/18",
141 +         "MediaDeliveryCoordinator.kt",
142 +         "未真机验收",
143 +     ],
144 +     [
145 +         "发布编排",
146 +         "Plan/Target/Snapshot/Outbox/Intent已有",
147 +         "APK提交保护、统一结果语义、多目标",
148 +         "V1-13~22",
149 +         "db.py；services.py",
150 +         "未真实闭环",
151 +     ],
152 +     [
153 +         "闲鱼",
154 +         "字段预填和选图配方",
155 +         "Web资源断点/选错图/最终提交/对账",
156 +         "V1-18~22",
157 +         "xianyu_publish.py",
158 +         "未真实发布验收",
159 +     ],
160 +     [
161 +         "小红书/抖音/公众号",
162 +         "App已安装；内容基础可复用",
163 +         "执行器与实际账号权限尚待实现/确认",
164 +         "V1-23~26",
165 +         "TargetLocatorRegistry.kt；device.json",
166 +         "未真实发布验收",
167 +     ],
168 +     [
169 +         "上线",
170 +         "调试APK和部署脚本已有",
171 +         "真实会话/release/备份恢复/无USB验证",
172 +         "V1-28~30",
173 +         "build.gradle.kts；session.ts",
174 +         "未验收",
175 +     ],
176 | ]
    - platforms=[
    -  ['闲鱼','商品/多图/价格/运费/成色','APK为当前基础；API需独立确认权限','7.27.90','预填代码已有，未最终提交','身份/精确媒体/字段回读/permit/对账','单次商品发布并核对列表/详情','V1-18~22'],
    -  ['小红书','图文笔记','先探测官方分享能力；必要时受控APK UI','8.50.1','仅安装，未接执行器','分享成功不等于发布；标题正文/图序/账号','笔记结果+审核状态；图文首验','V1-23/24'],
    -  ['抖音','单视频作品','有正式scope优先API；否则已授权UI路线','39.6.0','未核实video.create实际授权','上传→创建→审核；提交后禁自动切渠道','视频ID/作品核验/账号一致','V1-23/25'],
    -  ['微信公众号','公众号图文文章','先核实后台权限和当前官方文档','微信8.0.76（非公众号能力证明）','主体/权限未知；文档正文未取到','草稿/发布/群发分开，不能默认个人微信能发','文章ID/URL+状态；只有草稿不算done','V1-23/26'],
177 + platforms = [
178 +     [
179 +         "闲鱼",
180 +         "商品/多图/价格/运费/成色",
181 +         "APK为当前基础；API需独立确认权限",
182 +         "7.27.90",
183 +         "预填代码已有，未最终提交",
184 +         "身份/精确媒体/字段回读/permit/对账",
185 +         "单次商品发布并核对列表/详情",
186 +         "V1-18~22",
187 +     ],
188 +     [
189 +         "小红书",
190 +         "图文笔记",
191 +         "先探测官方分享能力；必要时受控APK UI",
192 +         "8.50.1",
193 +         "仅安装，未接执行器",
194 +         "分享成功不等于发布；标题正文/图序/账号",
195 +         "笔记结果+审核状态；图文首验",
196 +         "V1-23/24",
197 +     ],
198 +     [
199 +         "抖音",
200 +         "单视频作品",
201 +         "有正式scope优先API；否则已授权UI路线",
202 +         "39.6.0",
203 +         "未核实video.create实际授权",
204 +         "上传→创建→审核；提交后禁自动切渠道",
205 +         "视频ID/作品核验/账号一致",
206 +         "V1-23/25",
207 +     ],
208 +     [
209 +         "微信公众号",
210 +         "公众号图文文章",
211 +         "先核实后台权限和当前官方文档",
212 +         "微信8.0.76（非公众号能力证明）",
213 +         "主体/权限未知；文档正文未取到",
214 +         "草稿/发布/群发分开，不能默认个人微信能发",
215 +         "文章ID/URL+状态；只有草稿不算done",
216 +         "V1-23/26",
217 +     ],
218 | ]
    - unknowns=[
    -  ['U01','商品库在哪、主键和字段是什么','来源管理员','库类型/只读入口/10条脱敏样本','V1-03/05/06','未确认','平台核心开发可继续'],
    -  ['U02','素材库原文件如何访问','来源管理员','20条样本/附件获取/大小/游标','V1-03/05/06','未确认','不把缩略图当原件'],
    -  ['U03','四平台账号授权与能力','账号管理员','账号指纹/当前scope/到期/允许模式','V1-12/23~26','未确认','只阻塞权限不明的平台'],
    -  ['U04','公众号主体、发布和草稿权限','公众号管理员','后台权限截图或脱敏接口结果','V1-26','未确认','微信安装不等于公众号授权'],
    -  ['U05','真机绑定环境和无障碍服务','设备管理员','确认环境、启用项目服务、只读回执','V1-04','服务未启用','ADB盘点已完成'],
    -  ['U06','实际商品/素材格式及规模','业务负责人','原始样本、容量、并发账号数量','V1-08/23/28','未确认','先一设备/一账号串行'],
    -  ['U07','Release签名及生产部署归属','部署管理员','secret_ref/环境地址/备份位置','V1-29','未确认','不复制明文密钥到计划'],
219 + unknowns = [
220 +     [
221 +         "U01",
222 +         "商品库在哪、主键和字段是什么",
223 +         "来源管理员",
224 +         "库类型/只读入口/10条脱敏样本",
225 +         "V1-03/05/06",
226 +         "未确认",
227 +         "平台核心开发可继续",
228 +     ],
229 +     [
230 +         "U02",
231 +         "素材库原文件如何访问",
232 +         "来源管理员",
233 +         "20条样本/附件获取/大小/游标",
234 +         "V1-03/05/06",
235 +         "未确认",
236 +         "不把缩略图当原件",
237 +     ],
238 +     [
239 +         "U03",
240 +         "四平台账号授权与能力",
241 +         "账号管理员",
242 +         "账号指纹/当前scope/到期/允许模式",
243 +         "V1-12/23~26",
244 +         "未确认",
245 +         "只阻塞权限不明的平台",
246 +     ],
247 +     [
248 +         "U04",
249 +         "公众号主体、发布和草稿权限",
250 +         "公众号管理员",
251 +         "后台权限截图或脱敏接口结果",
252 +         "V1-26",
253 +         "未确认",
254 +         "微信安装不等于公众号授权",
255 +     ],
256 +     [
257 +         "U05",
258 +         "真机绑定环境和无障碍服务",
259 +         "设备管理员",
260 +         "确认环境、启用项目服务、只读回执",
261 +         "V1-04",
262 +         "服务未启用",
263 +         "ADB盘点已完成",
264 +     ],
265 +     [
266 +         "U06",
267 +         "实际商品/素材格式及规模",
268 +         "业务负责人",
269 +         "原始样本、容量、并发账号数量",
270 +         "V1-08/23/28",
271 +         "未确认",
272 +         "先一设备/一账号串行",
273 +     ],
274 +     [
275 +         "U07",
276 +         "Release签名及生产部署归属",
277 +         "部署管理员",
278 +         "secret_ref/环境地址/备份位置",
279 +         "V1-29",
280 +         "未确认",
281 +         "不复制明文密钥到计划",
282 +     ],
283 | ]
    - report=(D/'01-项目审核.md').read_text()
    - findings=[]
    - for m in re.finditer(r'^### (F\d+) / (P\d)：([^\n]+)\n(.*?)(?=\n### |\n## |\Z)',report,re.M|re.S):
    -  num,prio,title,body=m.groups();findings.append([num,prio,title,body.strip(),'静态证据+本轮运行；具体限制见正文','待实施修复'])
284 + report = (D / "01-项目审核.md").read_text()
285 + findings = []
286 + for m in re.finditer(
287 +     r"^### (F\d+) / (P\d)：([^\n]+)\n(.*?)(?=\n### |\n## |\Z)", report, re.M | re.S
288 + ):
289 +     num, prio, title, body = m.groups()
290 +     findings.append(
291 +         [num, prio, title, body.strip(), "静态证据+本轮运行；具体限制见正文", "待实施修复"]
292 +     )
293 | # Build reusable, printable tables.
    - wb=Workbook();wb.remove(wb.active)
    - wb.calculation=CalcProperties(calcId=191029,fullCalcOnLoad=True)
    - navy='17324D';teal='087F8C';light='EAF2F8';gray='526577'
    - def sheet(name,headers,rows,widths=None,height=58):
    -  ws=wb.create_sheet(name);ws.append(headers)
    -  for row in rows:ws.append(row)
    -  ws.freeze_panes='C2' if len(headers)>4 else 'A2';ws.auto_filter.ref=ws.dimensions
    -  ws.sheet_view.showGridLines=False
    -  for c in ws[1]:c.font=Font(name='微软雅黑',bold=True,color='FFFFFF',size=11);c.fill=PatternFill('solid',fgColor=navy);c.alignment=Alignment(wrap_text=True,vertical='center')
    -  ws.row_dimensions[1].height=32
    -  for row in ws.iter_rows(min_row=2):
    -   for c in row:
    -    c.font=Font(name='微软雅黑',size=10,color='243B53');c.alignment=Alignment(vertical='top',wrap_text=True)
    -    if c.row%2==0:c.fill=PatternFill('solid',fgColor='F0F5F9')
    -   ws.row_dimensions[row[0].row].height=height
    -  for i in range(1,len(headers)+1):ws.column_dimensions[__import__('openpyxl').utils.get_column_letter(i)].width=(widths or {}).get(i,24)
    -  ws.sheet_properties.pageSetUpPr.fitToPage=True
    -  ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
    -  ws.print_title_rows='1:1';ws.print_options.horizontalCentered=True
    -  ws.oddFooter.center.text='第 &P 页 / 共 &N 页';ws.oddFooter.right.text='2026-09-05 重审基线'
    -  return ws
    - summary=[
    -  ['审核结论','基础可复用；一键来源库到四平台发布尚未完成验收','详见01-项目审核.md'],
    -  ['八个业务里程碑','本轮完整验收0/8','不是代码完成率为0；按证据核验，不沿用旧40%'],
    -  ['计划任务数',30,'由任务明细维护'],
    -  ['已验收任务数','=COUNTIF(\'开发任务\'!G2:G31,"done")','只有全部验收满足才改done'],
    -  ['任务验收比例','=B5/B4','任务数口径，无工作量加权；不代表已有源码比例'],
    -  ['估算下限人日',"=SUM('开发任务'!E2:E31)",'一名跨端开发者，审核模型输出'],
    -  ['估算上限人日',"=SUM('开发任务'!F2:F31)",'平台审批/资料等待另计'],
    -  ['日历参考','单人约9–17周（5有效开发日/周）','规划估计非承诺；并行不能直接除模型数'],
    -  ['首要断点','Product保存后误走Content下发；相册索引可能选错图','先V1-10/14/18；保留正确的既有测试'],
    -  ['当前真机','OnePlus Android14，项目无障碍服务未启用','四平台App已安装；无实际发布动作'],
    -  ['本轮清理','2个孤立mock源码 + 1个测试无用变量；撤下旧计划/制表脚本','9个文件有清理前备份；有效测试保留'],
    -  ['入口','docs/v1/README.md','03任务卡供模型执行；tasks.json为结构化来源'],
    -  ['版本口径','本地源码重审，2026-09-05','不推断远端服务已同步或平台权限已获批'],
294 + wb = Workbook()
295 + wb.remove(wb.active)
296 + wb.calculation = CalcProperties(calcId=191029, fullCalcOnLoad=True)
297 + navy = "17324D"
298 + teal = "087F8C"
299 + light = "EAF2F8"
300 + gray = "526577"
301 +
302 +
303 + def sheet(name, headers, rows, widths=None, height=58):
304 +     ws = wb.create_sheet(name)
305 +     ws.append(headers)
306 +     for row in rows:
307 +         ws.append(row)
308 +     ws.freeze_panes = "C2" if len(headers) > 4 else "A2"
309 +     ws.auto_filter.ref = ws.dimensions
310 +     ws.sheet_view.showGridLines = False
311 +     for c in ws[1]:
312 +         c.font = Font(name="微软雅黑", bold=True, color="FFFFFF", size=11)
313 +         c.fill = PatternFill("solid", fgColor=navy)
314 +         c.alignment = Alignment(wrap_text=True, vertical="center")
315 +     ws.row_dimensions[1].height = 32
316 +     for row in ws.iter_rows(min_row=2):
317 +         for c in row:
318 +             c.font = Font(name="微软雅黑", size=10, color="243B53")
319 +             c.alignment = Alignment(vertical="top", wrap_text=True)
320 +             if c.row % 2 == 0:
321 +                 c.fill = PatternFill("solid", fgColor="F0F5F9")
322 +         ws.row_dimensions[row[0].row].height = height
323 +     for i in range(1, len(headers) + 1):
324 +         ws.column_dimensions[__import__("openpyxl").utils.get_column_letter(i)].width = (
325 +             widths or {}
326 +         ).get(i, 24)
327 +     ws.sheet_properties.pageSetUpPr.fitToPage = True
328 +     ws.page_setup.orientation = "landscape"
329 +     ws.page_setup.paperSize = ws.PAPERSIZE_A3
330 +     ws.page_setup.fitToWidth = 1
331 +     ws.page_setup.fitToHeight = 0
332 +     ws.print_title_rows = "1:1"
333 +     ws.print_options.horizontalCentered = True
334 +     ws.oddFooter.center.text = "第 &P 页 / 共 &N 页"
335 +     ws.oddFooter.right.text = "2026-09-05 重审基线"
336 +     return ws
337 +
338 +
339 + summary = [
340 +     ["审核结论", "基础可复用；一键来源库到四平台发布尚未完成验收", "详见01-项目审核.md"],
341 +     ["八个业务里程碑", "本轮完整验收0/8", "不是代码完成率为0；按证据核验，不沿用旧40%"],
342 +     ["计划任务数", 30, "由任务明细维护"],
343 +     ["已验收任务数", "=COUNTIF('开发任务'!G2:G31,\"done\")", "只有全部验收满足才改done"],
344 +     ["任务验收比例", "=B5/B4", "任务数口径，无工作量加权；不代表已有源码比例"],
345 +     ["估算下限人日", "=SUM('开发任务'!E2:E31)", "一名跨端开发者，审核模型输出"],
346 +     ["估算上限人日", "=SUM('开发任务'!F2:F31)", "平台审批/资料等待另计"],
347 +     ["日历参考", "单人约9–17周（5有效开发日/周）", "规划估计非承诺；并行不能直接除模型数"],
348 +     [
349 +         "首要断点",
350 +         "Product保存后误走Content下发；相册索引可能选错图",
351 +         "先V1-10/14/18；保留正确的既有测试",
352 +     ],
353 +     ["当前真机", "OnePlus Android14，项目无障碍服务未启用", "四平台App已安装；无实际发布动作"],
354 +     [
355 +         "本轮清理",
356 +         "2个孤立mock源码 + 1个测试无用变量；撤下旧计划/制表脚本",
357 +         "9个文件有清理前备份；有效测试保留",
358 +     ],
359 +     ["入口", "docs/v1/README.md", "03任务卡供模型执行；tasks.json为结构化来源"],
360 +     ["版本口径", "本地源码重审，2026-09-05", "不推断远端服务已同步或平台权限已获批"],
361 | ]
    - ws=sheet('总览',['项目','当前值','说明'],summary,{1:25,2:70,3:75},42);ws['B6'].number_format='0%'
362 + ws = sheet("总览", ["项目", "当前值", "说明"], summary, {1: 25, 2: 70, 3: 75}, 42)
363 + ws["B6"].number_format = "0%"
364 | # row checks: header=1; task count row4; done row5; ratio row6.
    - rows=[]
365 + rows = []
366 | for t in tasks:
    -  rows.append([t['id'],t['title'],t['phase'],', '.join(t['dependencies']) or '无',t['estimate_low'],t['estimate_high'],t['status'],t['existing'],t['blocker'] or '依赖满足后可领取',t['owner'],t['acceptance'],t['evidence']])
    - ws=sheet('开发任务',['ID','任务','阶段','依赖','人日下限','人日上限','状态','已有基础（非验收）','阻塞/启动条件','负责人','完成验收','证据目录'],rows,{1:12,2:35,3:22,4:32,5:12,6:12,7:16,8:58,9:46,10:16,11:78,12:32},92)
    - dv=DataValidation(type='list',formula1='"todo,doing,blocked,blocked_hardware,review,done"');dv.error='请选择有效状态';dv.errorTitle='状态错误';dv.showErrorMessage=True;ws.add_data_validation(dv);dv.add('G2:G31')
    - for val,col in [('done','D9EAD3'),('blocked','FCE4D6'),('review','FFF2CC')]:ws.conditional_formatting.add('G2:G31',FormulaRule(formula=[f'G2="{val}"'],fill=PatternFill('solid',fgColor=col)))
    - rows=[]
367 +     rows.append(
368 +         [
369 +             t["id"],
370 +             t["title"],
371 +             t["phase"],
372 +             ", ".join(t["dependencies"]) or "无",
373 +             t["estimate_low"],
374 +             t["estimate_high"],
375 +             t["status"],
376 +             t["existing"],
377 +             t["blocker"] or "依赖满足后可领取",
378 +             t["owner"],
379 +             t["acceptance"],
380 +             t["evidence"],
381 +         ]
382 +     )
383 + ws = sheet(
384 +     "开发任务",
385 +     [
386 +         "ID",
387 +         "任务",
388 +         "阶段",
389 +         "依赖",
390 +         "人日下限",
391 +         "人日上限",
392 +         "状态",
393 +         "已有基础（非验收）",
394 +         "阻塞/启动条件",
395 +         "负责人",
396 +         "完成验收",
397 +         "证据目录",
398 +     ],
399 +     rows,
400 +     {1: 12, 2: 35, 3: 22, 4: 32, 5: 12, 6: 12, 7: 16, 8: 58, 9: 46, 10: 16, 11: 78, 12: 32},
401 +     92,
402 + )
403 + dv = DataValidation(type="list", formula1='"todo,doing,blocked,blocked_hardware,review,done"')
404 + dv.error = "请选择有效状态"
405 + dv.errorTitle = "状态错误"
406 + dv.showErrorMessage = True
407 + ws.add_data_validation(dv)
408 + dv.add("G2:G31")
409 + for val, col in [("done", "D9EAD3"), ("blocked", "FCE4D6"), ("review", "FFF2CC")]:
410 +     ws.conditional_formatting.add(
411 +         "G2:G31", FormulaRule(formula=[f'G2="{val}"'], fill=PatternFill("solid", fgColor=col))
412 +     )
413 + rows = []
414 + for t in tasks:
415 +     rows.append(
416 +         [
417 +             t["id"],
418 +             t["title"],
419 +             "\n".join(t["files"]),
420 +             "\n".join(f"{i}. {s}" for i, s in enumerate(t["steps"], 1)),
421 +             "\n".join(t["verification_commands"]),
422 +             t["acceptance"],
423 +             t["evidence"],
424 +         ]
425 +     )
426 + sheet(
427 +     "实施步骤",
428 +     ["ID", "任务", "修改范围", "按顺序实施", "验收命令/操作", "通过标准", "证据目录"],
429 +     rows,
430 +     {1: 12, 2: 36, 3: 70, 4: 115, 5: 80, 6: 75, 7: 32},
431 +     205,
432 + )
433 + phase = defaultdict(lambda: [0, 0, []])
434 | for t in tasks:
    -  rows.append([t['id'],t['title'],'\n'.join(t['files']),'\n'.join(f'{i}. {s}' for i,s in enumerate(t['steps'],1)),'\n'.join(t['verification_commands']),t['acceptance'],t['evidence']])
    - sheet('实施步骤',['ID','任务','修改范围','按顺序实施','验收命令/操作','通过标准','证据目录'],rows,{1:12,2:36,3:70,4:115,5:80,6:75,7:32},205)
    - phase=defaultdict(lambda:[0,0,[]])
    - for t in tasks:phase[t['phase']][0]+=t['estimate_low'];phase[t['phase']][1]+=t['estimate_high'];phase[t['phase']][2].append(t['id'])
    - sheet('阶段安排',['阶段','任务范围','下限人日','上限人日','交付门','外部等待'],[[p,', '.join(x[2]),x[0],x[1],{'M0 基线':'来源盘点、设备健康、工程门','M1 来源与内容':'真实库同步+商品素材可编辑','M2 发布核心':'冻结快照+互斥+APK收件/媒体授权','M3 闲鱼':'正确预填→一次提交→结果对账','M4 三内容平台':'小红书/抖音/公众号分别验收','M5 完整V1':'四平台批次+恢复+release+8里程碑'}[p],'账号权限/库入口/平台审核按实际等待，未计入人日'] for p,x in phase.items()],{1:24,2:70,3:14,4:14,5:58,6:62},66)
    - sheet('当前能力',['能力','已有实现','缺口','任务','代码证据','本轮状态'],capabilities,{1:22,2:50,3:72,4:22,5:48,6:25},72)
    - sheet('审核问题',['ID','优先级','问题','证据与影响','证据口径','状态'],findings,{1:12,2:12,3:55,4:130,5:45,6:24},190)
    - sheet('平台矩阵',['平台','V1内容类型','渠道方案','当前安装版本','现状','实施关键点','独立验收','任务'],platforms,{1:22,2:34,3:62,4:43,5:55,6:68,7:57,8:22},112)
    - accept=[]
    - for line in (D/'02-实施方案.md').read_text().splitlines():
    -  if re.match(r'\| A\d+',line):accept.append([x.strip() for x in line.strip('|').split('|')]+['未执行',''])
    - sheet('验收用例',['ID','输入或故障','期望结果','执行状态','证据'],accept,{1:12,2:75,3:90,4:20,5:45},60)
    - sheet('验证记录',['检查','结果','明细','退出码','日志','限制'],checks,{1:34,2:24,3:45,4:14,5:46,6:85},65)
    - sheet('待确认事项',['ID','待确认','提供人','所需输入','阻塞任务','状态','独立推进'],unknowns,{1:12,2:50,3:20,4:68,5:25,6:24,7:50},65)
    - cleanup=json.loads((A/'cleanup-manifest.json').read_text())
    - sheet('清理记录',['原路径','处理','原SHA256','恢复方式'],[[x['path'],'移除测试无用解构变量' if x['action'].startswith('remove unused') else '移除孤立mock或旧计划/制表产物',x['sha256'],'artifacts/review-20260905/cleanup-backup.zip 内原相对路径'] for x in cleanup],{1:100,2:48,3:76,4:80},50)
435 +     phase[t["phase"]][0] += t["estimate_low"]
436 +     phase[t["phase"]][1] += t["estimate_high"]
437 +     phase[t["phase"]][2].append(t["id"])
438 + sheet(
439 +     "阶段安排",
440 +     ["阶段", "任务范围", "下限人日", "上限人日", "交付门", "外部等待"],
441 +     [
442 +         [
443 +             p,
444 +             ", ".join(x[2]),
445 +             x[0],
446 +             x[1],
447 +             {
448 +                 "M0 基线": "来源盘点、设备健康、工程门",
449 +                 "M1 来源与内容": "真实库同步+商品素材可编辑",
450 +                 "M2 发布核心": "冻结快照+互斥+APK收件/媒体授权",
451 +                 "M3 闲鱼": "正确预填→一次提交→结果对账",
452 +                 "M4 三内容平台": "小红书/抖音/公众号分别验收",
453 +                 "M5 完整V1": "四平台批次+恢复+release+8里程碑",
454 +             }[p],
455 +             "账号权限/库入口/平台审核按实际等待，未计入人日",
456 +         ]
457 +         for p, x in phase.items()
458 +     ],
459 +     {1: 24, 2: 70, 3: 14, 4: 14, 5: 58, 6: 62},
460 +     66,
461 + )
462 + sheet(
463 +     "当前能力",
464 +     ["能力", "已有实现", "缺口", "任务", "代码证据", "本轮状态"],
465 +     capabilities,
466 +     {1: 22, 2: 50, 3: 72, 4: 22, 5: 48, 6: 25},
467 +     72,
468 + )
469 + sheet(
470 +     "审核问题",
471 +     ["ID", "优先级", "问题", "证据与影响", "证据口径", "状态"],
472 +     findings,
473 +     {1: 12, 2: 12, 3: 55, 4: 130, 5: 45, 6: 24},
474 +     190,
475 + )
476 + sheet(
477 +     "平台矩阵",
478 +     ["平台", "V1内容类型", "渠道方案", "当前安装版本", "现状", "实施关键点", "独立验收", "任务"],
479 +     platforms,
480 +     {1: 22, 2: 34, 3: 62, 4: 43, 5: 55, 6: 68, 7: 57, 8: 22},
481 +     112,
482 + )
483 + accept = []
484 + for line in (D / "02-实施方案.md").read_text().splitlines():
485 +     if re.match(r"\| A\d+", line):
486 +         accept.append([x.strip() for x in line.strip("|").split("|")] + ["未执行", ""])
487 + sheet(
488 +     "验收用例",
489 +     ["ID", "输入或故障", "期望结果", "执行状态", "证据"],
490 +     accept,
491 +     {1: 12, 2: 75, 3: 90, 4: 20, 5: 45},
492 +     60,
493 + )
494 + sheet(
495 +     "验证记录",
496 +     ["检查", "结果", "明细", "退出码", "日志", "限制"],
497 +     checks,
498 +     {1: 34, 2: 24, 3: 45, 4: 14, 5: 46, 6: 85},
499 +     65,
500 + )
501 + sheet(
502 +     "待确认事项",
503 +     ["ID", "待确认", "提供人", "所需输入", "阻塞任务", "状态", "独立推进"],
504 +     unknowns,
505 +     {1: 12, 2: 50, 3: 20, 4: 68, 5: 25, 6: 24, 7: 50},
506 +     65,
507 + )
508 + cleanup = json.loads((A / "cleanup-manifest.json").read_text())
509 + sheet(
510 +     "清理记录",
511 +     ["原路径", "处理", "原SHA256", "恢复方式"],
512 +     [
513 +         [
514 +             x["path"],
515 +             "移除测试无用解构变量"
516 +             if x["action"].startswith("remove unused")
517 +             else "移除孤立mock或旧计划/制表产物",
518 +             x["sha256"],
519 +             "artifacts/review-20260905/cleanup-backup.zip 内原相对路径",
520 +         ]
521 +         for x in cleanup
522 +     ],
523 +     {1: 100, 2: 48, 3: 76, 4: 80},
524 +     50,
525 + )
526 | for ws in wb:
    -  ws.sheet_properties.tabColor=teal if ws.title in ['总览','开发任务','实施步骤'] else navy
    - output=ROOT.parent/'LAMDA云控系统_V1重审开发计划_20260905.xlsx'
527 +     ws.sheet_properties.tabColor = teal if ws.title in ["总览", "开发任务", "实施步骤"] else navy
528 + output = ROOT.parent / "LAMDA云控系统_V1重审开发计划_20260905.xlsx"
529 | wb.save(output)
530 | # Cache these four deterministic overview formulas for read-only spreadsheet previews.
    - import zipfile,io,xml.etree.ElementTree as ET
    - ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    - buffer=io.BytesIO()
    - with zipfile.ZipFile(output) as zin, zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as zout:
    -  for info in zin.infolist():
    -   data=zin.read(info.filename)
    -   if info.filename=='xl/worksheets/sheet1.xml':
    -    tree=ET.fromstring(data)
    -    done=sum(t['status']=='done' for t in tasks)
    -    values={'B5':done,'B6':done/len(tasks),'B7':sum(t['estimate_low'] for t in tasks),'B8':sum(t['estimate_high'] for t in tasks)}
    -    for cell in tree.findall('.//m:c',ns):
    -     if cell.attrib.get('r') in values:
    -      v=cell.find('m:v',ns)
    -      if v is None:v=ET.SubElement(cell,'{'+ns['m']+'}v')
    -      v.text=str(values[cell.attrib['r']])
    -    data=ET.tostring(tree,encoding='utf-8')
    -   zout.writestr(info,data)
531 + import zipfile, io, xml.etree.ElementTree as ET
532 +
533 + ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
534 + buffer = io.BytesIO()
535 + with zipfile.ZipFile(output) as zin, zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zout:
536 +     for info in zin.infolist():
537 +         data = zin.read(info.filename)
538 +         if info.filename == "xl/worksheets/sheet1.xml":
539 +             tree = ET.fromstring(data)
540 +             done = sum(t["status"] == "done" for t in tasks)
541 +             values = {
542 +                 "B5": done,
543 +                 "B6": done / len(tasks),
544 +                 "B7": sum(t["estimate_low"] for t in tasks),
545 +                 "B8": sum(t["estimate_high"] for t in tasks),
546 +             }
547 +             for cell in tree.findall(".//m:c", ns):
548 +                 if cell.attrib.get("r") in values:
549 +                     v = cell.find("m:v", ns)
550 +                     if v is None:
551 +                         v = ET.SubElement(cell, "{" + ns["m"] + "}v")
552 +                     v.text = str(values[cell.attrib["r"]])
553 +             data = ET.tostring(tree, encoding="utf-8")
554 +         zout.writestr(info, data)
555 | output.write_bytes(buffer.getvalue())
    - cached=load_workbook(output,data_only=True)
    - assert [cached['总览'][x].value for x in ['B5','B6','B7','B8']]==[done,done/len(tasks),45,84]
556 + cached = load_workbook(output, data_only=True)
557 + assert [cached["总览"][x].value for x in ["B5", "B6", "B7", "B8"]] == [
558 +     done,
559 +     done / len(tasks),
560 +     45,
561 +     84,
562 + ]
563 | # Validate actual file contents and cross-document consistency.
    - r=load_workbook(output,data_only=False)
    - assert len(r['开发任务']['A'])==31
    - assert len(tasks)==30 and len({t['id'] for t in tasks})==30
    - assert sum(t['estimate_low'] for t in tasks)==45
    - assert sum(t['estimate_high'] for t in tasks)==84
    - assert r['总览']['B5'].value=='=COUNTIF(\'开发任务\'!G2:G31,"done")'
    - assert r['总览']['B6'].value=='=B5/B4'
    - assert len(accept)==18 and len(findings)==12
    - assert len(r.sheetnames)==11
564 + r = load_workbook(output, data_only=False)
565 + assert len(r["开发任务"]["A"]) == 31
566 + assert len(tasks) == 30 and len({t["id"] for t in tasks}) == 30
567 + assert sum(t["estimate_low"] for t in tasks) == 45
568 + assert sum(t["estimate_high"] for t in tasks) == 84
569 + assert r["总览"]["B5"].value == "=COUNTIF('开发任务'!G2:G31,\"done\")"
570 + assert r["总览"]["B6"].value == "=B5/B4"
571 + assert len(accept) == 18 and len(findings) == 12
572 + assert len(r.sheetnames) == 11
573 | for ws in r:
    -  assert ws.max_row>1 and ws.freeze_panes
    -  for row in ws:
    -   for c in row:
    -    assert not (isinstance(c.value,str) and c.value in ['#REF!','#DIV/0!','#VALUE!'])
    - (A/'workbook-validation.json').write_text(json.dumps({'sheets':r.sheetnames,'tasks':30,'findings':12,'acceptanceCases':18,'estimatePersonDays':[45,84],'formulaReferences':'validated; recalculates on opening in spreadsheet application','sha256':hashlib.sha256(output.read_bytes()).hexdigest()},ensure_ascii=False,indent=2))
574 +     assert ws.max_row > 1 and ws.freeze_panes
575 +     for row in ws:
576 +         for c in row:
577 +             assert not (isinstance(c.value, str) and c.value in ["#REF!", "#DIV/0!", "#VALUE!"])
578 + (A / "workbook-validation.json").write_text(
579 +     json.dumps(
580 +         {
581 +             "sheets": r.sheetnames,
582 +             "tasks": 30,
583 +             "findings": 12,
584 +             "acceptanceCases": 18,
585 +             "estimatePersonDays": [45, 84],
586 +             "formulaReferences": "validated; recalculates on opening in spreadsheet application",
587 +             "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
588 +         },
589 +         ensure_ascii=False,
590 +         indent=2,
591 +     )
592 + )
593 | print(output)
    - print('Validated 11 sheets, 30 tasks, 12 findings, 18 acceptance cases; estimates 45–84 person-days.')
594 + print(
595 +     "Validated 11 sheets, 30 tasks, 12 findings, 18 acceptance cases; estimates 45–84 person-days."
596 + )
    |

unformatted: File would be reformatted
   --> docs/v1/source-mapping.md:78:24
    |
77  |     # 1. 验证必填字段
    -     validate_required(['product_id', 'title', 'description', 'price', 'updated_at'], row)
    -     
78  +     validate_required(["product_id", "title", "description", "price", "updated_at"], row)
79  +
80  |     # 2. 类型转换
    -     price_amount = Decimal(row['price'])
    -     if price_amount < Decimal('0.01'):
81  +     price_amount = Decimal(row["price"])
82  +     if price_amount < Decimal("0.01"):
83  |         raise ValueError("price must be >= 0.01")
    -     
84  +
85  |     # 3. 媒体引用解析
86  |     media_refs = []
    -     if row.get('media_refs'):
    -         media_refs = [ref.strip() for ref in row['media_refs'].replace(';', ',').split(',') if ref.strip()]
    -     
87  +     if row.get("media_refs"):
88  +         media_refs = [
89  +             ref.strip() for ref in row["media_refs"].replace(";", ",").split(",") if ref.strip()
90  +         ]
91  +
92  |     # 4. 创建或更新 Product
93  |     product = upsert_product(
    -         external_id=row['product_id'],
94  +         external_id=row["product_id"],
95  |         source_connection_id=connection_id,
    -         title=row['title'],
    -         description=row['description'],
96  +         title=row["title"],
97  +         description=row["description"],
98  |         price_amount=price_amount,
    -         price_currency='CNY',
    -         stock_quantity=int(row['stock']) if row.get('stock') else None,
99  +         price_currency="CNY",
100 +         stock_quantity=int(row["stock"]) if row.get("stock") else None,
101 |         metadata={
    -             'category': row.get('category'),
    -             'condition': row.get('condition'),
102 +             "category": row.get("category"),
103 +             "condition": row.get("condition"),
104 |         },
105 |         media_refs=media_refs,
106 |     )
    -     
107 +
108 |     # 5. 记录 SourceRecordLink
109 |     record_source_link(
110 |         connection_id=connection_id,
    -         entity_kind='product',
    -         external_id=row['product_id'],
111 +         entity_kind="product",
112 +         external_id=row["product_id"],
113 |         internal_id=product.id,
    -         source_version=parse_timestamp(row['updated_at']),
114 +         source_version=parse_timestamp(row["updated_at"]),
115 |         source_hash=compute_hash(row),
116 |     )
    -     
117 +
118 |     return product
--------------------------------------------------------------------------------
125 |     # 1. 验证必填字段
    -     validate_required(['file_name', 'file_path', 'content_type', 'size_bytes', 'sha256'], row)
    -     
126 +     validate_required(["file_name", "file_path", "content_type", "size_bytes", "sha256"], row)
127 +
128 |     # 2. 读取原文件
    -     file_full_path = base_path / row['file_path']
129 +     file_full_path = base_path / row["file_path"]
130 |     if not file_full_path.exists():
131 |         raise FileNotFoundError(f"Media file not found: {file_full_path}")
    -     
132 +
133 |     file_content = file_full_path.read_bytes()
134 |     actual_sha256 = hashlib.sha256(file_content).hexdigest()
    -     
135 +
136 |     # 3. 验证哈希
    -     if actual_sha256 != row['sha256']:
137 +     if actual_sha256 != row["sha256"]:
138 |         raise ValueError(f"SHA256 mismatch for {row['file_name']}")
    -     
139 +
140 |     # 4. 上传到 S3
141 |     object_key = f"media/{tenant_id}/{actual_sha256[:2]}/{actual_sha256}"
142 |     s3_client.put_object(Bucket=bucket, Key=object_key, Body=file_content)
    -     
143 +
144 |     # 5. 注册 MediaAsset
145 |     asset = upsert_media_asset(
    -         external_id=row['file_name'],
146 +         external_id=row["file_name"],
147 |         source_connection_id=connection_id,
148 |         sha256=actual_sha256,
149 |         object_key=object_key,
    -         content_type=row['content_type'],
    -         size_bytes=int(row['size_bytes']),
150 +         content_type=row["content_type"],
151 +         size_bytes=int(row["size_bytes"]),
152 |         metadata={
    -             'file_name': row['file_name'],
    -             'width': int(row['width']) if row.get('width') else None,
    -             'height': int(row['height']) if row.get('height') else None,
153 +             "file_name": row["file_name"],
154 +             "width": int(row["width"]) if row.get("width") else None,
155 +             "height": int(row["height"]) if row.get("height") else None,
156 |         },
157 |     )
    -     
158 +
159 |     # 6. 记录 SourceRecordLink
160 |     record_source_link(
161 |         connection_id=connection_id,
    -         entity_kind='media',
    -         external_id=row['file_name'],
162 +         entity_kind="media",
163 +         external_id=row["file_name"],
164 |         internal_id=asset.id,
    -         source_version=parse_timestamp(row['file_mtime']),
165 +         source_version=parse_timestamp(row["file_mtime"]),
166 |         source_hash=actual_sha256,
167 |     )
    -     
168 +
169 |     return asset
    |

unformatted: File would be reformatted
  --> edge/gateway/src/cloudctl_edge/adb_debug.py:86:42
   |
85 |                 raise AdbDebugError("UI tree does not accept caller parameters")
   -             content = await self._runner(
   -                 self._argv("exec-out", "uiautomator", "dump", "/dev/tty")
   -             )
86 +             content = await self._runner(self._argv("exec-out", "uiautomator", "dump", "/dev/tty"))
87 |             self._validate_capture(content)
   |

unformatted: File would be reformatted
   --> edge/gateway/src/cloudctl_edge/spool.py:261:79
    |
260 |             self._connection.execute(
    -                 "UPDATE debug_grants SET revoked_at = COALESCE(revoked_at, ?) "
    -                 "WHERE session_id = ?",
261 +                 "UPDATE debug_grants SET revoked_at = COALESCE(revoked_at, ?) WHERE session_id = ?",
262 |                 (datetime.now(UTC).isoformat(), session_id),
    |

unformatted: File would be reformatted
   --> scripts/benchmark_media_references.py:17:29
    |
16  | from cloudctl_api.app import create_app
    - from cloudctl_api.db import ContentItemRow, ContentRevisionMediaRow, ContentRevisionRow, MediaAssetRow
17  + from cloudctl_api.db import (
18  +     ContentItemRow,
19  +     ContentRevisionMediaRow,
20  +     ContentRevisionRow,
21  +     MediaAssetRow,
22  + )
23  | from cloudctl_api.settings import Settings
--------------------------------------------------------------------------------
31  |     with tempfile.TemporaryDirectory(prefix="cloudctl-benchmark-") as directory:
    -         app = create_app(Settings(
    -             env="test", repository_mode="sqlite", sqlite_path=Path(directory) / "bench.db",
    -             dev_auth_bypass=True,
    -         ))
32  +         app = create_app(
33  +             Settings(
34  +                 env="test",
35  +                 repository_mode="sqlite",
36  +                 sqlite_path=Path(directory) / "bench.db",
37  +                 dev_auth_bypass=True,
38  +             )
39  +         )
40  |         async with app.router.lifespan_context(app):
41  |             database = app.state.database
42  |             now = datetime.now(UTC)
43  |             async with database.unit_of_work() as session:
    -                 await session.execute(insert(MediaAssetRow), [
    -                     dict(id=name, tenant_id=TENANT, sha256=digest * 64, object_key=name,
    -                          content_type="image/jpeg", size_bytes=32, metadata_json={}, created_at=now)
    -                     for name, digest in (("target", "a"), ("other", "b"))
    -                 ])
    -                 await session.execute(insert(ContentItemRow), [
    -                     dict(id="content", tenant_id=TENANT, title="Benchmark", created_by=USER,
    -                          status="ACTIVE", created_at=now)
    -                 ])
44  +                 await session.execute(
45  +                     insert(MediaAssetRow),
46  +                     [
47  +                         dict(
48  +                             id=name,
49  +                             tenant_id=TENANT,
50  +                             sha256=digest * 64,
51  +                             object_key=name,
52  +                             content_type="image/jpeg",
53  +                             size_bytes=32,
54  +                             metadata_json={},
55  +                             created_at=now,
56  +                         )
57  +                         for name, digest in (("target", "a"), ("other", "b"))
58  +                     ],
59  +                 )
60  +                 await session.execute(
61  +                     insert(ContentItemRow),
62  +                     [
63  +                         dict(
64  +                             id="content",
65  +                             tenant_id=TENANT,
66  +                             title="Benchmark",
67  +                             created_by=USER,
68  +                             status="ACTIVE",
69  +                             created_at=now,
70  +                         )
71  +                     ],
72  +                 )
73  |                 for start in range(0, size, 500):
74  |                     indexes = range(start, min(start + 500, size))
    -                     await session.execute(insert(ContentRevisionRow), [
    -                         dict(id=f"revision-{i:08}", tenant_id=TENANT, content_id="content",
    -                              revision_no=i + 1, payload={"mediaAssetIds": ["target" if i < matches else "other"]},
    -                              payload_sha256="c" * 64, created_by=USER, created_at=now)
    -                         for i in indexes
    -                     ])
    -                     await session.execute(insert(ContentRevisionMediaRow), [
    -                         dict(id=f"reference-{i:08}", tenant_id=TENANT, content_id="content",
    -                              content_revision_id=f"revision-{i:08}",
    -                              media_asset_id="target" if i < matches else "other", created_at=now)
    -                         for i in indexes
    -                     ])
75  +                     await session.execute(
76  +                         insert(ContentRevisionRow),
77  +                         [
78  +                             dict(
79  +                                 id=f"revision-{i:08}",
80  +                                 tenant_id=TENANT,
81  +                                 content_id="content",
82  +                                 revision_no=i + 1,
83  +                                 payload={"mediaAssetIds": ["target" if i < matches else "other"]},
84  +                                 payload_sha256="c" * 64,
85  +                                 created_by=USER,
86  +                                 created_at=now,
87  +                             )
88  +                             for i in indexes
89  +                         ],
90  +                     )
91  +                     await session.execute(
92  +                         insert(ContentRevisionMediaRow),
93  +                         [
94  +                             dict(
95  +                                 id=f"reference-{i:08}",
96  +                                 tenant_id=TENANT,
97  +                                 content_id="content",
98  +                                 content_revision_id=f"revision-{i:08}",
99  +                                 media_asset_id="target" if i < matches else "other",
100 +                                 created_at=now,
101 +                             )
102 +                             for i in indexes
103 +                         ],
104 +                     )
105 |             async with database.engine.connect() as connection:
106 |                 await connection.execute(text("ANALYZE"))
    -                 plan = [list(row) for row in await connection.execute(text(
    -                     "EXPLAIN QUERY PLAN SELECT * FROM content_revision_media "
    -                     "WHERE tenant_id = :tenant AND media_asset_id = :asset"
    -                 ), {"tenant": TENANT, "asset": "target"})]
107 +                 plan = [
108 +                     list(row)
109 +                     for row in await connection.execute(
110 +                         text(
111 +                             "EXPLAIN QUERY PLAN SELECT * FROM content_revision_media "
112 +                             "WHERE tenant_id = :tenant AND media_asset_id = :asset"
113 +                         ),
114 +                         {"tenant": TENANT, "asset": "target"},
115 +                     )
116 +                 ]
117 |                 version = await connection.scalar(text("SELECT sqlite_version()"))
    -             headers = {"X-Tenant-Id": TENANT, "X-User-Id": USER, "X-Roles": "viewer", "X-MFA": "false"}
118 +             headers = {
119 +                 "X-Tenant-Id": TENANT,
120 +                 "X-User-Id": USER,
121 +                 "X-Roles": "viewer",
122 +                 "X-MFA": "false",
123 +             }
124 |             timings = []
125 |             async with httpx.AsyncClient(
    -                 transport=httpx.ASGITransport(app=app), base_url="http://benchmark", trust_env=False,
126 +                 transport=httpx.ASGITransport(app=app),
127 +                 base_url="http://benchmark",
128 +                 trust_env=False,
129 |             ) as client:
130 |                 for iteration in range(35):
131 |                     start = perf_counter()
    -                     response = await client.get("/api/v1/media/assets/target/references", headers=headers)
132 +                     response = await client.get(
133 +                         "/api/v1/media/assets/target/references", headers=headers
134 +                     )
135 |                     elapsed = (perf_counter() - start) * 1000
--------------------------------------------------------------------------------
139 |                         timings.append(elapsed)
    -             return dict(rows=size, matches=matches, samples=len(timings), warmup=5,
    -                         p50_ms=round(statistics.median(timings), 3),
    -                         p95_ms=round(sorted(timings)[math.ceil(len(timings) * .95) - 1], 3),
    -                         max_ms=round(max(timings), 3), sqlite_version=version,
    -                         query_plan=plan)
140 +             return dict(
141 +                 rows=size,
142 +                 matches=matches,
143 +                 samples=len(timings),
144 +                 warmup=5,
145 +                 p50_ms=round(statistics.median(timings), 3),
146 +                 p95_ms=round(sorted(timings)[math.ceil(len(timings) * 0.95) - 1], 3),
147 +                 max_ms=round(max(timings), 3),
148 +                 sqlite_version=version,
149 +                 query_plan=plan,
150 +             )
151 |
152 |
153 | async def main() -> None:
    -     result = dict(measured_at=datetime.now(UTC).isoformat(), python=platform.python_version(),
    -                   system=platform.platform(), database="temporary file-backed SQLite",
    -                   concurrency=1, transport="in-process ASGI", cases=[])
154 +     result = dict(
155 +         measured_at=datetime.now(UTC).isoformat(),
156 +         python=platform.python_version(),
157 +         system=platform.platform(),
158 +         database="temporary file-backed SQLite",
159 +         concurrency=1,
160 +         transport="in-process ASGI",
161 +         cases=[],
162 +     )
163 |     for size, matches in ((1000, 10), (10000, 10), (1000, 1000)):
    |

unformatted: File would be reformatted
   --> scripts/debug_device_rpc_smoke.py:110:28
    |
109 |             await websocket.send(
    -                 json.dumps(
    -                     {"type": "debug.auth", "sessionId": session_id, "token": relay_token}
    -                 )
110 +                 json.dumps({"type": "debug.auth", "sessionId": session_id, "token": relay_token})
111 |             )
--------------------------------------------------------------------------------
115 |
    -             await websocket.send(
    -                 json.dumps({"type": "view.layout", "sessionId": session_id})
    -             )
116 +             await websocket.send(json.dumps({"type": "view.layout", "sessionId": session_id}))
117 |             layout_accepted = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
--------------------------------------------------------------------------------
125 |
    -             await websocket.send(
    -                 json.dumps({"type": "view.frame", "sessionId": session_id})
    -             )
126 +             await websocket.send(json.dumps({"type": "view.frame", "sessionId": session_id}))
127 |             frame_accepted = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
    |

unformatted: File would be reformatted
  --> scripts/debug_rpc_smoke.py:69:28
   |
68 |             await websocket.send(
   -                 json.dumps(
   -                     {"type": "debug.auth", "sessionId": session_id, "token": relay_token}
   -                 )
69 +                 json.dumps({"type": "debug.auth", "sessionId": session_id, "token": relay_token})
70 |             )
   |

unformatted: File would be reformatted
   --> scripts/validate-demo-sources.py:19:1
    |
18  |     print("验证 source-profile.json...")
    -     
19  +
20  |     if not PROFILE.exists():
21  |         raise FileNotFoundError(f"Profile not found: {PROFILE}")
    -     
22  +
23  |     with open(PROFILE, encoding="utf-8") as f:
24  |         profile = json.load(f)
    -     
25  +
26  |     # 必填字段
27  |     assert "version" in profile, "Missing version"
28  |     assert "sources" in profile, "Missing sources"
29  |     assert len(profile["sources"]) >= 2, "Expected at least 2 sources"
    -     
30  +
31  |     # 验证来源定义
--------------------------------------------------------------------------------
37  |         assert "fields" in source, "Missing source.fields"
    -     
38  +
39  |     print("  ✓ Profile structure valid")
--------------------------------------------------------------------------------
45  |     print("\n验证商品数据...")
    -     
46  +
47  |     products_csv = DEMO_DATA / "products.csv"
48  |     if not products_csv.exists():
49  |         raise FileNotFoundError(f"Products CSV not found: {products_csv}")
    -     
50  +
51  |     with open(products_csv, encoding="utf-8") as f:
52  |         reader = csv.DictReader(f)
53  |         rows = list(reader)
    -     
54  +
55  |     assert len(rows) >= 10, f"Expected >= 10 products, got {len(rows)}"
    -     
56  +
57  |     product_ids = set()
58  |     issues = []
    -     
59  +
60  |     for idx, row in enumerate(rows, 1):
--------------------------------------------------------------------------------
67  |             product_ids.add(row["product_id"])
    -         
68  +
69  |         if not row.get("title"):
70  |             issues.append(f"Row {idx}: Missing title")
71  |         elif len(row["title"]) > 60:
72  |             issues.append(f"Row {idx}: Title too long ({len(row['title'])} > 60)")
    -         
73  +
74  |         if not row.get("description"):
75  |             issues.append(f"Row {idx}: Missing description")
76  |         elif len(row["description"]) > 3000:
77  |             issues.append(f"Row {idx}: Description too long")
    -         
78  +
79  |         # 价格验证
--------------------------------------------------------------------------------
88  |                 issues.append(f"Row {idx}: Invalid price format: {row['price']}")
    -         
89  +
90  |         # 时间戳验证
--------------------------------------------------------------------------------
97  |                 issues.append(f"Row {idx}: Invalid timestamp: {row['updated_at']}")
    -     
98  +
99  |     if issues:
100 |         for issue in issues:
101 |             print(f"  ✗ {issue}")
102 |         raise ValueError(f"Found {len(issues)} validation errors in products")
    -     
103 +
104 |     print(f"  ✓ {len(rows)} products validated")
    -     print(f"  ✓ Price range: {min(Decimal(r['price']) for r in rows)} - {max(Decimal(r['price']) for r in rows)} CNY")
    -     
105 +     print(
106 +         f"  ✓ Price range: {min(Decimal(r['price']) for r in rows)} - {max(Decimal(r['price']) for r in rows)} CNY"
107 +     )
108 +
109 |     return rows
--------------------------------------------------------------------------------
114 |     print("\n验证素材清单...")
    -     
115 +
116 |     media_csv = DEMO_DATA / "media-manifest.csv"
117 |     if not media_csv.exists():
118 |         raise FileNotFoundError(f"Media manifest not found: {media_csv}")
    -     
119 +
120 |     with open(media_csv, encoding="utf-8") as f:
121 |         reader = csv.DictReader(f)
122 |         rows = list(reader)
    -     
123 +
124 |     assert len(rows) >= 20, f"Expected >= 20 media files, got {len(rows)}"
    -     
125 +
126 |     file_names = set()
127 |     sha256_hashes = set()
128 |     issues = []
129 |     total_size = 0
    -     
130 +
131 |     for idx, row in enumerate(rows, 1):
--------------------------------------------------------------------------------
138 |             file_names.add(row["file_name"])
    -         
139 +
140 |         if not row.get("sha256"):
--------------------------------------------------------------------------------
145 |             sha256_hashes.add(row["sha256"])
    -         
146 +
147 |         if not row.get("content_type"):
148 |             issues.append(f"Row {idx}: Missing content_type")
149 |         elif row["content_type"] not in ["image/jpeg", "image/png", "video/mp4"]:
150 |             issues.append(f"Row {idx}: Unsupported content_type: {row['content_type']}")
    -         
151 +
152 |         # 大小验证
--------------------------------------------------------------------------------
163 |                 issues.append(f"Row {idx}: Invalid size_bytes: {row['size_bytes']}")
    -         
164 +
165 |         # 尺寸验证（可选）
--------------------------------------------------------------------------------
172 |                 issues.append(f"Row {idx}: Invalid width format: {row['width']}")
    -         
173 +
174 |         if row.get("height"):
--------------------------------------------------------------------------------
180 |                 issues.append(f"Row {idx}: Invalid height format: {row['height']}")
    -     
181 +
182 |     if issues:
183 |         for issue in issues:
184 |             print(f"  ✗ {issue}")
185 |         raise ValueError(f"Found {len(issues)} validation errors in media")
    -     
186 +
187 |     print(f"  ✓ {len(rows)} media files validated")
188 |     print(f"  ✓ Total size: {total_size:,} bytes (~{total_size / (1024 * 1024):.1f} MB)")
189 |     print(f"  ✓ Unique SHA256 hashes: {len(sha256_hashes)}")
    -     
190 +
191 |     return rows
--------------------------------------------------------------------------------
196 |     print("\n验证关联关系...")
    -     
197 +
198 |     media_ids = {row["file_name"] for row in media}
199 |     issues = []
    -     
200 +
201 |     total_refs = 0
202 |     products_with_media = 0
    -     
203 +
204 |     for product in products:
205 |         media_refs = product.get("media_refs", "").strip()
206 |         if not media_refs:
207 |             continue
    -         
208 +
209 |         products_with_media += 1
210 |         refs = [ref.strip() for ref in media_refs.replace(";", ",").split(",") if ref.strip()]
211 |         total_refs += len(refs)
    -         
212 +
213 |         for ref in refs:
214 |             if ref not in media_ids:
215 |                 issues.append(f"Product {product['product_id']}: Referenced media {ref} not found")
    -     
216 +
217 |     if issues:
218 |         for issue in issues:
219 |             print(f"  ✗ {issue}")
220 |         raise ValueError(f"Found {len(issues)} relationship errors")
    -     
221 +
222 |     print(f"  ✓ {products_with_media}/{len(products)} products have media")
--------------------------------------------------------------------------------
228 |     print("=== V1-03 示范数据验证 ===\n")
    -     
229 +
230 |     try:
--------------------------------------------------------------------------------
234 |         validate_relationships(products, media)
    -         
235 +
236 |         print("\n" + "=" * 50)
237 |         print("✓ 所有验证通过")
238 |         print("=" * 50)
    -         
239 +
240 |         # 输出摘要
--------------------------------------------------------------------------------
245 |         print(f"  - 认证方式: {profile['security']['credentials_storage']}")
    -         
246 +
247 |     except Exception as e:
248 |         print(f"\n✗ 验证失败: {e}")
249 |         return 1
    -     
250 +
251 |     return 0
    |

unformatted: File would be reformatted
   --> services/control-api/src/cloudctl_api/schemas.py:166:35
    |
165 |     group_id: str | None = Field(default=None, alias="groupId")
    -     min_price: str | None = Field(default=None, alias="minPrice", pattern=r"^[0-9]+(\.[0-9]{1,2})?$")
    -     max_price: str | None = Field(default=None, alias="maxPrice", pattern=r"^[0-9]+(\.[0-9]{1,2})?$")
166 +     min_price: str | None = Field(
167 +         default=None, alias="minPrice", pattern=r"^[0-9]+(\.[0-9]{1,2})?$"
168 +     )
169 +     max_price: str | None = Field(
170 +         default=None, alias="maxPrice", pattern=r"^[0-9]+(\.[0-9]{1,2})?$"
171 +     )
172 |     status: Literal["ACTIVE", "ARCHIVED", "ALL"] | None = Field(default="ACTIVE")
    |

unformatted: File would be reformatted
    --> services/control-api/src/cloudctl_api/services.py:1264:1
     |
1263 |                 raise ValidationError("one or more products do not exist or are archived")
     -             
1264 +
1265 |             for product in products:
--------------------------------------------------------------------------------
1273 |                 )
     -             
1274 +
1275 |             return {"updated_count": len(products), "product_ids": request.product_ids}
--------------------------------------------------------------------------------
1282 |             repository = ControlRepository(session, actor)
     -             
1283 +
1284 |             # Verify group exists
1285 |             group = await session.get(ContentGroupRow, request.group_id)
1286 |             if group is None or group.tenant_id != repository.tenant_id:
1287 |                 raise ValidationError("content group does not exist in tenant")
     -             
1288 +
1289 |             products = list(
--------------------------------------------------------------------------------
1299 |                 raise ValidationError("one or more products do not exist or are archived")
     -             
1300 +
1301 |             # Remove existing group memberships
--------------------------------------------------------------------------------
1307 |             )
     -             
1308 +
1309 |             # Add new group memberships
--------------------------------------------------------------------------------
1319 |                 )
     -             
1320 +
1321 |             return {"updated_count": len(products), "group_id": request.group_id}
--------------------------------------------------------------------------------
1339 |                 raise ValidationError("one or more products do not exist or are already archived")
     -             
1340 +
1341 |             for product in products:
--------------------------------------------------------------------------------
1349 |                 )
     -             
1350 +
1351 |             return {"archived_count": len(products), "product_ids": request.product_ids}
1352 |
     -     async def import_products(
     -         self, actor: Actor, request: ProductImportRequest
     -     ) -> dict[str, Any]:
1353 +     async def import_products(self, actor: Actor, request: ProductImportRequest) -> dict[str, Any]:
1354 |         require_permissions(actor.roles, Permission.CONTENT_WRITE)
1355 |         async with self.database.unit_of_work() as session:
1356 |             repository = ControlRepository(session, actor)
     -             
1357 +
1358 |             if request.group_id:
1359 |                 group = await session.get(ContentGroupRow, request.group_id)
1360 |                 if group is None or group.tenant_id != repository.tenant_id:
1361 |                     raise ValidationError("content group does not exist in tenant")
     -             
1362 +
1363 |             imported_ids = []
1364 |             skipped_count = 0
     -             
1365 +
1366 |             for item in request.items:
--------------------------------------------------------------------------------
1373 |                 )
     -                 
1374 +
1375 |                 if existing:
1376 |                     skipped_count += 1
1377 |                     continue
     -                 
1378 +
1379 |                 product_id = repository.new_id()
--------------------------------------------------------------------------------
1394 |                 repository.add(product)
     -                 
1395 +
1396 |                 # Add to group if specified
--------------------------------------------------------------------------------
1407 |                     )
     -                 
1408 +
1409 |                 repository.audit(
--------------------------------------------------------------------------------
1414 |                 )
     -                 
1415 +
1416 |                 imported_ids.append(product_id)
     -             
1417 +
1418 |             return {
--------------------------------------------------------------------------------
1429 |             repository = ControlRepository(session, actor)
     -             
1430 +
1431 |             query = select(ProductRow).where(ProductRow.tenant_id == repository.tenant_id)
     -             
1432 +
1433 |             if request.status and request.status != "ALL":
1434 |                 query = query.where(ProductRow.status == request.status)
     -             
1435 +
1436 |             if request.search:
--------------------------------------------------------------------------------
1442 |                 )
     -             
1443 +
1444 |             if request.category:
1445 |                 query = query.where(ProductRow.category == request.category)
     -             
1446 +
1447 |             if request.min_price:
1448 |                 query = query.where(ProductRow.price >= request.min_price)
     -             
1449 +
1450 |             if request.max_price:
1451 |                 query = query.where(ProductRow.price <= request.max_price)
     -             
1452 +
1453 |             if request.group_id:
--------------------------------------------------------------------------------
1459 |                 )
     -             
1460 +
1461 |             products = list(await session.scalars(query.order_by(ProductRow.created_at.desc())))
     -             
1462 +
1463 |             result = []
--------------------------------------------------------------------------------
1476 |                 result.append(self._product_view(product, asset_ids, media))
     -             
1477 +
1478 |             return result
     |

unformatted: File would be reformatted
   --> services/control-api/src/cloudctl_api/source_routes.py:52:1
    |
51  |     from uuid import uuid4
    -     
52  +
53  |     async with database.session_factory() as session:
--------------------------------------------------------------------------------
60  |         existing = result.scalar_one_or_none()
    -         
61  +
62  |         if existing:
63  |             raise HTTPException(status_code=409, detail="Connection name already exists")
    -         
64  +
65  |         # Create connection
--------------------------------------------------------------------------------
80  |         await session.commit()
    -         
81  +
82  |         return SourceConnectionResponse(
--------------------------------------------------------------------------------
105 |     async with database.session_factory() as session:
    -         stmt = select(SourceConnectionRow).where(
    -             SourceConnectionRow.tenant_id == str(actor.tenant_id)
    -         ).order_by(SourceConnectionRow.created_at.desc())
    -         
106 +         stmt = (
107 +             select(SourceConnectionRow)
108 +             .where(SourceConnectionRow.tenant_id == str(actor.tenant_id))
109 +             .order_by(SourceConnectionRow.created_at.desc())
110 +         )
111 +
112 |         result = await session.execute(stmt)
113 |         connections = result.scalars().all()
    -         
114 +
115 |         return [
--------------------------------------------------------------------------------
142 |     from datetime import UTC, datetime
    -     
143 +
144 |     async with database.session_factory() as session:
--------------------------------------------------------------------------------
151 |         connection = result.scalar_one_or_none()
    -         
152 +
153 |         if not connection:
154 |             raise HTTPException(status_code=404, detail="Connection not found")
    -         
155 +
156 |         # Preview
--------------------------------------------------------------------------------
162 |         )
    -         
163 +
164 |         # Update test result
--------------------------------------------------------------------------------
173 |             connection.last_test_result = f"Partial: {valid}/{total} valid"
    -         
174 +
175 |         await session.commit()
    -         
176 +
177 |         return preview
--------------------------------------------------------------------------------
196 |         connection = result.scalar_one_or_none()
    -         
197 +
198 |         if not connection:
199 |             raise HTTPException(status_code=404, detail="Connection not found")
    -         
200 +
201 |         # Create connector
--------------------------------------------------------------------------------
206 |         )
    -         
207 +
208 |         # Execute sync
--------------------------------------------------------------------------------
218 |         )
    -         
219 +
220 |         await session.commit()
    -         
221 +
222 |         # Get the created sync run
223 |         stmt = select(SyncRunRow).where(SyncRunRow.id == sync_result["sync_run_id"])
224 |         result = await session.execute(stmt)
225 |         sync_run = result.scalar_one()
    -         
226 +
227 |         return SyncRunResponse(
--------------------------------------------------------------------------------
260 |             raise HTTPException(status_code=404, detail="Connection not found")
    -         
261 +
262 |         # Get runs
    -         stmt = select(SyncRunRow).where(
    -             SyncRunRow.connection_id == connection_id,
    -             SyncRunRow.tenant_id == str(actor.tenant_id),
    -         ).order_by(SyncRunRow.started_at.desc()).limit(20)
    -         
263 +         stmt = (
264 +             select(SyncRunRow)
265 +             .where(
266 +                 SyncRunRow.connection_id == connection_id,
267 +                 SyncRunRow.tenant_id == str(actor.tenant_id),
268 +             )
269 +             .order_by(SyncRunRow.started_at.desc())
270 +             .limit(20)
271 +         )
272 +
273 |         result = await session.execute(stmt)
274 |         runs = result.scalars().all()
    -         
275 +
276 |         return [
--------------------------------------------------------------------------------
313 |             raise HTTPException(status_code=404, detail="Connection not found")
    -         
314 +
315 |         # Get errors
--------------------------------------------------------------------------------
319 |         )
    -         
320 +
321 |         if resolved is False:
322 |             stmt = stmt.where(SyncErrorRow.resolved_at.is_(None))
323 |         elif resolved is True:
324 |             stmt = stmt.where(SyncErrorRow.resolved_at.isnot(None))
    -         
325 +
326 |         stmt = stmt.order_by(SyncErrorRow.created_at.desc()).limit(100)
    -         
327 +
328 |         result = await session.execute(stmt)
329 |         errors = result.scalars().all()
    -         
330 +
331 |         return [
    |

unformatted: File would be reformatted
   --> services/control-api/src/cloudctl_api/source_service.py:349:1
    |
348 |     Execute a synchronization run.
    -     
349 +
350 |     Returns summary dict with counts and status.
351 |     """
352 |     from datetime import UTC, datetime
353 |     from uuid import uuid4
    -     
354 +
355 |     from sqlalchemy import select
    -     
356 +
357 |     from .db import (
--------------------------------------------------------------------------------
361 |     )
    -     
362 +
363 |     # Create sync run record
364 |     sync_run_id = str(uuid4())
365 |     now = datetime.now(UTC)
    -     
366 +
367 |     # Get cursor from last successful run
--------------------------------------------------------------------------------
380 |     cursor_before = last_run.cursor_after if last_run and run_mode == "incremental" else None
    -     
381 +
382 |     sync_run = SyncRunRow(
--------------------------------------------------------------------------------
399 |     await session.flush()
    -     
400 +
401 |     # Get connection config
--------------------------------------------------------------------------------
405 |     entity_kind = connection.entity_kind
    -     
406 +
407 |     # Sync pages
--------------------------------------------------------------------------------
412 |     total_failed = 0
    -     
413 +
414 |     try:
--------------------------------------------------------------------------------
419 |             )
    -             
420 +
421 |             if not raw_records:
422 |                 break
    -             
423 +
424 |             # Process each record
425 |             for raw in raw_records:
426 |                 total_read += 1
427 |                 external_id = connector.get_external_id(raw)
    -                 
428 +
429 |                 try:
430 |                     # Normalize
431 |                     normalized, errors = connector.normalize_record(raw)
    -                     
432 +
433 |                     if errors:
--------------------------------------------------------------------------------
445 |                         continue
    -                     
446 +
447 |                     # Compute record hash
448 |                     import hashlib
449 |                     import json
    -                     
450 +
451 |                     record_json = json.dumps(normalized, sort_keys=True)
452 |                     record_hash = hashlib.sha256(record_json.encode()).hexdigest()
    -                     
453 +
454 |                     # Check existing link
--------------------------------------------------------------------------------
461 |                     existing_link = link_result.scalar_one_or_none()
    -                     
462 +
463 |                     if existing_link and existing_link.record_hash == record_hash:
464 |                         # Same hash, skip
465 |                         continue
    -                     
466 +
467 |                     # Create or update entity
--------------------------------------------------------------------------------
485 |                         raise ValueError(f"Unknown entity_kind: {entity_kind}")
    -                     
486 +
487 |                     # Update or create link
--------------------------------------------------------------------------------
504 |                         session.add(link)
    -                     
505 +
506 |                 except Exception as e:
--------------------------------------------------------------------------------
517 |                     total_failed += 1
    -             
518 +
519 |             # Commit page
--------------------------------------------------------------------------------
525 |             await session.flush()
    -             
526 +
527 |             # Move to next page
528 |             current_cursor = next_cursor
529 |             if not next_cursor:
530 |                 break
    -         
531 +
532 |         # Mark completed
533 |         sync_run.status = "completed"
534 |         sync_run.completed_at = datetime.now(UTC)
535 |         await session.flush()
    -         
536 +
537 |         return {
--------------------------------------------------------------------------------
544 |         }
    -         
545 +
546 |     except Exception as e:
--------------------------------------------------------------------------------
565 |     from uuid import uuid4
    -     
566 +
567 |     from .db import SyncErrorRow
    -     
568 +
569 |     for error_msg in errors:
--------------------------------------------------------------------------------
596 |     from uuid import uuid4
    -     
597 +
598 |     from sqlalchemy import select
    -     
599 +
600 |     from .db import MediaAssetRow, ProductMediaRow, ProductRow
    -     
601 +
602 |     if existing_link and existing_link.entity_id:
--------------------------------------------------------------------------------
606 |         product = result.scalar_one()
    -         
607 +
608 |         product.title = normalized["title"]
--------------------------------------------------------------------------------
613 |         product.revision += 1
    -         
614 +
615 |         entity_id = product.id
--------------------------------------------------------------------------------
633 |         session.add(product)
    -     
634 +
635 |     # Handle media references
--------------------------------------------------------------------------------
639 |         from sqlalchemy import delete
    -         
640 +
641 |         del_stmt = delete(ProductMediaRow).where(ProductMediaRow.product_id == entity_id)
642 |         await session.execute(del_stmt)
    -         
643 +
644 |         # Add new media associations
--------------------------------------------------------------------------------
652 |             all_media = media_result.scalars().all()
    -             
653 +
654 |             # Filter by file_name in metadata
--------------------------------------------------------------------------------
659 |                     break
    -             
660 +
661 |             if media_asset:
--------------------------------------------------------------------------------
671 |                 session.add(pm)
    -     
672 +
673 |     return entity_id
--------------------------------------------------------------------------------
686 |     from uuid import uuid4
    -     
687 +
688 |     from sqlalchemy import select
    -     
689 +
690 |     from .db import MediaAssetRow
    -     
691 +
692 |     sha256 = normalized["sha256"]
    -     
693 +
694 |     # Check if asset already exists by SHA256
--------------------------------------------------------------------------------
700 |     existing_asset = result.scalar_one_or_none()
    -     
701 +
702 |     if existing_asset:
--------------------------------------------------------------------------------
709 |         return existing_asset.id
    -     
710 +
711 |     # Download and verify asset
712 |     file_name = normalized["file_name"]
713 |     try:
714 |         asset_data, content_type = await connector.fetch_asset(file_name)
    -         
715 +
716 |         # Verify SHA256
717 |         import hashlib
    -         
718 +
719 |         actual_sha256 = hashlib.sha256(asset_data).hexdigest()
720 |         if actual_sha256 != sha256:
721 |             msg = f"SHA256 mismatch for {file_name}: expected {sha256}, got {actual_sha256}"
722 |             raise ValueError(msg)
    -             
723 +
724 |     except FileNotFoundError as e:
725 |         # Asset file not available, skip this media item
726 |         msg = f"Media file not found: {file_name}"
727 |         raise FileNotFoundError(msg) from e
    -     
728 +
729 |     # Store in object store
730 |     object_key = f"media/{tenant_id}/{sha256[:2]}/{sha256}"
731 |     object_store.put(object_key, asset_data, content_type)
    -     
732 +
733 |     # Create media asset
--------------------------------------------------------------------------------
749 |     session.add(asset)
    -     
750 +
751 |     return entity_id
    |

unformatted: File would be reformatted
   --> services/control-api/src/cloudctl_api/xianyu_publish.py:39:30
    |
38  |
    - def build_text_publish_steps(*, description: str, price: str, auto_publish: bool = False) -> list[dict[str, Any]]:
39  + def build_text_publish_steps(
40  +     *, description: str, price: str, auto_publish: bool = False
41  + ) -> list[dict[str, Any]]:
42  |     """Return allowlisted steps that fill the idlefish publish form.
--------------------------------------------------------------------------------
103 |     ]
    -     
104 +
105 |     if auto_publish:
106 |         # Add publish button click and confirmation
    -         steps.extend([
    -             {
    -                 "stepId": "click-publish",
    -                 "action": "ui.tap",
    -                 "locatorRef": "xianyu_publish_button",
    -                 "timeoutMs": 5_000,
    -             },
    -             {
    -                 "stepId": "wait-publish-complete",
    -                 "action": "ui.wait",
    -                 "locatorRef": "xianyu_home_sell",
    -                 "condition": "EXISTS",
    -                 "pollMs": 500,
    -                 "timeoutMs": 15_000,
    -             },
    -             {
    -                 "stepId": "capture-success",
    -                 "action": "ui.screenshot",
    -                 "label": "xianyu_publish_success",
    -                 "timeoutMs": 5_000,
    -             },
107 +         steps.extend(
108 +             [
109 +                 {
110 +                     "stepId": "click-publish",
111 +                     "action": "ui.tap",
112 +                     "locatorRef": "xianyu_publish_button",
113 +                     "timeoutMs": 5_000,
114 +                 },
115 +                 {
116 +                     "stepId": "wait-publish-complete",
117 +                     "action": "ui.wait",
118 +                     "locatorRef": "xianyu_home_sell",
119 +                     "condition": "EXISTS",
120 +                     "pollMs": 500,
121 +                     "timeoutMs": 15_000,
122 +                 },
123 +                 {
124 +                     "stepId": "capture-success",
125 +                     "action": "ui.screenshot",
126 +                     "label": "xianyu_publish_success",
127 +                     "timeoutMs": 5_000,
128 +                 },
129 +                 {
130 +                     "stepId": "mark-published",
131 +                     "action": "run.log",
132 +                     "level": "INFO",
133 +                     "messageCode": "XIANYU_PUBLISH_SUCCESS",
134 +                     "timeoutMs": 1_000,
135 +                 },
136 +             ]
137 +         )
138 +     else:
139 +         steps.append(
140 |             {
    -                 "stepId": "mark-published",
141 +                 "stepId": "mark-ready",
142 |                 "action": "run.log",
143 |                 "level": "INFO",
    -                 "messageCode": "XIANYU_PUBLISH_SUCCESS",
144 +                 "messageCode": "XIANYU_PUBLISH_FORM_READY",
145 |                 "timeoutMs": 1_000,
    -             },
    -         ])
    -     else:
    -         steps.append({
    -             "stepId": "mark-ready",
    -             "action": "run.log",
    -             "level": "INFO",
    -             "messageCode": "XIANYU_PUBLISH_FORM_READY",
    -             "timeoutMs": 1_000,
    -         })
    -     
146 +             }
147 +         )
148 |
--------------------------------------------------------------------------------
185 |     """Build a complete Xianyu publish task.
    -     
186 +
187 |     Args:
--------------------------------------------------------------------------------
204 |             raise ValueError("delivery_id is required when media assets are supplied")
    -     
    -     steps = build_text_publish_steps(description=description, price=price, auto_publish=auto_publish)
    -     
205 +
206 +     steps = build_text_publish_steps(
207 +         description=description, price=price, auto_publish=auto_publish
208 +     )
209 +
210 |     # Insert media upload steps after opening publish page (before filling description)
--------------------------------------------------------------------------------
238 |         steps[4:4] = media_steps
    -     
239 +
240 |     total = sum(int(step["timeoutMs"]) for step in steps)
241 |     if total > 900_000:
242 |         raise ValueError("publish step timeouts exceed the task budget")
    -     
243 +
244 |     task = {
    |

unformatted: File would be reformatted
  --> tests/integration/conftest.py:16:1
   |
15 |     db = Database(settings)
   -     
16 +
17 |     # Create schema
18 |     await db.create_schema()
   -     
19 +
20 |     async with db.session_factory() as session:
21 |         yield session
22 |         await session.rollback()
   -     
23 +
24 |     await db.dispose()
   |

unformatted: File would be reformatted
   --> tests/integration/test_source_sync.py:25:1
    |
24  |         from datetime import UTC, datetime
    -         
25  +
26  |         # Create connection
--------------------------------------------------------------------------------
70  |         # Check errors if any
    -         if result['records_failed'] > 0:
71  +         if result["records_failed"] > 0:
72  |             error_stmt = select(SyncErrorRow).where(
--------------------------------------------------------------------------------
90  |         sync_run = sync_result.scalar_one()
    -         
91  +
92  |         assert sync_run.status == "completed"
--------------------------------------------------------------------------------
99  |         products = prod_result.scalars().all()
    -         
100 +
101 |         assert len(products) == 10
--------------------------------------------------------------------------------
106 |         # Verify links created
    -         link_stmt = select(SourceRecordLinkRow).where(
    -             SourceRecordLinkRow.tenant_id == tenant_id
    -         )
107 +         link_stmt = select(SourceRecordLinkRow).where(SourceRecordLinkRow.tenant_id == tenant_id)
108 |         link_result = await session.execute(link_stmt)
109 |         links = link_result.scalars().all()
    -         
110 +
111 |         assert len(links) == 10
--------------------------------------------------------------------------------
259 |         product = prod_result.scalar_one()
    -         
260 +
261 |         assert product.price == "3999.0"
262 |         assert product.revision == 2
263 |
264 |     @pytest.mark.asyncio
    -     async def test_sync_media_with_download(
    -         self, session, tenant_id: str, user_id: str
    -     ) -> None:
265 +     async def test_sync_media_with_download(self, session, tenant_id: str, user_id: str) -> None:
266 |         """Test media synchronization with asset download.
    -         
267 +
268 |         Note: Demo media files don't actually exist in artifacts/v1/V1-03/demo-data/media/,
--------------------------------------------------------------------------------
313 |         # Verify errors recorded
    -         error_stmt = select(SyncErrorRow).where(
    -             SyncErrorRow.connection_id == connection.id
    -         )
314 +         error_stmt = select(SyncErrorRow).where(SyncErrorRow.connection_id == connection.id)
315 |         error_result = await session.execute(error_stmt)
316 |         errors = error_result.scalars().all()
    -         
317 +
318 |         assert len(errors) == 20
--------------------------------------------------------------------------------
373 |         # Verify errors recorded
    -         error_stmt = select(SyncErrorRow).where(
    -             SyncErrorRow.connection_id == connection.id
    -         )
374 +         error_stmt = select(SyncErrorRow).where(SyncErrorRow.connection_id == connection.id)
375 |         error_result = await session.execute(error_stmt)
376 |         errors = error_result.scalars().all()
    -         
377 +
378 |         assert len(errors) >= 2
--------------------------------------------------------------------------------
382 |     @pytest.mark.asyncio
    -     async def test_sync_cursor_persistence(
    -         self, session, tenant_id: str, user_id: str
    -     ) -> None:
383 +     async def test_sync_cursor_persistence(self, session, tenant_id: str, user_id: str) -> None:
384 |         """Test cursor is persisted across pages."""
--------------------------------------------------------------------------------
425 |         sync_run = sync_result.scalar_one()
    -         
426 +
427 |         # Cursor should be None (end of data)
--------------------------------------------------------------------------------
435 |     from datetime import UTC, datetime
    -     
436 +
437 |     from cloudctl_api.db import TenantRow
    -     
438 +
439 |     tenant = TenantRow(
--------------------------------------------------------------------------------
452 |     from datetime import UTC, datetime
    -     
453 +
454 |     from cloudctl_api.db import UserRow
    -     
455 +
456 |     user = UserRow(
    |

16 files would be reformatted, 308 files already formatted
```
退出码: 1

#### ruff check检查
```
I001 [*] Import block is un-sorted or un-formatted
 --> artifacts/review-20260905/build-plan.py:1:1
  |
1 | / from pathlib import Path
2 | | import json
  | |___________^
3 |   ROOT=Path(__file__).resolve().parents[2]
4 |   OUT=ROOT/'docs/v1'
  |
help: Organize imports
  |
1 + import json
2 | from pathlib import Path
  - import json
3 +
4 | ROOT=Path(__file__).resolve().parents[2]
  |

E501 Line too long (337 > 100)
 --> artifacts/review-20260905/build-plan.py:7:101
  |
5 | …
6 | …
7 | …deps],estimate_low=days[0],estimate_high=days[1],status='blocked' if block else 'todo',existing=existing,files=files,steps=steps,verification_commands=checks,acceptance=accept,blocker=block,evidence=f'artifacts/v1/V1-{n:02}/',owner='待分配'))
  |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
8 | …
9 | …
  |

E501 Line too long (146 > 100)
  --> artifacts/review-20260905/build-plan.py:10:81
   |
 8 | …
 9 | …l/companion/'
10 | …,(1,2),'Python 392 / Web 40 / Studio 16 / APK 41 单测通过；静态检查与部分浏览器用例失败',
   |                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
11 | …ck-security-boundaries.sh','apps/web/playwright.config.ts','apps/web/e2e/smoke.spec.ts'],
12 | … 清单，建立不包含 lab/凭据的源码 Git 检查点。','按 Ruff/Pyright 日志定位问题；对 Outbox 构造参数、gRPC 方法真实签名逐项核对，禁止只加…
   |

E501 Line too long (507 > 100)
  --> artifacts/review-20260905/build-plan.py:12:68
   |
10 | … / APK 41 单测通过；静态检查与部分浏览器用例失败',
11 | …aywright.config.ts','apps/web/e2e/smoke.spec.ts'],
12 | … 查点。','按 Ruff/Pyright 日志定位问题；对 Outbox 构造参数、gRPC 方法真实签名逐项核对，禁止只加 type: ignore。','修复 BSD grep 扫描失败：错误必须非零退出；临时夹具覆盖违规 import、设备端口、密钥样式，夹具不含真实密钥。','Playwright 独占端口并验证页面属于 CloudCtl；产品用例只使用产品配置；核对侧栏滚动和页面文案现状后调整真实交互断言。','补完整锁定和安装说明；在干净测试环境验证，而不是删除当前工作虚拟环境。'],
   |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^…^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
13 | …nv/bin/pyright','pnpm lint','pnpm typecheck','pnpm test','pnpm build','bash scripts/check-security-boundaries.sh','pnpm --filter @cloudctl/web e2e:product'],
14 | …
   |

E501 Line too long (253 > 100)
  --> artifacts/review-20260905/build-plan.py:13:101
   |
11 | …laywright.config.ts','apps/web/e2e/smoke.spec.ts'],
12 | …检查点。','按 Ruff/Pyright 日志定位问题；对 Outbox 构造参数、gRPC 方法真实签名逐项核对，禁止只加 type: ignore。','修复 BSD grep 扫描失败：错误必须非零退出；临时夹…
13 | …env/bin/pyright','pnpm lint','pnpm typecheck','pnpm test','pnpm build','bash scripts/check-security-boundaries.sh','pnpm --filter @cloudctl/web e2e:product'],
   |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
14 | …
15 | …ME/旧规则仍描述 LAMDA 主线',
   |

E501 Line too long (123 > 100)
  --> artifacts/review-20260905/build-plan.py:15:79
   |
13 | ['.venv/bin/python -m pytest -q','.venv/bin/ruff check .','.venv/bin/ruff format --check .','.venv/bin/pyright','pnpm lint','pnpm type…
14 | '上述命令全绿；浏览器 smoke 在独占端口运行且无新增 skip；扫描器故障不能返回成功。')
15 | add(2,'冻结 APK 直连主线和 V1 业务范围','M0 基线',[],(.5,1),'ADR 0003 已接受 APK 本地执行，README/旧规则仍描述 LAMDA 主线',
   |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^
16 | ['AGENTS.md','README.md','docs/adr/0003-mobile-local-execution.md','docs/v1/02-实施方案.md'],
17 | ['逐条列出旧架构与 ADR 0003 冲突，写新的 ADR 说明适用范围及取代关系。','将设备任务定为 Companion 直连；已有 API 平台执行走服务端；两…
   |

E501 Line too long (316 > 100)
  --> artifacts/review-20260905/build-plan.py:17:67
   |
15 | …E/旧规则仍描述 LAMDA 主线',
16 | …
17 | … 直连；已有 API 平台执行走服务端；两者共享业务 Target。','保留 LAMDA/Edge 诊断边界，但生产首版不依赖 USB，不同时在手机上跑两个 Runner。','明确闲鱼商品、小红书图文、抖音视频、公众号文章均属于完整 V1；其他竞品目录冻结。'],
   |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
18 | …
19 | …
   |

E501 Line too long (112 > 100)
  --> artifacts/review-20260905/build-plan.py:20:64
   |
18 | ['rg -n "Mobile-local|Companion|LAMDA|V1" AGENTS.md README.md docs/adr'],
19 | '每种执行方式有唯一所有者、同一提交语义和明确文档入口；无相互矛盾的强制路线。')
20 | add(3,'盘点用户真实商品库和素材库','M0 基线',[],(.5,1),'本轮未找到实际来源连接器，库类型、地址、字段和授权未知',
   |                                                                                                     ^^^^^^^^^^^^
21 | ['docs/v1/source-profile.json（新增）','docs/v1/source-mapping.md（新增）'],
22 | ['由库管理员提供只读入口，填写实施方案第3节的来源类型、范围、稳定主键、附件获取方式与规模。','只读抽样10商品/20素材，脱敏记录字段名、…
   |

E501 Line too long (114 > 100)
  --> artifacts/review-20260905/build-plan.py:24:59
   |
22 | ['由库管理员提供只读入口，填写实施方案第3节的来源类型、范围、稳定主键、附件获取方式与规模。','只读抽样10商品/20素材，脱敏记录字段名、…
23 | ['读取 source-profile.json 并校验必填项；按实际来源官方文档执行只读采样（端点待盘点）'],
24 | '真实入口、主键与字段映射确认；原图/视频可读取；凭据只存 secret_ref。','需要用户现有库的只读入口、类型和字段样本')
   |                                                                                                     ^^^^^^^^^^^^^^
25 | add(4,'恢复真机验收前置条件','M0 基线',[],(.5,1),'OnePlus Android14在线；APK 0.1.0 debug；项目无障碍服务未启用',
26 | [K+'MainActivity.kt',K+'service/CompanionSyncService.kt','docs/v1/device-matrix.json（新增）'],
   |

E501 Line too long (112 > 100)
  --> artifacts/review-20260905/build-plan.py:25:80
   |
23 | ['读取 source-profile.json 并校验必填项；按实际来源官方文档执行只读采样（端点待盘点）'],
24 | '真实入口、主键与字段映射确认；原图/视频可读取；凭据只存 secret_ref。','需要用户现有库的只读入口、类型和字段样本')
25 | add(4,'恢复真机验收前置条件','M0 基线',[],(.5,1),'OnePlus Android14在线；APK 0.1.0 debug；项目无障碍服务未启用',
   |                                                                                                     ^^^^^^^^^^^^
26 | [K+'MainActivity.kt',K+'service/CompanionSyncService.kt','docs/v1/device-matrix.json（新增）'],
27 | ['记录当前手机、APK、四个App版本；核对APK所绑定API环境与本轮源码构建摘要。','在手机系统设置中由用户/授权管理员启用项目无障碍服务；确…
   |

E501 Line too long (161 > 100)
  --> artifacts/review-20260905/build-plan.py:28:101
   |
26 | …1/device-matrix.json（新增）'],
27 | … 建摘要。','在手机系统设置中由用户/授权管理员启用项目无障碍服务；确认通知、前台服务和电池状态。','用现有注册流程绑定受控测试设备，不…
28 | …bled_accessibility_services','./mobile/companion/build-external.sh testDebugUnitTest lintDebug'],
   |                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
29 | … 自动化通过。')
30 | … Product/Media/Content领域，不另建业务库',
   |

E501 Line too long (107 > 100)
  --> artifacts/review-20260905/build-plan.py:30:76
   |
28 | ['adb devices -l','adb -s b0644fb5 shell settings get secure enabled_accessibility_services','./mobile/companion/build-external.sh tes…
29 | '项目服务已启用，HTTPS绑定正确，真实健康任务有回执；不把ADB在线当自动化通过。')
30 | add(5,'来源连接器协议和字段映射','M1 来源与内容',[2,3],(1,2),'复用Product/Media/Content领域，不另建业务库',
   |                                                                                                      ^^^^^^
31 | [P+'source_schemas.py（新增）',P+'source_service.py（新增）',P+'db.py','services/control-api/migrations/versions/（新增迁移）'],
32 | ['定义 SourceConnection/SourceRecordLink/SyncRun/SyncError 的字段与租户唯一键。','新增连接测试和preview接口，预览只返回规范记录与逐行…
   |

E501 Line too long (339 > 100)
  --> artifacts/review-20260905/build-plan.py:32:82
   |
30 | … 建业务库',
31 | …grations/versions/（新增迁移）'],
32 | … preview接口，预览只返回规范记录与逐行错误，不写业务商品。','定义 read_page(cursor)、fetch_asset(ref)、normalize_record(record) 协议；只实现盘点确认的一种来源。','映射版本不可变；来源凭据经secret_ref解析，日志脱敏；分页游标只从来源响应取得。'],
   |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
33 | …venv/bin/python -m pytest -q tests/integration/test_source_connections.py'],
34 | …
   |

E501 Line too long (171 > 100)
  --> artifacts/review-20260905/build-plan.py:33:79
   |
31 | …','services/control-api/migrations/versions/（新增迁移）'],
32 | … 唯一键。','新增连接测试和preview接口，预览只返回规范记录与逐行错误，不写业务商品。','定义 read_page(cursor)、fetch_asset(ref)、norma…
33 | … 、权限失效、字段错误','.venv/bin/python -m pytest -q tests/integration/test_source_connections.py'],
   |                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
34 | …
35 | … 和SHA去重可复用',
   |

E501 Line too long (174 > 100)
  --> artifacts/review-20260905/build-plan.py:38:99
   |
36 | …box-dispatcher/src/cloudctl_outbox/'],
37 | … ','分页业务提交后推进游标；来源下载先临时文件校验再注册资产。','对过期附件地址向来源重新取一次；下载失败保留行级错误与重试入口。','…
38 | …st -q tests/integration/test_source_sync.py tests/integration/test_backend_accounts_media_content.py'],
   |                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
39 | … 一致。')
40 | … 台缺来源库连接体验',
   |

E501 Line too long (126 > 100)
  --> artifacts/review-20260905/build-plan.py:43:91
   |
41 | ['apps/web/src/views/SourceConnectionsView.vue（新增）','apps/web/src/router.ts','packages/api-contracts/typescript/src/'],
42 | ['从OpenAPI生成来源接口类型；表单只显示脱敏连接和字段映射。','新增测试连接、预览10条、确认同步、最后同步时间与错误列表。','点击行级错…
43 | ['python scripts/export_openapi.py（使用项目虚拟环境）','pnpm contracts','pnpm typecheck','pnpm --filter @cloudctl/web test'],
   |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^
44 | '非技术用户能确认来源、预览映射、启动同步并找到错误记录；页面刷新不丢任务。')
45 | add(8,'完善媒体就绪状态和大文件处理','M1 来源与内容',[2],(1,2),'MediaAsset/Upload/Derivative/Tag/Group已存在',
   |

E501 Line too long (110 > 100)
  --> artifacts/review-20260905/build-plan.py:45:82
   |
43 | ['python scripts/export_openapi.py（使用项目虚拟环境）','pnpm contracts','pnpm typecheck','pnpm --filter @cloudctl/web test'],
44 | '非技术用户能确认来源、预览映射、启动同步并找到错误记录；页面刷新不丢任务。')
45 | add(8,'完善媒体就绪状态和大文件处理','M1 来源与内容',[2],(1,2),'MediaAsset/Upload/Derivative/Tag/Group已存在',
   |                                                                                                     ^^^^^^^^^^
46 | [P+'media_store.py',P+'services.py',P+'schemas.py','tests/integration/test_backend_accounts_media_content.py'],
47 | ['检查上传完成校验：真实字节、大小、MIME、hash和租户引用必须一致。','定义 PROCESSING/READY/FAILED；查明现有衍生物是否有执行工人，没有…
   |

E501 Line too long (307 > 100)
  --> artifacts/review-20260905/build-plan.py:47:70
   |
45 | …/Group已存在',
46 | …a_content.py'],
47 | …D；查明现有衍生物是否有执行工人，没有则补缩略图/视频元数据活动。','大视频采用流式传输和长度上限；使用100MB测试文件验证峰值内存，不以测试大小代替平台限制。','失败临时文件清理；被计划/商品引用的资产不物理删除。'],
   |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
48 | …00MB流式上传下载基准并记录峰值内存、耗时'],
49 | …
   |

E501 Line too long (139 > 100)
  --> artifacts/review-20260905/build-plan.py:48:99
   |
46 | …ests/integration/test_backend_accounts_media_content.py'],
47 | … 用必须一致。','定义 PROCESSING/READY/FAILED；查明现有衍生物是否有执行工人，没有则补缩略图/视频元数据活动。','大视频采用流式传输和长…
48 | …t_backend_accounts_media_content.py','运行100MB流式上传下载基准并记录峰值内存、耗时'],
   |                                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
49 | …sh错误被拒绝。')
50 | …(1,2),'目前编辑表单仍需要输入mediaAssetIds',
   |

E501 Line too long (233 > 100)
  --> artifacts/review-20260905/build-plan.py:52:59
   |
50 | …,
51 | …ages/api-contracts/typescript/src/'],
52 | … ID；封面单独标识。','显示引用数量，归档时告知具体商品/计划；失败媒体不可选。','沿用现有媒体接口与TanStack Query，不另建本地媒体真相。'],
   |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
53 | …'],
54 | …
   |

E501 Line too long (122 > 100)
  --> artifacts/review-20260905/build-plan.py:55:72
   |
53 | ['pnpm typecheck','新增组件测试：分页、顺序、封面、未就绪禁用','pnpm --filter @cloudctl/web test'],
54 | '用户能选图/视频、排序、设封面且保存后重开一致。')
55 | add(10,'商品原子保存、不可变修订与资源类型纠正','M1 来源与内容',[1,8],(1.5,3),'Product已存在，Web保存后仍调旧Content下发',
   |                                                                                                      ^^^^^^^^^^^^^^^^^^^^^
56 | [P+'db.py',P+'services.py',P+'schemas.py','apps/web/src/views/OperationsView.vue','tests/integration/test_backend_accounts_media_conte…
57 | ['先增加失败回归：保存新Product再发往旧Content路径，明确类型不匹配；不使用预制共享ID掩盖。','复用Product行，加不可变ProductRevision并…
   |

E501 Line too long (150 > 100)
  --> artifacts/review-20260905/build-plan.py:58:101
   |
56 | …ws/OperationsView.vue','tests/integration/test_backend_accounts_media_content.py'],
57 | … 不匹配；不使用预制共享ID掩盖。','复用Product行，加不可变ProductRevision并回填当前版本；历史未知版本不可伪造。','商品字段和媒体顺序…
58 | …end_accounts_media_content.py','pnpm --filter @cloudctl/web e2e:product','pnpm typecheck'],
   |                                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
59 | …ent查询；旧发布快照可读。')
60 | … ContentRevision和媒体关联',
   |

E501 Line too long (104 > 100)
  --> artifacts/review-20260905/build-plan.py:63:101
   |
61 | [P+'content_payload.py',P+'schemas.py','apps/web/src/views/OperationsView.vue','tests/unit/test_content_payload.py'],
62 | ['复用ContentRevision，定义图文、单视频、公众号文章三类结构。','每平台保存title/body/media/cover/hashtags覆盖；不改共享原始素材。','…
63 | ['.venv/bin/python -m pytest -q tests/unit/test_content_payload.py','pnpm --filter @cloudctl/web test'],
   |                                                                                                     ^^^^
64 | '同一内容可形成三种合法平台预览；编辑覆盖不会污染其他平台或旧修订。')
65 | add(12,'账号能力、身份核对与设备绑定','M2 发布核心',[2,4],(1.5,3),'已有账号记录与设备绑定，不等同真实平台授权',
   |

E501 Line too long (111 > 100)
  --> artifacts/review-20260905/build-plan.py:65:67
   |
63 | ['.venv/bin/python -m pytest -q tests/unit/test_content_payload.py','pnpm --filter @cloudctl/web test'],
64 | '同一内容可形成三种合法平台预览；编辑覆盖不会污染其他平台或旧修订。')
65 | add(12,'账号能力、身份核对与设备绑定','M2 发布核心',[2,4],(1.5,3),'已有账号记录与设备绑定，不等同真实平台授权',
   |                                                                                                      ^^^^^^^^^^
66 | [P+'db.py',P+'services.py',P+'mobile_service.py',K+'automation/TargetLocatorRegistry.kt'],
67 | ['读取现有account/binding实体，扩展channel/scope/status/verifiedAt/identityFingerprint，不复制账号表。','区分ANDROID登录指纹与API OAut…
   |

E501 Line too long (309 > 100)
  --> artifacts/review-20260905/build-plan.py:67:85
   |
65 | … 真实平台授权',
66 | …
67 | … 号表。','区分ANDROID登录指纹与API OAuth scope；未支持/过期/撤销分别返回稳定码。','提交前核对当前账号指纹及绑定设备，遇到切号/登录失效阻断。','Web显示授权来源、最后检查时间与恢复入口；Token保留服务端secret_ref。'],
   |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
68 | …egration/test_account_capabilities.py','真机核对一个账号并模拟身份不一致（不自动切换账号）'],
69 | …
   |

E501 Line too long (188 > 100)
  --> artifacts/review-20260905/build-plan.py:68:99
   |
66 | …gistry.kt'],
67 | …gerprint，不复制账号表。','区分ANDROID登录指纹与API OAuth scope；未支持/过期/撤销分别返回稳定码。','提交前核对当前账号指纹及绑定设备…
68 | …test -q tests/integration/test_account_capabilities.py','真机核对一个账号并模拟身份不一致（不自动切换账号）'],
   |                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
69 | …
70 | …obileTask状态，不能直接互相复制',
   |

E501 Line too long (111 > 100)
  --> artifacts/review-20260905/build-plan.py:70:76
   |
68 | ['新增 tests/integration/test_account_capabilities.py','.venv/bin/python -m pytest -q tests/integration/test_account_capabilities.py',…
69 | '账号名相同不当成同一账号；失效、错号、错设备都不能申请提交许可。')
70 | add(13,'统一目标状态机与错误合同','M2 发布核心',[2],(1,2),'已有PublishState和MobileTask状态，不能直接互相复制',
   |                                                                                                      ^^^^^^^^^^
71 | ['packages/domain/src/cloudctl_domain/',P+'schemas.py',P+'mobile_schemas.py','contracts/'],
72 | ['列出现有所有状态及调用方，写新旧映射表与允许转移矩阵。','加入PREPARED/DRAFT_SAVED/平台接收/审核中/公开成功语义，决定兼容存储方式。',…
   |

E501 Line too long (143 > 100)
  --> artifacts/review-20260905/build-plan.py:73:101
   |
71 | …P+'mobile_schemas.py','contracts/'],
72 | … ','加入PREPARED/DRAFT_SAVED/平台接收/审核中/公开成功语义，决定兼容存储方式。','定义失败是否可重试及提交边界，UNKNOWN只允许查询/人工…
73 | …_domain.py tests/contracts/test_openapi_contract.py','pnpm contracts','pnpm typecheck'],
   |                                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
74 | … 。')
75 | … ',[10,11,12,13],(2,3),'Plan/Snapshot/Target/Approval/Outbox表已有',
   |

E501 Line too long (124 > 100)
  --> artifacts/review-20260905/build-plan.py:75:83
   |
73 | ['.venv/bin/python -m pytest -q tests/unit/test_backend_domain.py tests/contracts/test_openapi_contract.py','pnpm contracts','pnpm typ…
74 | '非法倒退转移被拒绝；填表SUCCEEDED不能使Target变公开成功。')
75 | add(14,'计划校验、快照冻结与Product发布入口','M2 发布核心',[10,11,12,13],(2,3),'Plan/Snapshot/Target/Approval/Outbox表已有',
   |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^
76 | [P+'services.py',P+'routes.py',P+'schemas.py',P+'db.py','tests/integration/test_backend_control_api.py'],
77 | ['扩展现有Plan合同以source.kind分派ProductRevision/ContentRevision，避免重复Plan体系。','校验source租户、媒体READY、账号能力、设备绑…
   |

E501 Line too long (173 > 100)
  --> artifacts/review-20260905/build-plan.py:78:101
   |
76 | …tion/test_backend_control_api.py'],
77 | … 重复Plan体系。','校验source租户、媒体READY、账号能力、设备绑定、平台格式并生成previewHash。','同事务写Plan/Target/不可变快照/审批/ou…
78 | …_api.py tests/integration/test_backend_accounts_media_content.py','新增Product到Plan到Target集成用例'],
   |                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
79 | … 内容。')
80 | …,'Temporal/Outbox已有；本轮未证明真PostgreSQL和历史replay',
   |

E501 Line too long (129 > 100)
  --> artifacts/review-20260905/build-plan.py:80:82
   |
78 | ['.venv/bin/python -m pytest -q tests/integration/test_backend_control_api.py tests/integration/test_backend_accounts_media_content.py…
79 | '新商品通过正式发布入口建计划；重复请求只有一个Plan；来源修改不影响冻结内容。')
80 | add(15,'复用Outbox编排并验证PostgreSQL互斥','M2 发布核心',[14],(1.5,3),'Temporal/Outbox已有；本轮未证明真PostgreSQL和历史replay',
   |                                                                                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
81 | ['services/temporal-worker/src/cloudctl_worker/','services/outbox-dispatcher/src/cloudctl_outbox/',P+'mobile_service.py','tests/replay…
82 | ['消费既有outbox为Target选择API或APK执行器；同event_id仅处理一次。','固定账号再设备的锁顺序，PG租约fence递增；API目标不伪造deviceId。'…
   |

E501 Line too long (159 > 100)
  --> artifacts/review-20260905/build-plan.py:83:96
   |
81 | …ox-dispatcher/src/cloudctl_outbox/',P+'mobile_service.py','tests/replay/'],
82 | … 。','固定账号再设备的锁顺序，PG租约fence递增；API目标不伪造deviceId。','在临时PostgreSQL数据库跑实际Alembic升级及并发领取，不操作现…
83 | …outbox.py tests/replay','在隔离测试PostgreSQL上执行alembic upgrade head/current及新增并发测试'],
   |                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
84 | … 重放日志。')
85 | …,3),'AutomationStore、CloudTaskClient、SyncService已存在',
   |

E501 Line too long (121 > 100)
  --> artifacts/review-20260905/build-plan.py:85:84
   |
83 | ['.venv/bin/python -m pytest -q tests/integration/test_backend_outbox.py tests/replay','在隔离测试PostgreSQL上执行alembic upgrade head…
84 | '并发领取仍单Runner；Outbox至少一次投递不重复业务；有PG和真实历史重放日志。')
85 | add(16,'APK任务协议持久化与恢复补齐','M2 发布核心',[13,15],(1.5,3),'AutomationStore、CloudTaskClient、SyncService已存在',
   |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^
86 | [K+'automation/AutomationTask.kt',K+'data/AutomationStore.kt',K+'network/CloudTaskClient.kt',K+'service/CompanionSyncService.kt'],
87 | ['扩展版本化任务合同包含targetId/snapshotHash/accountFingerprint/channel；未知版本拒绝。','核对taskId+canonical digest的持久化去重，…
   |

E501 Line too long (310 > 100)
  --> artifacts/review-20260905/build-plan.py:87:80
   |
85 | …lient、SyncService已存在',
86 | …'service/CompanionSyncService.kt'],
87 | …askId+canonical digest的持久化去重，重复相同内容返回旧回执，异内容拒绝。','状态先落本地DB再ACK，事件携带唯一ID/序号；旧fence不可继续执行。','进程恢复按PREPARING/COMMIT_STARTED分支，准备可恢复，提交已开始只对账。'],
   |      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
88 | … /异摘要/旧fence测试'],
89 | …
   |

E501 Line too long (118 > 100)
  --> artifacts/review-20260905/build-plan.py:88:94
   |
86 | [K+'automation/AutomationTask.kt',K+'data/AutomationStore.kt',K+'network/CloudTaskClient.kt',K+'service/CompanionSyncService.kt'],
87 | ['扩展版本化任务合同包含targetId/snapshotHash/accountFingerprint/channel；未知版本拒绝。','核对taskId+canonical digest的持久化去重，…
88 | ['./mobile/companion/build-external.sh testDebugUnitTest lintDebug','新增AutomationStore进程恢复/异摘要/旧fence测试'],
   |                                                                                                      ^^^^^^^^^^^^^^^^^
89 | '重启不会丢任务或重复最终动作；未知协议失败关闭。')
90 | add(17,'任务绑定的媒体授权与流式投递','M2 发布核心',[8,14,16],(1.5,3),'已有下载校验/MediaStore导出；当前仅限制到租户',
   |

E501 Line too long (118 > 100)
  --> artifacts/review-20260905/build-plan.py:90:74
   |
88 | ['./mobile/companion/build-external.sh testDebugUnitTest lintDebug','新增AutomationStore进程恢复/异摘要/旧fence测试'],
89 | '重启不会丢任务或重复最终动作；未知协议失败关闭。')
90 | add(17,'任务绑定的媒体授权与流式投递','M2 发布核心',[8,14,16],(1.5,3),'已有下载校验/MediaStore导出；当前仅限制到租户',
   |                                                                                                     ^^^^^^^^^^^^^^^^^^
91 | [P+'mobile_service.py',P+'mobile_routes.py',K+'media/MediaDelivery.kt',K+'data/MediaDeliveryCoordinator.kt'],
92 | ['新增delivery grant绑定target/task/device/manifestHash/到期，下载请求必须属于清单。','按snapshot中媒体ID和hash生成manifest，不接受设…
   |

E501 Line too long (295 > 100)
  --> artifacts/review-20260905/build-plan.py:92:81
   |
90 | … ；当前仅限制到租户',
91 | …dinator.kt'],
92 | …t中媒体ID和hash生成manifest，不接受设备随意指定同租户资产。','流式下载.part，长度/hash校验后原子安装；缓存命中必须重验绑定与hash。','在本地持久化URI映射，重复领取复用；失败和取消只删除本任务产物。'],
   |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
93 | …uild-external.sh testDebugUnitTest','真机100MB视频传输及断网/hash错误验收'],
94 | …
   |

E501 Line too long (172 > 100)
  --> artifacts/review-20260905/build-plan.py:93:101
   |
91 | …,K+'data/MediaDeliveryCoordinator.kt'],
92 | … 须属于清单。','按snapshot中媒体ID和hash生成manifest，不接受设备随意指定同租户资产。','流式下载.part，长度/hash校验后原子安装；缓存…
93 | ….py','./mobile/companion/build-external.sh testDebugUnitTest','真机100MB视频传输及断网/hash错误验收'],
   |                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
94 | …
95 | …y_select_N只按第N个选择节点',
   |

E501 Line too long (179 > 100)
   --> artifacts/review-20260905/build-plan.py:98:101
    |
 96 | …on/CloudCtlAccessibilityService.kt',K+'media/MediaGalleryExporter.kt'],
 97 | …'建立assetId/hash/URI到可验证选项的映射，优先受控相册和唯一标识。','编译选择步骤前验证所有素材已导出；选后核对顺序/封面/数量和图像…
 98 | …'./mobile/companion/build-external.sh testDebugUnitTest','OnePlus+闲鱼7.27.90执行A/B/C素材和干扰图验收'],
    |                            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 99 | …
100 | …价格配方，缺完整字段回读',
    |

E501 Line too long (101 > 100)
   --> artifacts/review-20260905/build-plan.py:100:70
    |
 98 | ['.venv/bin/python -m pytest -q tests/unit/test_xianyu_publish_recipe.py','./mobile/companion/build-external.sh testDebugUnitTest','O…
 99 | '实际选中A/B/C且顺序一致；不确定时不提交。')
100 | add(19,'闲鱼完整商品预填和预览证据','M3 闲鱼',[10,12,18],(1.5,3),'已有描述/价格配方，缺完整字段回读',
    |                                                                                                     ^
101 | [P+'xianyu_publish.py',K+'automation/TargetLocatorRegistry.kt','contracts/xianyu-publish-text.example.json'],
102 | ['根据实际UI补标题/描述/价格/成色/运费/发货地，字段存在性由当前类目决定。','每次打开面板和确认字段都有后置条件；输入后读回Decimal价…
    |

E501 Line too long (124 > 100)
   --> artifacts/review-20260905/build-plan.py:103:89
    |
101 | [P+'xianyu_publish.py',K+'automation/TargetLocatorRegistry.kt','contracts/xianyu-publish-text.example.json'],
102 | ['根据实际UI补标题/描述/价格/成色/运费/发货地，字段存在性由当前类目决定。','每次打开面板和确认字段都有后置条件；输入后读回Decimal价…
103 | ['.venv/bin/python -m pytest -q tests/unit/test_xianyu_publish_recipe.py','真机单商品三图字段读回、草稿恢复、必填缺失验收'],
    |                                                                                                      ^^^^^^^^^^^^^^^^^^^^^^^
104 | '商品、媒体、价格、运费和账号可逐项核对，预填不触发最终发布。')
105 | add(20,'最终提交许可与最多一次执行','M3 闲鱼',[13,16,19],(2,4),'数据库CommitIntent存在，APK最终发布协议未闭环',
    |

E501 Line too long (111 > 100)
   --> artifacts/review-20260905/build-plan.py:105:76
    |
103 | ['.venv/bin/python -m pytest -q tests/unit/test_xianyu_publish_recipe.py','真机单商品三图字段读回、草稿恢复、必填缺失验收'],
104 | '商品、媒体、价格、运费和账号可逐项核对，预填不触发最终发布。')
105 | add(20,'最终提交许可与最多一次执行','M3 闲鱼',[13,16,19],(2,4),'数据库CommitIntent存在，APK最终发布协议未闭环',
    |                                                                                                      ^^^^^^^^^^
106 | [P+'services.py',P+'mobile_service.py',P+'db.py',K+'data/AutomationStore.kt',K+'automation/LocalAutomationExecutor.kt'],
107 | ['复用CommitIntent，加target唯一约束/一次提交许可；核对现有attempt_no不能允许第二次最终提交。','许可绑定snapshot/审批/账号/fence/到…
    |

E501 Line too long (370 > 100)
   --> artifacts/review-20260905/build-plan.py:107:68
    |
105 | … 布协议未闭环',
106 | …lAutomationExecutor.kt'],
107 | …'许可绑定snapshot/审批/账号/fence/到期；过期、错号、取消请求拒绝。','APK先持久化COMMIT_STARTED再点唯一发布节点；该动作不可用通用步骤重试。','分别在许可前、日志落盘后、点击后断网/杀进程，恢复不再次点击。','API Publisher采用同等提交账本语义，避免API失败后自动切APK重复发送。'],
    |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^…^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
108 | …tegration/test_publish_commit_permit.py','./mobile/companion/build-external.sh testDebugUnitTest','真机提交断点验收（受控内容、用户确认）'],
109 | …
    |

E501 Line too long (235 > 100)
   --> artifacts/review-20260905/build-plan.py:108:99
    |
106 | …lAutomationExecutor.kt'],
107 | …'许可绑定snapshot/审批/账号/fence/到期；过期、错号、取消请求拒绝。','APK先持久化COMMIT_STARTED再点唯一发布节点；该动作不可用通用步骤重试。','分…
108 | …tegration/test_publish_commit_permit.py','./mobile/companion/build-external.sh testDebugUnitTest','真机提交断点验收（受控内容、用户确认）'],
    |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
109 | …
110 | … 结果',
    |

E501 Line too long (102 > 100)
   --> artifacts/review-20260905/build-plan.py:110:71
    |
108 | ['新增 tests/integration/test_publish_commit_permit.py','.venv/bin/python -m pytest -q tests/integration/test_publish_commit_permit.p…
109 | '每Target最多一次提交尝试；重复许可/任务/重启均无重复发布。')
110 | add(21,'结果对账、审核状态与人工处理','M3 闲鱼',[20],(1.5,3),'现有MobileTask终态不能证明平台发布结果',
    |                                                                                                     ^^
111 | [P+'services.py',P+'mobile_service.py','services/temporal-worker/src/cloudctl_worker/',K+'automation/'],
112 | ['定义结构化平台回执：externalId/url、平台接收/审核/公开状态、证据hash、账号指纹。','闲鱼按当前账号商品列表/详情核对标题图价格；不以…
    |

E501 Line too long (108 > 100)
   --> artifacts/review-20260905/build-plan.py:115:75
    |
113 | ['新增 tests/integration/test_publish_reconciliation.py','真机成功/平台拒绝/审核中/响应丢失验收'],
114 | '填表、已接收、审核中、公开成功、未知严格分开；UNKNOWN不自动重发。')
115 | add(22,'Web 一次确认发布向导和结果页','M3 闲鱼',[9,11,14,21],(2,3),'现有发布路由重定向到通用OperationsView',
    |                                                                                                     ^^^^^^^^
116 | ['apps/web/src/views/PublishWizardView.vue（新增）','apps/web/src/views/PublishPlanView.vue（新增）','apps/web/src/router.ts','packag…
117 | ['独立路由保留planId/targetId，选来源修订、平台账号、媒体和平台覆盖。','调用validate展示每目标previewHash与阻塞字段；用户一次确认后su…
    |

E501 Line too long (127 > 100)
   --> artifacts/review-20260905/build-plan.py:118:91
    |
116 | ['apps/web/src/views/PublishWizardView.vue（新增）','apps/web/src/views/PublishPlanView.vue（新增）','apps/web/src/router.ts','packag…
117 | ['独立路由保留planId/targetId，选来源修订、平台账号、媒体和平台覆盖。','调用validate展示每目标previewHash与阻塞字段；用户一次确认后su…
118 | ['pnpm contracts','pnpm typecheck','pnpm --filter @cloudctl/web test','新增真实API+测试数据库的Publish E2E（不拦截所有请求）'],
    |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^
119 | '能从真实Product建计划到查看结果；双击无重复；无mock回执；阶段名称准确。')
120 | add(23,'平台权限探测与适配器注册合同','M4 三内容平台',[2,12,13],(1,2),'除闲鱼外未见已接入的移动定位器',
    |

E501 Line too long (103 > 100)
   --> artifacts/review-20260905/build-plan.py:120:68
    |
118 | ['pnpm contracts','pnpm typecheck','pnpm --filter @cloudctl/web test','新增真实API+测试数据库的Publish E2E（不拦截所有请求）'],
119 | '能从真实Product建计划到查看结果；双击无重复；无mock回执；阶段名称准确。')
120 | add(23,'平台权限探测与适配器注册合同','M4 三内容平台',[2,12,13],(1,2),'除闲鱼外未见已接入的移动定位器',
    |                                                                                                      ^^
121 | ['packages/automation-sdk/src/cloudctl_automation_sdk/',P+'platform_capabilities.py（新增）','docs/v1/platform-capabilities.json（新…
122 | ['记录四平台账号实际授权/scope、渠道、格式、限制、审核方式与文档日期。','定义validate/prepare/before_commit/commit_once/reconcile/cle…
    |

E501 Line too long (104 > 100)
   --> artifacts/review-20260905/build-plan.py:125:74
    |
123 | ['新增适配器合同测试：未知平台/错误scope/错误channel/过期版本','逐账号保存脱敏权限探测证据'],
124 | '每个平台有已证实渠道或明确阻塞；公开资料和账号实际权限分栏。')
125 | add(24,'小红书图文发布适配器','M4 三内容平台',[11,17,20,21,23],(3,5),'本机小红书8.50.1；执行器尚未接入',
    |                                                                                                     ^^^^
126 | [K+'automation/TargetLocatorRegistry.kt',P+'publishers/xiaohongshu.py（新增）','docs/compatibility/'],
127 | ['按V1-23选择实际可用分享/API/UI路线；记录能力限制，不安装未经验证第三方私有API。','完成账号核对、精确多图选择、标题正文话题预填、预…
    |

E501 Line too long (108 > 100)
   --> artifacts/review-20260905/build-plan.py:130:79
    |
128 | ['新增tests/unit/test_xiaohongshu_publisher.py','Android单测及8.50.1真机图文全链路验收'],
129 | '指定图文发布到指定账号；有外部结果证据；审核中不显示公开成功。')
130 | add(25,'抖音视频发布适配器','M4 三内容平台',[11,17,20,21,23],(3,5),'本机抖音39.6.0；需核查video.create授权',
    |                                                                                                     ^^^^^^^^
131 | [P+'publishers/douyin.py（新增）',K+'automation/TargetLocatorRegistry.kt','docs/compatibility/'],
132 | ['验证实际OAuth scope；有正式权限用API，否则按已授权UI路线实现。','API先上传并保存video_id，UI精确选择指定视频；验证时长/格式/封面，…
    |

E501 Line too long (291 > 100)
   --> artifacts/review-20260905/build-plan.py:132:68
    |
130 | ….create授权',
131 | …],
132 | … 确选择指定视频；验证时长/格式/封面，限制来自能力配置。','填写标题/话题/可见范围，生成预览hash；调用共用提交账本。','上传成功不等于发布成功；保存item_id并查询审核/可见状态；请求丢失不再次创建。'],
    |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
133 | … 态验收'],
134 | …
    |

E501 Line too long (109 > 100)
   --> artifacts/review-20260905/build-plan.py:135:70
    |
133 | ['新增tests/unit/test_douyin_publisher.py','对真实授权账户进行单视频发布、超限、授权失效和审核状态验收'],
134 | '完整视频到指定账号；上传、提交、审核三阶段可追溯；无跨渠道重复。')
135 | add(26,'微信公众号文章发布适配器','M4 三内容平台',[11,20,21,23],(3,5),'官方文档正文本轮未取得；账号资格未知',
    |                                                                                                      ^^^^^^^^
136 | [P+'publishers/wechat_official.py（新增）','docs/v1/wechat-permissions.md（新增）'],
137 | ['先从用户公众号后台和官方文档确认草稿/发布/状态查询权限、端点与参数，保存日期；不据第三方博客锁合同。','上传封面和正文图，HTML清洗/…
    |

E501 Line too long (355 > 100)
   --> artifacts/review-20260905/build-plan.py:137:53
    |
135 | … 号资格未知',
136 | …
137 | … 合同。','上传封面和正文图，HTML清洗/内联样式/图片地址替换；生成草稿并预览。','有发布能力才使用共用许可提交，记录publish/article ID和状态；只会创建草稿则标DRAFT_SAVED。','公众号文章发布与粉丝群发分开；无权限则明确阻塞完整发布，按平台后台合法手工流程补验收。'],
    |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
138 | … '],
139 | …
    |

E501 Line too long (119 > 100)
   --> artifacts/review-20260905/build-plan.py:140:73
    |
138 | ['新增tests/unit/test_wechat_official_publisher.py','真实公众号草稿、发布、状态查询与权限不足验收'],
139 | '文章发布有可核验URL/ID；只有草稿权限不得把该任务标done。')
140 | add(27,'多平台多账号排队与部分失败','M5 完整V1',[15,22,24,25,26],(1.5,3),'已有批次操作骨架，需统一真正的PublishTarget',
    |                                                                                                     ^^^^^^^^^^^^^^^^^^^
141 | [P+'services.py','services/temporal-worker/src/cloudctl_worker/','apps/web/src/views/PublishPlanView.vue'],
142 | ['同一计划按平台账号展开Target，冻结每个目标内容覆盖。','设备和账号串行；不同设备可并行，默认并发1，配置上限验证。','汇总成功/失败/…
    |

E501 Line too long (111 > 100)
   --> artifacts/review-20260905/build-plan.py:150:77
    |
148 | ['实施方案A06-A18真实验收，日志包含设备/版本/task/target/时间和hash'],
149 | '无USB任务能独立运行；提交不重复；账号异常暂停；24h报告可复核。')
150 | add(29,'Release 构建、部署备份与回滚','M5 完整V1',[1,28],(1.5,3),'当前已装debug APK；服务部署与本地版本未比对',
    |                                                                                                      ^^^^^^^^^^
151 | ['mobile/companion/app/build.gradle.kts','infra/','scripts/backup.sh','scripts/restore.sh','docs/runbooks/'],
152 | ['配置release signing secret_ref、递增versionCode；产物记录SHA和签名摘要，debuggable=false。','生产认证关闭dev bypass；前端固定角色…
    |

E501 Line too long (376 > 100)
   --> artifacts/review-20260905/build-plan.py:152:82
    |
150 | … 地版本未比对',
151 | …/runbooks/'],
152 | … 产认证关闭dev bypass；前端固定角色改为真实会话/权限，API地址和TLS指纹改环境配置；验证租户隔离、API TLS、对象存储和后台任务环境。','在测试部署做PG备份恢复和schema回滚/前滚演练；不在用户真实库试破坏性迁移。','安装同签名升级验证绑定/任务保留，记录回滚可行性，不强制换签名或降级。'],
    |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^…^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
153 | …ompanion（验版本与flags）','隔离环境备份恢复及灰度运行检查'],
154 | …
    |

E501 Line too long (157 > 100)
   --> artifacts/review-20260905/build-plan.py:153:90
    |
151 | …up.sh','scripts/restore.sh','docs/runbooks/'],
152 | … 签名摘要，debuggable=false。','生产认证关闭dev bypass；前端固定角色改为真实会话/权限，API地址和TLS指纹改环境配置；验证租户隔离、API…
153 | …ys package com.company.cloudctl.companion（验版本与flags）','隔离环境备份恢复及灰度运行检查'],
    |                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
154 | …
155 | …,2),'完整端到端里程碑本轮验收0/8',
    |

E701 Multiple statements on one line (colon)
   --> artifacts/review-20260905/build-plan.py:167:19
    |
165 |   old=prior.get(task['id'],{})
166 |   for field in ('status','owner','blocker','progress_notes','verified_at','acceptance_evidence'):
167 |    if field in old:task[field]=old[field]
    |                   ^
168 | ids={t['id'] for t in items}
169 | for t in items:
    |

E501 Line too long (220 > 100)
   --> artifacts/review-20260905/build-plan.py:171:101
    |
169 | …
170 | …
171 | …on-days, external waits excluded; no implementation task accepted in this review','tasks':items},ensure_ascii=False,indent=2))
    |        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
172 | … 施前核对最新代码。', '', '每张卡完成时都要保存实际退出码、测试摘要、变更清单和证据；命令中的自然语言项是待实现验收步骤，不能复制为 …
173 | …
    |

E501 Line too long (400 > 100)
   --> artifacts/review-20260905/build-plan.py:172:74
    |
170 | …
171 | …n-days, external waits excluded; no implementation task accepted in this review','tasks':items},ensure_ascii=False,indent=2))
172 | … 施前核对最新代码。', '', '每张卡完成时都要保存实际退出码、测试摘要、变更清单和证据；命令中的自然语言项是待实现验收步骤，不能复制为 shell。所有 Python 命令使用项目 `.venv/bin/python`。', '', '状态：todo/doing/blocked/blocked_hardware/review/done。当前任务没有完成验收，已有能力列仅表示可复用的基础。', '']
    |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^…^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
173 | …
174 | …encies']) or '无'}；状态：{t['status']}。",f"- 估算：{t['estimate_low']}–{t['estimate_high']} 人日（非承诺工期）。",f"- 已有基础：{t['existing']}",f"- 文件范围：{'；'.join('`'+x+'`' for x in t['files'])}",f"- 输入条件：{'所有依赖验收完成' if t['dependencies'] else '读完当前审核及实施方案'}。{t['blocker']}",''…
    |

E501 Line too long (422 > 100)
   --> artifacts/review-20260905/build-plan.py:174:94
    |
172 | … 施前核对最新代码。', '', '每张卡完成时都要保存实际退出码、测试摘要、变更清单和证据；命令中的自然语言项是待实现验收步骤，不能复制为 shell。所有 Python 命令使用项目 `.venv/bin/python`。', '', '状态：todo/doing/blocked/blocked_hardware/review/done。当前任务没有完成验收，已有能力列仅表示可复用的基础。', '']
173 | …
174 | …encies']) or '无'}；状态：{t['status']}。",f"- 估算：{t['estimate_low']}–{t['estimate_high']} 人日（非承诺工期）。",f"- 已有基础：{t['existing']}",f"- 文件范围：{'；'.join('`'+x+'`' for x in t['files'])}",f"- 输入条件：{'所有依赖验收完成' if t['dependencies'] else '读完当前审核及实施方案'}。{t['blocker']}",'','实施步骤：','']
    |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^…^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
175 | …
176 | …
    |

E501 Line too long (197 > 100)
   --> artifacts/review-20260905/build-plan.py:177:80
    |
175 | …
176 | …
177 | … 源码回到本卡前检查点；数据库仅在隔离验证后使用本卡迁移的回退/前滚方案；已发生的平台发布不通过重跑任务回退。",'']
    |                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
178 | …
179 | …'estimate_high'] for x in items))
    |

E501 Line too long (116 > 100)
   --> artifacts/review-20260905/build-plan.py:179:101
    |
177 |  lines += ['',f"验收：{t['acceptance']}",'',f"证据目录：`{t['evidence']}`。失败回退：源码回到本卡前检查点；数据库仅在隔离验证后使用…
178 | (OUT/'03-逐项任务卡.md').write_text('\n'.join(lines))
179 | print('tasks',len(items),'person-days',sum(x['estimate_low'] for x in items),sum(x['estimate_high'] for x in items))
    |                                                                                                     ^^^^^^^^^^^^^^^^

I001 [*] Import block is un-sorted or un-formatted
  --> artifacts/review-20260905/build-workbook.py:1:1
   |
 1 | / from pathlib import Path
 2 | | from collections import defaultdict
 3 | | import json,re,hashlib
 4 | | from openpyxl import Workbook,load_workbook
 5 | | from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
 6 | | from openpyxl.worksheet.datavalidation import DataValidation
 7 | | from openpyxl.formatting.rule import FormulaRule
 8 | | from openpyxl.workbook.properties import CalcProperties
   | |_______________________________________________________^
 9 |   ROOT=Path(__file__).resolve().parents[2]
10 |   D=ROOT/'docs/v1'; A=ROOT/'artifacts/review-20260905'
   |
help: Organize imports
   |
   - from pathlib import Path
1  + import hashlib
2  + import json
3  + import re
4  | from collections import defaultdict
   - import json,re,hashlib
   - from openpyxl import Workbook,load_workbook
   - from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
   - from openpyxl.worksheet.datavalidation import DataValidation
5  + from pathlib import Path
6  +
7  + from openpyxl import Workbook, load_workbook
8  | from openpyxl.formatting.rule import FormulaRule
9  + from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
10 | from openpyxl.workbook.properties import CalcProperties
11 + from openpyxl.worksheet.datavalidation import DataValidation
12 +
13 | ROOT=Path(__file__).resolve().parents[2]
   |

E401 [*] Multiple imports on one line
 --> artifacts/review-20260905/build-workbook.py:3:1
  |
1 | from pathlib import Path
2 | from collections import defaultdict
3 | import json,re,hashlib
  | ^^^^^^^^^^^^^^^^^^^^^^
4 | from openpyxl import Workbook,load_workbook
5 | from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
  |
help: Split imports
  |
2 | from collections import defaultdict
  - import json,re,hashlib
3 + import json
4 + import re
5 + import hashlib
6 | from openpyxl import Workbook,load_workbook
  |

F401 [*] `openpyxl.styles.Border` imported but unused
 --> artifacts/review-20260905/build-workbook.py:5:56
  |
3 | import json,re,hashlib
4 | from openpyxl import Workbook,load_workbook
5 | from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
  |                                                        ^^^^^^
6 | from openpyxl.worksheet.datavalidation import DataValidation
7 | from openpyxl.formatting.rule import FormulaRule
  |
help: Remove unused import
  |
4 | from openpyxl import Workbook,load_workbook
  - from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
5 + from openpyxl.styles import Font,PatternFill,Alignment
6 | from openpyxl.worksheet.datavalidation import DataValidation
  |

F401 [*] `openpyxl.styles.Side` imported but unused
 --> artifacts/review-20260905/build-workbook.py:5:63
  |
3 | import json,re,hashlib
4 | from openpyxl import Workbook,load_workbook
5 | from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
  |                                                               ^^^^
6 | from openpyxl.worksheet.datavalidation import DataValidation
7 | from openpyxl.formatting.rule import FormulaRule
  |
help: Remove unused import
  |
4 | from openpyxl import Workbook,load_workbook
  - from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
5 + from openpyxl.styles import Font,PatternFill,Alignment
6 | from openpyxl.worksheet.datavalidation import DataValidation
  |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:10:17
   |
 8 | from openpyxl.workbook.properties import CalcProperties
 9 | ROOT=Path(__file__).resolve().parents[2]
10 | D=ROOT/'docs/v1'; A=ROOT/'artifacts/review-20260905'
   |                 ^
11 | tasks=json.loads((D/'tasks.json').read_text())['tasks']
12 | checks=[
   |

E501 Line too long (110 > 100)
  --> artifacts/review-20260905/build-workbook.py:18:85
   |
16 |  ['TS 类型（清理后）','通过','Web/Studio/合同通过',0,'typecheck-after-cleanup.log','编译类型检查'],
17 |  ['Web/Studio 构建','通过','两应用构建通过',0,'build.log','Studio 大包警告'],
18 |  ['Companion 单测+lint','通过','41 tests / 14 suites；lint成功',0,'android.log','主机测试，无障碍真机未验收'],
   |                                                                                                      ^^^^^^^^^
19 |  ['Ruff','失败','24 errors',1,'ruff.log','原始静态检查'],
20 |  ['格式检查','失败','27 files',1,'format.log','未为审计做批量格式改写'],
   |

E501 Line too long (102 > 100)
  --> artifacts/review-20260905/build-workbook.py:22:82
   |
20 |  ['格式检查','失败','27 files',1,'format.log','未为审计做批量格式改写'],
21 |  ['Pyright','失败','12 errors',1,'pyright.log','Edge/Outbox类型合同待修'],
22 |  ['Web lint（清理后）','失败','4 errors',1,'web-lint-after-cleanup.log','原5个，去掉1个无用测试变量'],
   |                                                                                                     ^^
23 |  ['安全扫描','无效/需重验','退出0，grep报错',0,'security.log','不能视为所有扫描规则通过'],
24 |  ['默认E2E','环境污染','4173复用其他项目',1,'e2e.log','不作为本项目失败数量；Studio未运行'],
   |

E501 Line too long (123 > 100)
  --> artifacts/review-20260905/build-workbook.py:25:75
   |
23 |  ['安全扫描','无效/需重验','退出0，grep报错',0,'security.log','不能视为所有扫描规则通过'],
24 |  ['默认E2E','环境污染','4173复用其他项目',1,'e2e.log','不作为本项目失败数量；Studio未运行'],
25 |  ['独立端口Web smoke','部分失败','16通过/4失败/8既有跳过',1,'e2e-isolated.log','两处非精确文本定位器；不是已确认滚动故障'],
   |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^
26 |  ['商品专用E2E','通过','1 passed',0,'e2e-product.log','API拦截用例，不是真实数据库到真机'],
27 |  ['真机盘点','通过','OnePlus Android14；四App已安装',0,'device.json','项目无障碍服务未启用'],
   |

B905 `zip()` without an explicit `strict=` parameter
  --> artifacts/review-20260905/build-workbook.py:31:83
   |
29 | …,None,'','本轮审核没有发布外部内容'],
30 | …
31 | …date':'2026-09-05','checks':[dict(zip(['check','result','detail','exitCode','log','limitation'],r)) for r in checks]},ensure_ascii=Fa…
   |                                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
32 | …
33 | … 类型及只读入口','V1-03~07','source检索；01审核F10','未验收'],
   |
help: Add explicit value for parameter `strict=`

E501 Line too long (195 > 100)
  --> artifacts/review-20260905/build-workbook.py:31:101
   |
29 | … '],
30 | …
31 | …(zip(['check','result','detail','exitCode','log','limitation'],r)) for r in checks]},ensure_ascii=False,indent=2))
   |                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
32 | …
33 | …ce检索；01审核F10','未验收'],
   |

E501 Line too long (174 > 100)
  --> artifacts/review-20260905/build-workbook.py:46:66
   |
44 | …
45 | …'7.27.90','预填代码已有，未最终提交','身份/精确媒体/字段回读/permit/对账','单次商品发布并核对列表/详情','V1-18~22'],
46 | …仅安装，未接执行器','分享成功不等于发布；标题正文/图序/账号','笔记结果+审核状态；图文首验','V1-23/24'],
   |                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
47 | …未核实video.create实际授权','上传→创建→审核；提交后禁自动切渠道','视频ID/作品核验/账号一致','V1-23/25'],
48 | ….76（非公众号能力证明）','主体/权限未知；文档正文未取到','草稿/发布/群发分开，不能默认个人微信能发','文章ID/URL+状态；只有草稿不算don…
   |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:62:32
   |
60 | findings=[]
61 | for m in re.finditer(r'^### (F\d+) / (P\d)：([^\n]+)\n(.*?)(?=\n### |\n## |\Z)',report,re.M|re.S):
62 |  num,prio,title,body=m.groups();findings.append([num,prio,title,body.strip(),'静态证据+本轮运行；具体限制见正文','待实施修复'])
   |                                ^
63 | # Build reusable, printable tables.
64 | wb=Workbook();wb.remove(wb.active)
   |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:64:14
   |
62 |  num,prio,title,body=m.groups();findings.append([num,prio,title,body.strip(),'静态证据+本轮运行；具体限制见正文','待实施修复'])
63 | # Build reusable, printable tables.
64 | wb=Workbook();wb.remove(wb.active)
   |              ^
65 | wb.calculation=CalcProperties(calcId=191029,fullCalcOnLoad=True)
66 | navy='17324D';teal='087F8C';light='EAF2F8';gray='526577'
   |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:66:14
   |
64 | wb=Workbook();wb.remove(wb.active)
65 | wb.calculation=CalcProperties(calcId=191029,fullCalcOnLoad=True)
66 | navy='17324D';teal='087F8C';light='EAF2F8';gray='526577'
   |              ^
67 | def sheet(name,headers,rows,widths=None,height=58):
68 |  ws=wb.create_sheet(name);ws.append(headers)
   |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:66:28
   |
64 | wb=Workbook();wb.remove(wb.active)
65 | wb.calculation=CalcProperties(calcId=191029,fullCalcOnLoad=True)
66 | navy='17324D';teal='087F8C';light='EAF2F8';gray='526577'
   |                            ^
67 | def sheet(name,headers,rows,widths=None,height=58):
68 |  ws=wb.create_sheet(name);ws.append(headers)
   |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:66:43
   |
64 | wb=Workbook();wb.remove(wb.active)
65 | wb.calculation=CalcProperties(calcId=191029,fullCalcOnLoad=True)
66 | navy='17324D';teal='087F8C';light='EAF2F8';gray='526577'
   |                                           ^
67 | def sheet(name,headers,rows,widths=None,height=58):
68 |  ws=wb.create_sheet(name);ws.append(headers)
   |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:68:26
   |
66 | navy='17324D';teal='087F8C';light='EAF2F8';gray='526577'
67 | def sheet(name,headers,rows,widths=None,height=58):
68 |  ws=wb.create_sheet(name);ws.append(headers)
   |                          ^
69 |  for row in rows:ws.append(row)
70 |  ws.freeze_panes='C2' if len(headers)>4 else 'A2';ws.auto_filter.ref=ws.dimensions
   |

E701 Multiple statements on one line (colon)
  --> artifacts/review-20260905/build-workbook.py:69:17
   |
67 | def sheet(name,headers,rows,widths=None,height=58):
68 |  ws=wb.create_sheet(name);ws.append(headers)
69 |  for row in rows:ws.append(row)
   |                 ^
70 |  ws.freeze_panes='C2' if len(headers)>4 else 'A2';ws.auto_filter.ref=ws.dimensions
71 |  ws.sheet_view.showGridLines=False
   |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:70:50
   |
68 |  ws=wb.create_sheet(name);ws.append(headers)
69 |  for row in rows:ws.append(row)
70 |  ws.freeze_panes='C2' if len(headers)>4 else 'A2';ws.auto_filter.ref=ws.dimensions
   |                                                  ^
71 |  ws.sheet_view.showGridLines=False
72 |  for c in ws[1]:c.font=Font(name='微软雅黑',bold=True,color='FFFFFF',size=11);c.fill=PatternFill('solid',fgColor=navy);c.alignment=Ali…
   |

E701 Multiple statements on one line (colon)
  --> artifacts/review-20260905/build-workbook.py:72:16
   |
70 |  ws.freeze_panes='C2' if len(headers)>4 else 'A2';ws.auto_filter.ref=ws.dimensions
71 |  ws.sheet_view.showGridLines=False
72 |  for c in ws[1]:c.font=Font(name='微软雅黑',bold=True,color='FFFFFF',size=11);c.fill=PatternFill('solid',fgColor=navy);c.alignment=Ali…
   |                ^
73 |  ws.row_dimensions[1].height=32
74 |  for row in ws.iter_rows(min_row=2):
   |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:72:74
   |
70 |  ws.freeze_panes='C2' if len(headers)>4 else 'A2';ws.auto_filter.ref=ws.dimensions
71 |  ws.sheet_view.showGridLines=False
72 |  for c in ws[1]:c.font=Font(name='微软雅黑',bold=True,color='FFFFFF',size=11);c.fill=PatternFill('solid',fgColor=navy);c.alignment=Ali…
   |                                                                              ^
73 |  ws.row_dimensions[1].height=32
74 |  for row in ws.iter_rows(min_row=2):
   |

E501 Line too long (174 > 100)
  --> artifacts/review-20260905/build-workbook.py:72:97
   |
70 | ….dimensions
71 | …
72 | …ze=11);c.fill=PatternFill('solid',fgColor=navy);c.alignment=Alignment(wrap_text=True,vertical='center')
   |                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
73 | …
74 | …
   |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:72:115
   |
70 |  ws.freeze_panes='C2' if len(headers)>4 else 'A2';ws.auto_filter.ref=ws.dimensions
71 |  ws.sheet_view.showGridLines=False
72 |  for c in ws[1]:c.font=Font(name='微软雅黑',bold=True,color='FFFFFF',size=11);c.fill=PatternFill('solid',fgColor=navy);c.alignment=Ali…
   |                                                                                                                       ^
73 |  ws.row_dimensions[1].height=32
74 |  for row in ws.iter_rows(min_row=2):
   |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:76:51
   |
74 |  for row in ws.iter_rows(min_row=2):
75 |   for c in row:
76 |    c.font=Font(name='微软雅黑',size=10,color='243B53');c.alignment=Alignment(vertical='top',wrap_text=True)
   |                                                       ^
77 |    if c.row%2==0:c.fill=PatternFill('solid',fgColor='F0F5F9')
78 |   ws.row_dimensions[row[0].row].height=height
   |

E701 Multiple statements on one line (colon)
  --> artifacts/review-20260905/build-workbook.py:77:17
   |
75 |   for c in row:
76 |    c.font=Font(name='微软雅黑',size=10,color='243B53');c.alignment=Alignment(vertical='top',wrap_text=True)
77 |    if c.row%2==0:c.fill=PatternFill('solid',fgColor='F0F5F9')
   |                 ^
78 |   ws.row_dimensions[row[0].row].height=height
79 |  for i in range(1,len(headers)+1):ws.column_dimensions[__import__('openpyxl').utils.get_column_letter(i)].width=(widths or {}).get(i,2…
   |

E701 Multiple statements on one line (colon)
  --> artifacts/review-20260905/build-workbook.py:79:34
   |
77 |    if c.row%2==0:c.fill=PatternFill('solid',fgColor='F0F5F9')
78 |   ws.row_dimensions[row[0].row].height=height
79 |  for i in range(1,len(headers)+1):ws.column_dimensions[__import__('openpyxl').utils.get_column_letter(i)].width=(widths or {}).get(i,2…
   |                                  ^
80 |  ws.sheet_properties.pageSetUpPr.fitToPage=True
81 |  ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
   |

E501 Line too long (136 > 100)
  --> artifacts/review-20260905/build-workbook.py:79:101
   |
77 | …'F0F5F9')
78 | …
79 | …ns[__import__('openpyxl').utils.get_column_letter(i)].width=(widths or {}).get(i,24)
   |                                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
80 | …
81 | ….paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
   |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:81:39
   |
79 |  for i in range(1,len(headers)+1):ws.column_dimensions[__import__('openpyxl').utils.get_column_letter(i)].width=(widths or {}).get(i,2…
80 |  ws.sheet_properties.pageSetUpPr.fitToPage=True
81 |  ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
   |                                       ^
82 |  ws.print_title_rows='1:1';ws.print_options.horizontalCentered=True
83 |  ws.oddFooter.center.text='第 &P 页 / 共 &N 页';ws.oddFooter.right.text='2026-09-05 重审基线'
   |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:81:79
   |
79 |  for i in range(1,len(headers)+1):ws.column_dimensions[__import__('openpyxl').utils.get_column_letter(i)].width=(widths or {}).get(i,2…
80 |  ws.sheet_properties.pageSetUpPr.fitToPage=True
81 |  ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
   |                                                                               ^
82 |  ws.print_title_rows='1:1';ws.print_options.horizontalCentered=True
83 |  ws.oddFooter.center.text='第 &P 页 / 共 &N 页';ws.oddFooter.right.text='2026-09-05 重审基线'
   |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:81:106
   |
79 |  for i in range(1,len(headers)+1):ws.column_dimensions[__import__('openpyxl').utils.get_column_letter(i)].width=(widths or {}).get(i,2…
80 |  ws.sheet_properties.pageSetUpPr.fitToPage=True
81 |  ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
   |                                                                                                          ^
82 |  ws.print_title_rows='1:1';ws.print_options.horizontalCentered=True
83 |  ws.oddFooter.center.text='第 &P 页 / 共 &N 页';ws.oddFooter.right.text='2026-09-05 重审基线'
   |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:82:27
   |
80 |  ws.sheet_properties.pageSetUpPr.fitToPage=True
81 |  ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
82 |  ws.print_title_rows='1:1';ws.print_options.horizontalCentered=True
   |                           ^
83 |  ws.oddFooter.center.text='第 &P 页 / 共 &N 页';ws.oddFooter.right.text='2026-09-05 重审基线'
84 |  return ws
   |

E702 Multiple statements on one line (semicolon)
  --> artifacts/review-20260905/build-workbook.py:83:44
   |
81 |  ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
82 |  ws.print_title_rows='1:1';ws.print_options.horizontalCentered=True
83 |  ws.oddFooter.center.text='第 &P 页 / 共 &N 页';ws.oddFooter.right.text='2026-09-05 重审基线'
   |                                                ^
84 |  return ws
85 | summary=[
   |

E501 Line too long (107 > 100)
  --> artifacts/review-20260905/build-workbook.py:96:61
   |
94 |  ['首要断点','Product保存后误走Content下发；相册索引可能选错图','先V1-10/14/18；保留正确的既有测试'],
95 |  ['当前真机','OnePlus Android14，项目无障碍服务未启用','四平台App已安装；无实际发布动作'],
96 |  ['本轮清理','2个孤立mock源码 + 1个测试无用变量；撤下旧计划/制表脚本','9个文件有清理前备份；有效测试保留'],
   |                                                                                                     ^^^^^^^
97 |  ['入口','docs/v1/README.md','03任务卡供模型执行；tasks.json为结构化来源'],
98 |  ['版本口径','本地源码重审，2026-09-05','不推断远端服务已同步或平台权限已获批'],
   |

E702 Multiple statements on one line (semicolon)
   --> artifacts/review-20260905/build-workbook.py:100:61
    |
 98 |  ['版本口径','本地源码重审，2026-09-05','不推断远端服务已同步或平台权限已获批'],
 99 | ]
100 | ws=sheet('总览',['项目','当前值','说明'],summary,{1:25,2:70,3:75},42);ws['B6'].number_format='0%'
    |                                                                      ^
101 | # row checks: header=1; task count row4; done row5; ratio row6.
102 | rows=[]
    |

E501 Line too long (221 > 100)
   --> artifacts/review-20260905/build-workbook.py:104:100
    |
102 | …
103 | …
104 | …w'],t['estimate_high'],t['status'],t['existing'],t['blocker'] or '依赖满足后可领取',t['owner'],t['acceptance'],t['evidence']])
    |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
105 | …,'阻塞/启动条件','负责人','完成验收','证据目录'],rows,{1:12,2:35,3:22,4:32,5:12,6:12,7:16,8:58,9:46,10:16,11:78,12:32},92)
106 | …error='请选择有效状态';dv.errorTitle='状态错误';dv.showErrorMessage=True;ws.add_data_validation(dv);dv.add('G2:G31')
    |

E702 Multiple statements on one line (semicolon)
   --> artifacts/review-20260905/build-workbook.py:106:92
    |
104 |  rows.append([t['id'],t['title'],t['phase'],', '.join(t['dependencies']) or '无',t['estimate_low'],t['estimate_high'],t['status'],t['…
105 | ws=sheet('开发任务',['ID','任务','阶段','依赖','人日下限','人日上限','状态','已有基础（非验收）','阻塞/启动条件','负责人','完成验收',…
106 | dv=DataValidation(type='list',formula1='"todo,doing,blocked,blocked_hardware,review,done"');dv.error='请选择有效状态';dv.errorTitle=…
    |                                                                                            ^
107 | for val,col in [('done','D9EAD3'),('blocked','FCE4D6'),('review','FFF2CC')]:ws.conditional_formatting.add('G2:G31',FormulaRule(formul…
108 | rows=[]
    |

E702 Multiple statements on one line (semicolon)
   --> artifacts/review-20260905/build-workbook.py:106:111
    |
104 |  rows.append([t['id'],t['title'],t['phase'],', '.join(t['dependencies']) or '无',t['estimate_low'],t['estimate_high'],t['status'],t['…
105 | ws=sheet('开发任务',['ID','任务','阶段','依赖','人日下限','人日上限','状态','已有基础（非验收）','阻塞/启动条件','负责人','完成验收',…
106 | dv=DataValidation(type='list',formula1='"todo,doing,blocked,blocked_hardware,review,done"');dv.error='请选择有效状态';dv.errorTitle=…
    |                                                                                                                      ^
107 | for val,col in [('done','D9EAD3'),('blocked','FCE4D6'),('review','FFF2CC')]:ws.conditional_formatting.add('G2:G31',FormulaRule(formul…
108 | rows=[]
    |

E702 Multiple statements on one line (semicolon)
   --> artifacts/review-20260905/build-workbook.py:106:132
    |
104 | …无',t['estimate_low'],t['estimate_high'],t['status'],t['existing'],t['blocker'] or '依赖满足后可领取',t['owner'],t['acceptance'],t['…
105 | …已有基础（非验收）','阻塞/启动条件','负责人','完成验收','证据目录'],rows,{1:12,2:35,3:22,4:32,5:12,6:12,7:16,8:58,9:46,10:16,11:78,1…
106 | …review,done"');dv.error='请选择有效状态';dv.errorTitle='状态错误';dv.showErrorMessage=True;ws.add_data_validation(dv);dv.add('G2:G31…
    |                                                                   ^
107 | …s.conditional_formatting.add('G2:G31',FormulaRule(formula=[f'G2="{val}"'],fill=PatternFill('solid',fgColor=col)))
108 | …
    |

E702 Multiple statements on one line (semicolon)
   --> artifacts/review-20260905/build-workbook.py:106:157
    |
104 | …estimate_high'],t['status'],t['existing'],t['blocker'] or '依赖满足后可领取',t['owner'],t['acceptance'],t['evidence']])
105 | …启动条件','负责人','完成验收','证据目录'],rows,{1:12,2:35,3:22,4:32,5:12,6:12,7:16,8:58,9:46,10:16,11:78,12:32},92)
106 | …请选择有效状态';dv.errorTitle='状态错误';dv.showErrorMessage=True;ws.add_data_validation(dv);dv.add('G2:G31')
    |                                                                   ^
107 | …add('G2:G31',FormulaRule(formula=[f'G2="{val}"'],fill=PatternFill('solid',fgColor=col)))
108 | …
    |

E702 Multiple statements on one line (semicolon)
   --> artifacts/review-20260905/build-workbook.py:106:184
    |
104 | …,t['existing'],t['blocker'] or '依赖满足后可领取',t['owner'],t['acceptance'],t['evidence']])
105 | … ','证据目录'],rows,{1:12,2:35,3:22,4:32,5:12,6:12,7:16,8:58,9:46,10:16,11:78,12:32},92)
106 | …le='状态错误';dv.showErrorMessage=True;ws.add_data_validation(dv);dv.add('G2:G31')
    |                                                                   ^
107 | …rmula=[f'G2="{val}"'],fill=PatternFill('solid',fgColor=col)))
108 | …
    |

E701 Multiple statements on one line (colon)
   --> artifacts/review-20260905/build-workbook.py:107:76
    |
105 | ws=sheet('开发任务',['ID','任务','阶段','依赖','人日下限','人日上限','状态','已有基础（非验收）','阻塞/启动条件','负责人','完成验收',…
106 | dv=DataValidation(type='list',formula1='"todo,doing,blocked,blocked_hardware,review,done"');dv.error='请选择有效状态';dv.errorTitle=…
107 | for val,col in [('done','D9EAD3'),('blocked','FCE4D6'),('review','FFF2CC')]:ws.conditional_formatting.add('G2:G31',FormulaRule(formul…
    |                                                                            ^
108 | rows=[]
109 | for t in tasks:
    |

E501 Line too long (190 > 100)
   --> artifacts/review-20260905/build-workbook.py:107:101
    |
105 | … 基础（非验收）','阻塞/启动条件','负责人','完成验收','证据目录'],rows,{1:12,2:35,3:22,4:32,5:12,6:12,7:16,8:58,9:46,10:16,11:78,12:3…
106 | …view,done"');dv.error='请选择有效状态';dv.errorTitle='状态错误';dv.showErrorMessage=True;ws.add_data_validation(dv);dv.add('G2:G31')
107 | …conditional_formatting.add('G2:G31',FormulaRule(formula=[f'G2="{val}"'],fill=PatternFill('solid',fgColor=col)))
    |                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
108 | …
109 | …
    |

E501 Line too long (182 > 100)
   --> artifacts/review-20260905/build-workbook.py:110:101
    |
108 | …
109 | …
110 | …' for i,s in enumerate(t['steps'],1)),'\n'.join(t['verification_commands']),t['acceptance'],t['evidence']])
    |                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
111 | … 准','证据目录'],rows,{1:12,2:36,3:70,4:115,5:80,6:75,7:32},205)
112 | …
    |

E701 Multiple statements on one line (colon)
   --> artifacts/review-20260905/build-workbook.py:113:15
    |
111 | sheet('实施步骤',['ID','任务','修改范围','按顺序实施','验收命令/操作','通过标准','证据目录'],rows,{1:12,2:36,3:70,4:115,5:80,6:75,7:3…
112 | phase=defaultdict(lambda:[0,0,[]])
113 | for t in tasks:phase[t['phase']][0]+=t['estimate_low'];phase[t['phase']][1]+=t['estimate_high'];phase[t['phase']][2].append(t['id'])
    |               ^
114 | sheet('阶段安排',['阶段','任务范围','下限人日','上限人日','交付门','外部等待'],[[p,', '.join(x[2]),x[0],x[1],{'M0 基线':'来源盘点、…
115 | sheet('当前能力',['能力','已有实现','缺口','任务','代码证据','本轮状态'],capabilities,{1:22,2:50,3:72,4:22,5:48,6:25},72)
    |

E702 Multiple statements on one line (semicolon)
   --> artifacts/review-20260905/build-workbook.py:113:55
    |
111 | sheet('实施步骤',['ID','任务','修改范围','按顺序实施','验收命令/操作','通过标准','证据目录'],rows,{1:12,2:36,3:70,4:115,5:80,6:75,7:3…
112 | phase=defaultdict(lambda:[0,0,[]])
113 | for t in tasks:phase[t['phase']][0]+=t['estimate_low'];phase[t['phase']][1]+=t['estimate_high'];phase[t['phase']][2].append(t['id'])
    |                                                       ^
114 | sheet('阶段安排',['阶段','任务范围','下限人日','上限人日','交付门','外部等待'],[[p,', '.join(x[2]),x[0],x[1],{'M0 基线':'来源盘点、…
115 | sheet('当前能力',['能力','已有实现','缺口','任务','代码证据','本轮状态'],capabilities,{1:22,2:50,3:72,4:22,5:48,6:25},72)
    |

E702 Multiple statements on one line (semicolon)
   --> artifacts/review-20260905/build-workbook.py:113:96
    |
111 | sheet('实施步骤',['ID','任务','修改范围','按顺序实施','验收命令/操作','通过标准','证据目录'],rows,{1:12,2:36,3:70,4:115,5:80,6:75,7:3…
112 | phase=defaultdict(lambda:[0,0,[]])
113 | for t in tasks:phase[t['phase']][0]+=t['estimate_low'];phase[t['phase']][1]+=t['estimate_high'];phase[t['phase']][2].append(t['id'])
    |                                                                                                ^
114 | sheet('阶段安排',['阶段','任务范围','下限人日','上限人日','交付门','外部等待'],[[p,', '.join(x[2]),x[0],x[1],{'M0 基线':'来源盘点、…
115 | sheet('当前能力',['能力','已有实现','缺口','任务','代码证据','本轮状态'],capabilities,{1:22,2:50,3:72,4:22,5:48,6:25},72)
    |

E501 Line too long (132 > 100)
   --> artifacts/review-20260905/build-workbook.py:113:101
    |
111 | … ','验收命令/操作','通过标准','证据目录'],rows,{1:12,2:36,3:70,4:115,5:80,6:75,7:32},205)
112 | …
113 | …ow'];phase[t['phase']][1]+=t['estimate_high'];phase[t['phase']][2].append(t['id'])
    |                                                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
114 | … 人日','交付门','外部等待'],[[p,', '.join(x[2]),x[0],x[1],{'M0 基线':'来源盘点、设备健康、工程门','M1 来源与内容':'真实库同步+商品…
115 | …'代码证据','本轮状态'],capabilities,{1:22,2:50,3:72,4:22,5:48,6:25},72)
    |

E501 Line too long (485 > 100)
   --> artifacts/review-20260905/build-workbook.py:114:76
    |
112 | …
113 | …;phase[t['phase']][2].append(t['id'])
114 | …2]),x[0],x[1],{'M0 基线':'来源盘点、设备健康、工程门','M1 来源与内容':'真实库同步+商品素材可编辑','M2 发布核心':'冻结快照+互斥+APK收件/媒体授权','M3 闲鱼':'正确预填→一次提交→结果对账','M4 三内容平台':'小红书/抖音/公众号分别验收','M5 完整V1':'四平台批次+恢复+release+8里程碑'}[p],'账号权限/库入口/平台审核按实际等待，未计入人日'] for p,x in phase.items()],{1:24,2:70,3:14,4:14,5:58,6:62},66)
    |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^…^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
115 | …0,3:72,4:22,5:48,6:25},72)
116 | …,4:130,5:45,6:24},190)
    |

E701 Multiple statements on one line (colon)
   --> artifacts/review-20260905/build-workbook.py:120:30
    |
118 | accept=[]
119 | for line in (D/'02-实施方案.md').read_text().splitlines():
120 |  if re.match(r'\| A\d+',line):accept.append([x.strip() for x in line.strip('|').split('|')]+['未执行',''])
    |                              ^
121 | sheet('验收用例',['ID','输入或故障','期望结果','执行状态','证据'],accept,{1:12,2:75,3:90,4:20,5:45},60)
122 | sheet('验证记录',['检查','结果','明细','退出码','日志','限制'],checks,{1:34,2:24,3:45,4:14,5:46,6:85},65)
    |

E501 Line too long (106 > 100)
   --> artifacts/review-20260905/build-workbook.py:120:98
    |
118 | accept=[]
119 | for line in (D/'02-实施方案.md').read_text().splitlines():
120 |  if re.match(r'\| A\d+',line):accept.append([x.strip() for x in line.strip('|').split('|')]+['未执行',''])
    |                                                                                                     ^^^^^^
121 | sheet('验收用例',['ID','输入或故障','期望结果','执行状态','证据'],accept,{1:12,2:75,3:90,4:20,5:45},60)
122 | sheet('验证记录',['检查','结果','明细','退出码','日志','限制'],checks,{1:34,2:24,3:45,4:14,5:46,6:85},65)
    |

E501 Line too long (289 > 100)
   --> artifacts/review-20260905/build-workbook.py:125:77
    |
123 | …:12,2:50,3:20,4:68,5:25,6:24,7:50},65)
124 | …
125 | …x['action'].startswith('remove unused') else '移除孤立mock或旧计划/制表产物',x['sha256'],'artifacts/review-20260905/cleanup-backup.zip 内原相对路径'] for x in cleanup],{1:100,2:48,3:76,4:80},50)
    |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
126 | …
127 | …
    |

E401 [*] Multiple imports on one line
   --> artifacts/review-20260905/build-workbook.py:131:1
    |
129 | wb.save(output)
130 | # Cache these four deterministic overview formulas for read-only spreadsheet previews.
131 | import zipfile,io,xml.etree.ElementTree as ET
    | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
132 | ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
133 | buffer=io.BytesIO()
    |
help: Split imports
    |
130 | # Cache these four deterministic overview formulas for read-only spreadsheet previews.
    - import zipfile,io,xml.etree.ElementTree as ET
131 + import zipfile
132 + import io
133 + import xml.etree.ElementTree as ET
134 | ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    |

E402 Module level import not at top of file
   --> artifacts/review-20260905/build-workbook.py:131:1
    |
129 | wb.save(output)
130 | # Cache these four deterministic overview formulas for read-only spreadsheet previews.
131 | import zipfile,io,xml.etree.ElementTree as ET
    | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
132 | ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
133 | buffer=io.BytesIO()
    |
help: Move module level imports to top of file

I001 [*] Import block is un-sorted or un-formatted
   --> artifacts/review-20260905/build-workbook.py:131:1
    |
129 | wb.save(output)
130 | # Cache these four deterministic overview formulas for read-only spreadsheet previews.
131 | import zipfile,io,xml.etree.ElementTree as ET
    | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
132 | ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
133 | buffer=io.BytesIO()
    |
help: Organize imports
    |
130 | # Cache these four deterministic overview formulas for read-only spreadsheet previews.
    - import zipfile,io,xml.etree.ElementTree as ET
131 + import io
132 + import xml.etree.ElementTree as ET
133 + import zipfile
134 +
135 | ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    |

S314 Using `xml` to parse untrusted data is known to be vulnerable to XML attacks; use `defusedxml` equivalents
   --> artifacts/review-20260905/build-workbook.py:138:9
    |
136 |   data=zin.read(info.filename)
137 |   if info.filename=='xl/worksheets/sheet1.xml':
138 |    tree=ET.fromstring(data)
    |         ^^^^^^^^^^^^^^^^^^^
139 |    done=sum(t['status']=='done' for t in tasks)
140 |    values={'B5':done,'B6':done/len(tasks),'B7':sum(t['estimate_low'] for t in tasks),'B8':sum(t['estimate_high'] for t in tasks)}
    |

E501 Line too long (129 > 100)
   --> artifacts/review-20260905/build-workbook.py:140:101
    |
138 |    tree=ET.fromstring(data)
139 |    done=sum(t['status']=='done' for t in tasks)
140 |    values={'B5':done,'B6':done/len(tasks),'B7':sum(t['estimate_low'] for t in tasks),'B8':sum(t['estimate_high'] for t in tasks)}
    |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
141 |    for cell in tree.findall('.//m:c',ns):
142 |     if cell.attrib.get('r') in values:
    |

E701 Multiple statements on one line (colon)
   --> artifacts/review-20260905/build-workbook.py:144:18
    |
142 |     if cell.attrib.get('r') in values:
143 |      v=cell.find('m:v',ns)
144 |      if v is None:v=ET.SubElement(cell,'{'+ns['m']+'}v')
    |                  ^
145 |      v.text=str(values[cell.attrib['r']])
146 |    data=ET.tostring(tree,encoding='utf-8')
    |

E501 Line too long (322 > 100)
   --> artifacts/review-20260905/build-workbook.py:166:101
    |
164 | …
165 | …
166 | …s':12,'acceptanceCases':18,'estimatePersonDays':[45,84],'formulaReferences':'validated; recalculates on opening in spreadsheet application','sha256':hashlib.sha256(output.read_bytes()).hexdigest()},ensure_ascii=False,indent=2))
    |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
167 | …
168 | …days.')
    |

E501 Line too long (102 > 100)
   --> artifacts/review-20260905/build-workbook.py:168:101
    |
166 | (A/'workbook-validation.json').write_text(json.dumps({'sheets':r.sheetnames,'tasks':30,'findings':12,'acceptanceCases':18,'estimatePe…
167 | print(output)
168 | print('Validated 11 sheets, 30 tasks, 12 findings, 18 acceptance cases; estimates 45–84 person-days.')
    |                                                                                                     ^^

I001 [*] Import block is un-sorted or un-formatted
  --> scripts/benchmark_media_references.py:3:1
   |
 1 |   """Repeatable local SQLite API benchmark; not a production capacity claim."""
 2 |
 3 | / from __future__ import annotations
 4 | |
 5 | | import asyncio
 6 | | import json
 7 | | import math
 8 | | import platform
 9 | | import statistics
10 | | import tempfile
11 | | from datetime import UTC, datetime
12 | | from pathlib import Path
13 | | from time import perf_counter
14 | |
15 | | import httpx
16 | | from cloudctl_api.app import create_app
17 | | from cloudctl_api.db import ContentItemRow, ContentRevisionMediaRow, ContentRevisionRow, MediaAssetRow
18 | | from cloudctl_api.settings import Settings
19 | | from sqlalchemy import insert, text
   | |___________________________________^
20 |
21 |   TENANT = "00000000-0000-7000-8000-000000000111"
   |
help: Organize imports
   |
16 | from cloudctl_api.app import create_app
   - from cloudctl_api.db import ContentItemRow, ContentRevisionMediaRow, ContentRevisionRow, MediaAssetRow
17 + from cloudctl_api.db import (
18 +     ContentItemRow,
19 +     ContentRevisionMediaRow,
20 +     ContentRevisionRow,
21 +     MediaAssetRow,
22 + )
23 | from cloudctl_api.settings import Settings
   |

E501 Line too long (102 > 100)
  --> scripts/benchmark_media_references.py:17:101
   |
15 | import httpx
16 | from cloudctl_api.app import create_app
17 | from cloudctl_api.db import ContentItemRow, ContentRevisionMediaRow, ContentRevisionRow, MediaAssetRow
   |                                                                                                     ^^
18 | from cloudctl_api.settings import Settings
19 | from sqlalchemy import insert, text
   |

E501 Line too long (114 > 100)
  --> scripts/benchmark_media_references.py:48:101
   |
46 |                     await session.execute(insert(ContentRevisionRow), [
47 |                         dict(id=f"revision-{i:08}", tenant_id=TENANT, content_id="content",
48 |                              revision_no=i + 1, payload={"mediaAssetIds": ["target" if i < matches else "other"]},
   |                                                                                                     ^^^^^^^^^^^^^^
49 |                              payload_sha256="c" * 64, created_by=USER, created_at=now)
50 |                         for i in indexes
   |

E501 Line too long (103 > 100)
  --> scripts/benchmark_media_references.py:65:101
   |
63 |                 ), {"tenant": TENANT, "asset": "target"})]
64 |                 version = await connection.scalar(text("SELECT sqlite_version()"))
65 |             headers = {"X-Tenant-Id": TENANT, "X-User-Id": USER, "X-Roles": "viewer", "X-MFA": "false"}
   |                                                                                                     ^^^
66 |             timings = []
67 |             async with httpx.AsyncClient(
   |

E501 Line too long (101 > 100)
  --> scripts/benchmark_media_references.py:68:101
   |
66 |             timings = []
67 |             async with httpx.AsyncClient(
68 |                 transport=httpx.ASGITransport(app=app), base_url="http://benchmark", trust_env=False,
   |                                                                                                     ^
69 |             ) as client:
70 |                 for iteration in range(35):
   |

E501 Line too long (106 > 100)
  --> scripts/benchmark_media_references.py:72:101
   |
70 |                 for iteration in range(35):
71 |                     start = perf_counter()
72 |                     response = await client.get("/api/v1/media/assets/target/references", headers=headers)
   |                                                                                                     ^^^^^^
73 |                     elapsed = (perf_counter() - start) * 1000
74 |                     response.raise_for_status()
   |

E501 Line too long (118 > 100)
   --> scripts/validate-demo-sources.py:105:101
    |
104 |     print(f"  ✓ {len(rows)} products validated")
105 |     print(f"  ✓ Price range: {min(Decimal(r['price']) for r in rows)} - {max(Decimal(r['price']) for r in rows)} CNY")
    |                                                                                                     ^^^^^^^^^^^^^^^^^^
106 |     
107 |     return rows
    |

E501 Line too long (101 > 100)
   --> services/control-api/src/cloudctl_api/schemas.py:166:101
    |
164 |     category: str | None = Field(default=None, max_length=160)
165 |     group_id: str | None = Field(default=None, alias="groupId")
166 |     min_price: str | None = Field(default=None, alias="minPrice", pattern=r"^[0-9]+(\.[0-9]{1,2})?$")
    |                                                                                                     ^
167 |     max_price: str | None = Field(default=None, alias="maxPrice", pattern=r"^[0-9]+(\.[0-9]{1,2})?$")
168 |     status: Literal["ACTIVE", "ARCHIVED", "ALL"] | None = Field(default="ACTIVE")
    |

E501 Line too long (101 > 100)
   --> services/control-api/src/cloudctl_api/schemas.py:167:101
    |
165 |     group_id: str | None = Field(default=None, alias="groupId")
166 |     min_price: str | None = Field(default=None, alias="minPrice", pattern=r"^[0-9]+(\.[0-9]{1,2})?$")
167 |     max_price: str | None = Field(default=None, alias="maxPrice", pattern=r"^[0-9]+(\.[0-9]{1,2})?$")
    |                                                                                                     ^
168 |     status: Literal["ACTIVE", "ARCHIVED", "ALL"] | None = Field(default="ACTIVE")
    |

E501 Line too long (114 > 100)
  --> services/control-api/src/cloudctl_api/xianyu_publish.py:39:101
   |
39 | def build_text_publish_steps(*, description: str, price: str, auto_publish: bool = False) -> list[dict[str, Any]]:
   |                                                                                                     ^^^^^^^^^^^^^^
40 |     """Return allowlisted steps that fill the idlefish publish form.
   |

E501 Line too long (101 > 100)
   --> services/control-api/src/cloudctl_api/xianyu_publish.py:201:101
    |
199 |             raise ValueError("delivery_id is required when media assets are supplied")
200 |     
201 |     steps = build_text_publish_steps(description=description, price=price, auto_publish=auto_publish)
    |                                                                                                     ^
202 |     
203 |     # Insert media upload steps after opening publish page (before filling description)
    |

Found 133 errors.
[*] 8 fixable with the `--fix` option (1 hidden fix can be enabled with the `--unsafe-fixes` option).
```
退出码: 1

#### pyright类型检查
```
0 errors, 0 warnings, 0 informations
```
退出码: 0

#### mypy类型检查
```
packages/edge-protocol/src/cloudctl_edge_protocol/edge_control_pb2.pyi:35: error: Missing type arguments for generic type "Mapping"  [type-arg]
packages/edge-protocol/src/cloudctl_edge_protocol/edge_control_pb2.pyi:57: error: Missing type arguments for generic type "Mapping"  [type-arg]
packages/edge-protocol/src/cloudctl_edge_protocol/edge_control_pb2.pyi:83: error: Missing type arguments for generic type "Mapping"  [type-arg]
packages/edge-protocol/src/cloudctl_edge_protocol/edge_control_pb2.pyi:124: error: Missing type arguments for generic type "Mapping"  [type-arg]
packages/edge-protocol/src/cloudctl_edge_protocol/edge_control_pb2.pyi:146: error: Missing type arguments for generic type "Mapping"  [type-arg]
packages/edge-protocol/src/cloudctl_edge_protocol/edge_control_pb2.pyi:202: error: Missing type arguments for generic type "Mapping"  [type-arg]
packages/edge-protocol/src/cloudctl_edge_protocol/edge_control_pb2.pyi:236: error: Missing type arguments for generic type "Mapping"  [type-arg]
packages/edge-protocol/src/cloudctl_edge_protocol/edge_control_pb2.pyi:252: error: Missing type arguments for generic type "Mapping"  [type-arg]
packages/edge-protocol/src/cloudctl_edge_protocol/edge_control_pb2.pyi:272: error: Missing type arguments for generic type "Mapping"  [type-arg]
packages/edge-protocol/src/cloudctl_edge_protocol/edge_control_pb2.pyi:290: error: Missing type arguments for generic type "Mapping"  [type-arg]
packages/edge-protocol/src/cloudctl_edge_protocol/edge_control_pb2.pyi:310: error: Missing type arguments for generic type "Mapping"  [type-arg]
packages/edge-protocol/src/cloudctl_edge_protocol/edge_control_pb2.pyi:336: error: Missing type arguments for generic type "Mapping"  [type-arg]
services/outbox-dispatcher/src/cloudctl_outbox/debug_grpc_sink.py:59: error: Unused "type: ignore" comment  [unused-ignore]
services/edge-hub/src/cloudctl_edge_hub/grpc_service.py:16: error: Function is missing a type annotation for one or more parameters  [no-untyped-def]
services/edge-hub/src/cloudctl_edge_hub/sqlite_debug_store.py:79: error: Returning Any from function declared to return "tuple[object, ...] | None"  [no-any-return]
services/edge-hub/src/cloudctl_edge_hub/sqlite_debug_store.py:118: error: Returning Any from function declared to return "tuple[object, ...] | None"  [no-any-return]
services/edge-hub/src/cloudctl_edge_hub/sqlite_debug_store.py:138: error: Unused "type: ignore" comment  [unused-ignore]
services/edge-hub/src/cloudctl_edge_hub/sqlite_debug_store.py:144: error: Unused "type: ignore" comment  [unused-ignore]
services/edge-hub/src/cloudctl_edge_hub/debug_relay.py:468: error: Unused "type: ignore" comment  [unused-ignore]
services/control-api/src/cloudctl_api/source_service.py:262: error: Returning Any from function declared to return "str"  [no-any-return]
services/control-api/src/cloudctl_api/source_service.py:264: error: Returning Any from function declared to return "str"  [no-any-return]
services/control-api/src/cloudctl_api/source_service.py:673: error: Returning Any from function declared to return "str"  [no-any-return]
services/control-api/src/cloudctl_api/source_service.py:709: error: Returning Any from function declared to return "str"  [no-any-return]
services/control-api/src/cloudctl_api/mobile_service.py:737: error: Returning Any from function declared to return "DevicePreviewRow"  [no-any-return]
services/control-api/src/cloudctl_api/services.py:625: error: Incompatible types in assignment (expression has type "MediaGroupMembershipRow", variable has type "MediaTagRow")  [assignment]
services/control-api/src/cloudctl_api/services.py:626: error: "MediaTagRow" has no attribute "group_id"  [attr-defined]
services/control-api/src/cloudctl_api/services.py:629: error: Incompatible types in assignment (expression has type "dict[str, Any]", variable has type "MediaTagRow")  [assignment]
services/control-api/src/cloudctl_api/services.py:630: error: Unsupported target for indexed assignment ("MediaTagRow")  [index]
services/control-api/src/cloudctl_api/services.py:631: error: Unsupported target for indexed assignment ("MediaTagRow")  [index]
services/outbox-dispatcher/src/cloudctl_outbox/main.py:34: error: Argument 1 to "FanoutSink" has incompatible type "*list[object]"; expected "EventSink"  [arg-type]
services/control-api/src/cloudctl_api/source_routes.py:221: error: Incompatible types in assignment (expression has type "Select[tuple[SyncRunRow]]", variable has type "Select[tuple[SourceConnectionRow]]")  [assignment]
services/control-api/src/cloudctl_api/source_routes.py:228: error: "SourceConnectionRow" has no attribute "connection_id"; maybe "connection_name"?  [attr-defined]
services/control-api/src/cloudctl_api/source_routes.py:229: error: "SourceConnectionRow" has no attribute "run_mode"  [attr-defined]
services/control-api/src/cloudctl_api/source_routes.py:231: error: "SourceConnectionRow" has no attribute "started_at"  [attr-defined]
services/control-api/src/cloudctl_api/source_routes.py:232: error: "SourceConnectionRow" has no attribute "completed_at"  [attr-defined]
services/control-api/src/cloudctl_api/source_routes.py:233: error: "SourceConnectionRow" has no attribute "cursor_before"  [attr-defined]
services/control-api/src/cloudctl_api/source_routes.py:234: error: "SourceConnectionRow" has no attribute "cursor_after"  [attr-defined]
services/control-api/src/cloudctl_api/source_routes.py:235: error: "SourceConnectionRow" has no attribute "records_read"  [attr-defined]
services/control-api/src/cloudctl_api/source_routes.py:236: error: "SourceConnectionRow" has no attribute "records_created"  [attr-defined]
services/control-api/src/cloudctl_api/source_routes.py:237: error: "SourceConnectionRow" has no attribute "records_updated"  [attr-defined]
services/control-api/src/cloudctl_api/source_routes.py:238: error: "SourceConnectionRow" has no attribute "records_failed"  [attr-defined]
services/control-api/src/cloudctl_api/source_routes.py:239: error: "SourceConnectionRow" has no attribute "error_summary"  [attr-defined]
Found 42 errors in 10 files (checked 112 source files)
```
退出码: 1

#### pytest单元测试
```
F....................................................................... [ 17%]
........................................................................ [ 34%]
...........F............................................................ [ 52%]
........................................................................ [ 69%]
........................................................................ [ 87%]
.....................................................                    [100%]
=================================== FAILURES ===================================
__________________ test_committed_openapi_matches_application __________________

    def test_committed_openapi_matches_application() -> None:
        expected = create_app(
            Settings(env="test", repository_mode="memory", dev_auth_bypass=True)
        ).openapi()
        committed = json.loads(Path("packages/api-contracts/openapi.json").read_text(encoding="utf-8"))
>       assert committed == expected
E       AssertionError: assert {'components'..., ...}}, ...}} == {'openapi': '...eate'}, ...}}}
E         
E         Omitting 2 identical items, use -vv to show
E         Differing items:
E         {'components': {'schemas': {'AccountDeviceBind': {'properties': {'confirmationNote': {'maxLength': 1000, 'minLength': ...versionName', 'versionCode', 'signatureDigest', 'minSdk', ...], 'title': 'ApkArtifactCreate', 'type': 'object'}, ...}}} != {'components': {'schemas': {'AccountDeviceBind': {'properties': {'deviceId': {'type': 'string', 'maxLength': 36, 'minL..., 'packageName', 'versionName', 'versionCode', 'signatureDigest', 'minSdk', ...], 'title': 'ApkArtifactCreate'}, ...}}}
E         {'paths': {'/api/v1/accounts': {'...
E         
E         ...Full output truncated (2 lines hidden), use '-vv' to show

tests/contracts/test_openapi_contract.py:15: AssertionError
___________ test_xianyu_text_publish_task_is_accepted_and_claimable ____________

api = (<httpx.AsyncClient object at 0x118c89fd0>, <fastapi.applications.FastAPI object at 0x118825810>)

    @pytest.mark.asyncio
    async def test_xianyu_text_publish_task_is_accepted_and_claimable(
        api: tuple[httpx.AsyncClient, FastAPI],
    ) -> None:
        client, _ = api
        device_id = await create_direct_device(client)
        token = await enroll(client, device_id)
        body = build_text_publish_task(
            device_id,
            description="自用闲置，功能正常，支持当面交易",
            price="128",
        )
        created = await create_task(client, device_id, key="xianyu-text-publish", body=body)
        assert created.status_code == 201, created.text
        assert created.json()["targetPackage"] == XIANYU_PACKAGE
>       assert [step["stepId"] for step in created.json()["steps"]] == [
            "find-home-sell",
            "open-sell",
            "open-publish",
            "wait-publish-page",
            "fill-description",
            "fill-price",
            "capture-form",
            "mark-ready",
        ]
E       AssertionError: assert ['find-home-s...l-price', ...] == ['find-home-s...l-price', ...]
E         
E         At index 7 diff: 'click-publish' != 'mark-ready'
E         Left contains 3 more items, first extra item: 'wait-publish-complete'
E         Use -v to get more diff

tests/integration/test_mobile_task_api.py:653: AssertionError
=========================== short test summary info ============================
FAILED tests/contracts/test_openapi_contract.py::test_committed_openapi_matches_application
FAILED tests/integration/test_mobile_task_api.py::test_xianyu_text_publish_task_is_accepted_and_claimable
2 failed, 411 passed in 15.20s
```
退出码: 1


### 步骤6: 前端代码质量检查

#### pnpm lint
```

> cloudctl@0.1.0 lint /Users/wangziheng/Desktop/LAMDA云控系统_代码交接包_20260901/cloudctl-source
> pnpm --recursive --if-present lint

Scope: 3 of 4 workspace projects
packages/api-contracts/typescript lint$ tsc -p tsconfig.json --noEmit
packages/api-contracts/typescript lint: src/client.ts(241,33): error TS2304: Cannot find name 'ProductBatchUpdatePrice'.
packages/api-contracts/typescript lint: src/client.ts(245,33): error TS2304: Cannot find name 'ProductBatchUpdateGroup'.
packages/api-contracts/typescript lint: src/client.ts(249,29): error TS2304: Cannot find name 'ProductBatchDelete'.
packages/api-contracts/typescript lint: src/client.ts(253,24): error TS2304: Cannot find name 'ProductImportRequest'.
packages/api-contracts/typescript lint: src/client.ts(257,24): error TS2304: Cannot find name 'ProductFilterRequest'.
packages/api-contracts/typescript lint: Failed
/Users/wangziheng/Desktop/LAMDA云控系统_代码交接包_20260901/cloudctl-source/packages/api-contracts/typescript:
 ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL  @cloudctl/api-contracts@0.1.0 lint: `tsc -p tsconfig.json --noEmit`
Exit status 2
 ELIFECYCLE  Command failed with exit code 2.
```
退出码: 2

#### pnpm typecheck
```

> cloudctl@0.1.0 typecheck /Users/wangziheng/Desktop/LAMDA云控系统_代码交接包_20260901/cloudctl-source
> pnpm --recursive --if-present typecheck

Scope: 3 of 4 workspace projects
packages/api-contracts/typescript typecheck$ tsc -p tsconfig.json --noEmit
packages/api-contracts/typescript typecheck: src/client.ts(241,33): error TS2304: Cannot find name 'ProductBatchUpdatePrice'.
packages/api-contracts/typescript typecheck: src/client.ts(245,33): error TS2304: Cannot find name 'ProductBatchUpdateGroup'.
packages/api-contracts/typescript typecheck: src/client.ts(249,29): error TS2304: Cannot find name 'ProductBatchDelete'.
packages/api-contracts/typescript typecheck: src/client.ts(253,24): error TS2304: Cannot find name 'ProductImportRequest'.
packages/api-contracts/typescript typecheck: src/client.ts(257,24): error TS2304: Cannot find name 'ProductFilterRequest'.
packages/api-contracts/typescript typecheck: Failed
/Users/wangziheng/Desktop/LAMDA云控系统_代码交接包_20260901/cloudctl-source/packages/api-contracts/typescript:
 ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL  @cloudctl/api-contracts@0.1.0 typecheck: `tsc -p tsconfig.json --noEmit`
Exit status 2
 ELIFECYCLE  Command failed with exit code 2.
```
退出码: 2

#### pnpm test
```

> cloudctl@0.1.0 test /Users/wangziheng/Desktop/LAMDA云控系统_代码交接包_20260901/cloudctl-source
> pnpm --recursive --if-present test

Scope: 3 of 4 workspace projects
packages/api-contracts/typescript test$ tsc -p tsconfig.json --noEmit
packages/api-contracts/typescript test: src/client.ts(241,33): error TS2304: Cannot find name 'ProductBatchUpdatePrice'.
packages/api-contracts/typescript test: src/client.ts(245,33): error TS2304: Cannot find name 'ProductBatchUpdateGroup'.
packages/api-contracts/typescript test: src/client.ts(249,29): error TS2304: Cannot find name 'ProductBatchDelete'.
packages/api-contracts/typescript test: src/client.ts(253,24): error TS2304: Cannot find name 'ProductImportRequest'.
packages/api-contracts/typescript test: src/client.ts(257,24): error TS2304: Cannot find name 'ProductFilterRequest'.
packages/api-contracts/typescript test: Failed
/Users/wangziheng/Desktop/LAMDA云控系统_代码交接包_20260901/cloudctl-source/packages/api-contracts/typescript:
 ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL  @cloudctl/api-contracts@0.1.0 test: `tsc -p tsconfig.json --noEmit`
Exit status 2
 ELIFECYCLE  Test failed. See above for more details.
```
退出码: 2

#### pnpm build
```

> cloudctl@0.1.0 build /Users/wangziheng/Desktop/LAMDA云控系统_代码交接包_20260901/cloudctl-source
> pnpm --recursive --if-present build

Scope: 3 of 4 workspace projects
packages/api-contracts/typescript build$ tsc -p tsconfig.json
packages/api-contracts/typescript build: src/client.ts(241,33): error TS2304: Cannot find name 'ProductBatchUpdatePrice'.
packages/api-contracts/typescript build: src/client.ts(245,33): error TS2304: Cannot find name 'ProductBatchUpdateGroup'.
packages/api-contracts/typescript build: src/client.ts(249,29): error TS2304: Cannot find name 'ProductBatchDelete'.
packages/api-contracts/typescript build: src/client.ts(253,24): error TS2304: Cannot find name 'ProductImportRequest'.
packages/api-contracts/typescript build: src/client.ts(257,24): error TS2304: Cannot find name 'ProductFilterRequest'.
packages/api-contracts/typescript build: Failed
/Users/wangziheng/Desktop/LAMDA云控系统_代码交接包_20260901/cloudctl-source/packages/api-contracts/typescript:
 ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL  @cloudctl/api-contracts@0.1.0 build: `tsc -p tsconfig.json`
Exit status 2
 ELIFECYCLE  Command failed with exit code 2.
```
退出码: 2


### 步骤7: Android构建检查

#### Android Companion - test
```
Starting a Gradle Daemon (subsequent builds will be faster)
> Task :app:checkKotlinGradlePluginConfigurationErrors SKIPPED
> Task :app:preBuild UP-TO-DATE
> Task :app:preDebugBuild UP-TO-DATE
> Task :app:generateDebugBuildConfig UP-TO-DATE
> Task :app:checkDebugAarMetadata UP-TO-DATE
> Task :app:generateDebugResValues UP-TO-DATE
> Task :app:mapDebugSourceSetPaths UP-TO-DATE
> Task :app:generateDebugResources UP-TO-DATE
> Task :app:mergeDebugResources UP-TO-DATE
> Task :app:packageDebugResources UP-TO-DATE
> Task :app:parseDebugLocalResources UP-TO-DATE
> Task :app:createDebugCompatibleScreenManifests UP-TO-DATE
> Task :app:extractDeepLinksDebug UP-TO-DATE
> Task :app:processDebugMainManifest UP-TO-DATE
> Task :app:processDebugManifest UP-TO-DATE
> Task :app:processDebugManifestForPackage UP-TO-DATE
> Task :app:processDebugResources UP-TO-DATE
> Task :app:compileDebugKotlin UP-TO-DATE
> Task :app:javaPreCompileDebug UP-TO-DATE
> Task :app:compileDebugJavaWithJavac UP-TO-DATE
> Task :app:preDebugUnitTestBuild UP-TO-DATE
> Task :app:mergeDebugShaders UP-TO-DATE
> Task :app:compileDebugShaders NO-SOURCE
> Task :app:generateDebugAssets UP-TO-DATE
> Task :app:javaPreCompileDebugUnitTest
> Task :app:mergeDebugAssets UP-TO-DATE
> Task :app:bundleDebugClassesToCompileJar
> Task :app:bundleDebugClassesToRuntimeJar
> Task :app:packageDebugUnitTestForUnitTest
> Task :app:generateDebugUnitTestConfig
> Task :app:processDebugJavaRes UP-TO-DATE
> Task :app:buildKotlinToolingMetadata
> Task :app:verifyReleaseUpdatePublicKey FAILED
> Task :app:compileDebugUnitTestKotlin

FAILURE: Build failed with an exception.

* What went wrong:
Execution failed for task ':app:verifyReleaseUpdatePublicKey'.
> Set CLOUDCTL_APP_UPDATE_PUBLIC_KEY or -Pcloudctl.appUpdatePublicKey for release.

* Try:
> Run with --stacktrace option to get the stack trace.
> Run with --info or --debug option to get more log output.
> Run with --scan to get full insights.
> Get more help at https://help.gradle.org.

BUILD FAILED in 39s
28 actionable tasks: 8 executed, 20 up-to-date
```
退出码: 1

#### Android Companion - lint
```
> Task :app:checkKotlinGradlePluginConfigurationErrors SKIPPED
> Task :app:preBuild UP-TO-DATE
> Task :app:preDebugBuild UP-TO-DATE
> Task :app:generateDebugBuildConfig UP-TO-DATE
> Task :app:checkDebugAarMetadata UP-TO-DATE
> Task :app:generateDebugResValues UP-TO-DATE
> Task :app:mapDebugSourceSetPaths UP-TO-DATE
> Task :app:generateDebugResources UP-TO-DATE
> Task :app:mergeDebugResources UP-TO-DATE
> Task :app:packageDebugResources UP-TO-DATE
> Task :app:parseDebugLocalResources UP-TO-DATE
> Task :app:createDebugCompatibleScreenManifests UP-TO-DATE
> Task :app:extractDeepLinksDebug UP-TO-DATE
> Task :app:processDebugMainManifest UP-TO-DATE
> Task :app:processDebugManifest UP-TO-DATE
> Task :app:processDebugManifestForPackage UP-TO-DATE
> Task :app:processDebugResources UP-TO-DATE
> Task :app:compileDebugKotlin UP-TO-DATE
> Task :app:javaPreCompileDebug UP-TO-DATE
> Task :app:compileDebugJavaWithJavac UP-TO-DATE
> Task :app:bundleDebugClassesToCompileJar UP-TO-DATE
> Task :app:preDebugAndroidTestBuild SKIPPED
> Task :app:generateDebugAndroidTestResValues
> Task :app:generateDebugAndroidTestLintModel
> Task :app:extractProguardFiles
> Task :app:generateDebugLintReportModel
> Task :app:preDebugUnitTestBuild UP-TO-DATE
> Task :app:generateDebugUnitTestLintModel
> Task :app:lintAnalyzeDebugAndroidTest
> Task :app:lintAnalyzeDebugUnitTest
> Task :app:lintAnalyzeDebug

> Task :app:lintReportDebug
Wrote HTML report to file:///Users/wangziheng/Desktop/LAMDA云控系统_代码交接包_20260901/cloudctl-source/mobile/companion/app/build/reports/lint-results-debug.html

> Task :app:lintDebug
> Task :app:lint

BUILD SUCCESSFUL in 1m 36s
28 actionable tasks: 10 executed, 18 up-to-date
```
退出码: 0

#### Android Companion - assembleDebug
```
> Task :app:preBuild UP-TO-DATE
> Task :app:preDebugBuild UP-TO-DATE
> Task :app:mergeDebugNativeDebugMetadata NO-SOURCE
> Task :app:checkKotlinGradlePluginConfigurationErrors SKIPPED
> Task :app:generateDebugBuildConfig UP-TO-DATE
> Task :app:checkDebugAarMetadata UP-TO-DATE
> Task :app:generateDebugResValues UP-TO-DATE
> Task :app:mapDebugSourceSetPaths UP-TO-DATE
> Task :app:generateDebugResources UP-TO-DATE
> Task :app:mergeDebugResources UP-TO-DATE
> Task :app:packageDebugResources UP-TO-DATE
> Task :app:parseDebugLocalResources UP-TO-DATE
> Task :app:createDebugCompatibleScreenManifests UP-TO-DATE
> Task :app:extractDeepLinksDebug UP-TO-DATE
> Task :app:processDebugMainManifest UP-TO-DATE
> Task :app:processDebugManifest UP-TO-DATE
> Task :app:processDebugManifestForPackage UP-TO-DATE
> Task :app:processDebugResources UP-TO-DATE
> Task :app:compileDebugKotlin UP-TO-DATE
> Task :app:javaPreCompileDebug UP-TO-DATE
> Task :app:compileDebugJavaWithJavac UP-TO-DATE
> Task :app:mergeDebugShaders UP-TO-DATE
> Task :app:compileDebugShaders NO-SOURCE
> Task :app:generateDebugAssets UP-TO-DATE
> Task :app:mergeDebugAssets UP-TO-DATE
> Task :app:compressDebugAssets UP-TO-DATE
> Task :app:desugarDebugFileDependencies UP-TO-DATE
> Task :app:dexBuilderDebug UP-TO-DATE
> Task :app:mergeDebugGlobalSynthetics UP-TO-DATE
> Task :app:processDebugJavaRes UP-TO-DATE
> Task :app:mergeDebugJavaResource UP-TO-DATE
> Task :app:checkDebugDuplicateClasses UP-TO-DATE
> Task :app:mergeExtDexDebug UP-TO-DATE
> Task :app:mergeLibDexDebug UP-TO-DATE
> Task :app:mergeProjectDexDebug UP-TO-DATE
> Task :app:mergeDebugJniLibFolders UP-TO-DATE
> Task :app:mergeDebugNativeLibs UP-TO-DATE
> Task :app:stripDebugDebugSymbols UP-TO-DATE
> Task :app:validateSigningDebug UP-TO-DATE
> Task :app:writeDebugAppMetadata UP-TO-DATE
> Task :app:writeDebugSigningConfigVersions UP-TO-DATE
> Task :app:packageDebug UP-TO-DATE
> Task :app:createDebugApkListingFileRedirect UP-TO-DATE
> Task :app:assembleDebug UP-TO-DATE

BUILD SUCCESSFUL in 1s
37 actionable tasks: 37 up-to-date
```
退出码: 0


## 总结

### 环境配置完整性
- [x] Git commit已锁定并验证
- [x] Python、Node、pnpm、Java环境已检查
- [x] Python依赖已安装
- [x] Node依赖已安装

### 代码质量检查结果
详见上方各工具的退出码。

### 阻塞项

测试完成时间: Sun Sep  6 20:27:10 CST 2026
