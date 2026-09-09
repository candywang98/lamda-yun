# 一期多智能体并行执行协议

版本：2026-09-09  
适用范围：开发 Worker 调用编码/审阅子智能体；不适用于生产业务 Temporal Worker。

## 1. 已核实边界

- 当前 `services/temporal-worker` 负责发布业务工作流，不包含 LLM、Agent SDK、提示词或子智能体创建接口。
- 业务 Parent Workflow 目前在循环内直接等待每个 Child Workflow，因此目标发布是串行执行；这与“编码智能体并行”是两套问题。
- 编码智能体编排放在外部开发 Worker 层。生产 Worker 不获得模型凭据，也不直接接入开发 Agent。
- 当前 Git 只有一个 worktree，且工作区存在大量未提交实现与证据。形成共同基线前，只允许并行只读分析，不允许多个子智能体在同一目录并发写入。

## 2. 拓扑

```text
Root Worker / Controller
├─ Agent A: Control API / data / migration owner
├─ Agent B: Android / Companion owner
└─ Agent C: Web owner

Controller 串行持有：contract、merge、device、deploy、release、G3 side-effect 锁
```

控制器保留一个槽位做 DAG、锁、合并和证据管理；默认同时运行三个施工子智能体。三个子智能体必须先全部创建，再统一等待结果，禁止“创建 A→等待 A→创建 B”的伪并行。

伪代码：

```text
ready = select_maximal_ready_set(capacity=3)
handles = []
for item in ready:
    handles.append(spawn_subagent(item.card))
results = wait_all(handles)
for result in results:
    validate_scope_tests_evidence(result)
enqueue_controlled_merge(results)
```

如果执行环境没有真实子智能体能力，控制器必须报告 `SUBAGENT_CAPABILITY_UNAVAILABLE`，不能把普通函数调用或 Temporal Child Workflow 冒充子智能体。

## 3. READY 与非串行调度

一个检查点只有同时满足以下条件才进入 READY：

```text
MUST 接口/fixture 已冻结
AND owned_paths 与运行中任务不相交
AND 所需资源锁可获得
AND 没有待裁决的共享契约问题
AND 验证命令、完成标准、证据目录已声明
```

`INTEG` 关系只阻止最终跨端验收，不阻止使用冻结 fixture 的独立开发。某个任务进入 `WAIT_LOCK`、`WAIT_AUTH` 或 `WAIT_HARDWARE` 后，空出的子智能体槽位立即从 READY 池选择其他无冲突工作，不等待整个功能包。

调度状态：

- `READY`：可立即派发。
- `RUNNING`：子智能体施工中。
- `WAIT_CONTRACT`：等待共享契约裁决。
- `WAIT_LOCK`：等待迁移、设备、部署或发布锁。
- `VERIFY`：独立测试完成，等待控制器检查。
- `MERGE`：进入受控合并队列。
- `INTEGRATED`：同一集成 SHA 上通过跨端测试。
- `ACCEPTED`：真实验收满足；软件测试不能自动变为该状态。

## 4. 工作区与分支

正式启用三个写入子智能体前，控制器短暂串行完成：

1. 审核当前脏工作区，区分源码、测试、必要摘要与缓存/二进制/运行数据。
2. 建立可恢复的本地集成基线提交；不得盲目 `git add -A`。
3. 从同一基线 SHA 创建独立工作树：
   - `agent/p14-api-version-pin`
   - `agent/p14-android-lifecycle`
   - `agent/p14-web-t041`
   - 集成分支 `integration/p14-20260909`
4. 为各 worktree 配置独立测试数据库、端口和构建缓存，避免测试互相污染。

没有共同基线时，三个 Agent 会从旧提交重复开发，或在共享目录覆盖现有实现，因此该短暂冻结是并行成立的前提，不是把整个任务重新串行化。

## 5. 路径所有权

| 角色 | 独占写集 | 只读依赖 | 禁止写入 |
| --- | --- | --- | --- |
| P14-CONTROL | `services/control-api/**`、相关后端测试、唯一迁移 | `contracts/phase1/**`、Android/Web 调用方 | Web、Android、生成的 OpenAPI 客户端 |
| P14-ANDROID | `mobile/companion/**` 及直接测试 | 冻结的 Recipe/Command fixture | 后端、迁移、Web |
| P14-WEB | `apps/web/**` 及页面测试 | 冻结的 API fixture | 后端、Android、迁移、生成的 OpenAPI 客户端 |
| Root Worker | 计划书、共享契约裁决、生成客户端、最终 evidence | 三个分支 | 不代替所有者并发重写其实现 |

任何子智能体发现需要越界修改，状态改为 `WAIT_CONTRACT` 并提交变更请求；不得“顺手”修改另一个 Agent 的文件。

## 6. 资源锁

| 锁 | 持有者 | 作用 |
| --- | --- | --- |
| `CONTRACT:recipe-version` | Root Worker | versionId/hash、部署和回退语义 |
| `DB_MIGRATION` | P14-CONTROL，经 Root 授权 | 唯一迁移序列、升降级 |
| `MERGE:integration` | Root Worker | 受控合并与生成合同 |
| `DEVICE:b0644fb5` | Root/验收者 | OnePlus 安装、claim、暂停/恢复、激活、回退 |
| `DEPLOY:seoul` | Root/验收者 | 首尔服务部署与重启 |
| `RELEASE:P14` | 用户 + Root | Recipe 人工发布、撤销、回退 |
| `SIDE_EFFECT:G3` | 用户 + Root | 真实发布、扣费、删除、评价、推广 |

锁只串行化受保护动作。等待设备或用户授权时，Web、后端、Android 软件工作和其他 READY 包继续运行。

## 7. P14 当前三路并行

### P14-WEB / T041

- 目标：自动化版本管理页；展示候选版本、签名/兼容性、设备部署状态、操作者与时间；只能由用户显式点击发布/回退。
- 不占用真机，不接触签名私钥，不自行改变 API schema。
- 独立完成：页面单测、权限/失败显示和构建通过。

### P14-CONTROL / T040/T042 服务端部分

- 目标：任务首次 claim 原子固定 `recipeVersionId`、`recipeSha256`、deployment/attempt；暂停和恢复继续读取任务固定值；显式幂等回退；设备版本与操作者审计。
- 独占迁移序列；每个 `(tenant, device, commandType)` 只能有一个活动版本，数据库层必须确定。
- 已被运行/暂停任务固定的旧版本仍可按任务授权下载，不能因当前版本回退/撤销而断链。
- 独立完成：迁移升降级、API/claim/并发/审计集成测试通过，并输出冻结 fixture。

### P14-ANDROID / T040/T042 设备端部分

- 目标：原子下载与验签；不兼容/篡改拒绝；空闲激活；运行和暂停任务固定旧版；下载中断、进程重启和离线时保留已验证旧版；显式回退恢复本地活动版本。
- 先用本地 fixture 和单测，不独立向 OnePlus 发任务。
- 独立完成：RecipeCatalog、RecipePackageManager、AutomationStore/恢复相关测试通过。

### Root Worker / 集成验收

1. 检查 owned-path diff、commit、测试和证据。
2. Control → Android → Web 进入合并队列；开发时间仍是并行的。
3. 统一生成 OpenAPI/TypeScript 客户端并跑跨端测试。
4. 请求用户从 Web 人工发布无副作用 Recipe。
5. 独占设备锁依次验证：签名版本被 claim 固定并执行；运行/暂停旧版本不漂移；下载中断旧版可用；显式回退；设备版本审计。
6. 任一项缺失，P14 保持进行中；全部通过后才解锁 P15。

## 8. 子智能体交付格式

```text
WorkItem:
BaselineSHA:
BranchSHA:
OwnedPaths:
ContractVersion:
ChangedFiles:
Tests: <command, exit code, count>
EvidenceDir:
IndependentResult: PASS | BLOCKED
RequiredLocks:
RemainingGaps:
MergeOrderNotes:
```

子智能体不得直接更新权威 Excel。Root Worker 只在核实 commit、测试和证据后更新计划状态。

## 9. 后续并行池

P14 三路施工期间，若某路等待合同或构建资源，可从以下独立方向补位：

- P08：同 task 恢复的软件测试与只读证据整理；真机阶段与 P14 共用设备锁。
- P16/P40：媒体接口/上传 UI、违禁词 DTO/服务，可按后端与 Web 写集拆开。
- P48：公网/TURN/部署环境只读探测；任何部署或重启仍需 `DEPLOY` 锁。

不因 P14 进行中阻塞所有独立软件工作；但 P15 明确等待 P14 完整闭环。
