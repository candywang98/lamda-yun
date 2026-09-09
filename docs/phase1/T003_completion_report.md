# T003 完成报告

## 任务信息
- **任务ID**: T003
- **任务名称**: 写分层ADR并确定复用边界
- **优先级**: P0
- **状态**: 已完成
- **完成时间**: 2026-09-06 20:45

## 修改文件
- 新增: `docs/adr/0005-phase1-architecture-reuse.md`
- 新增: `docs/phase1/T003_architecture_review.md`
- 新增: `docs/phase1/T003_completion_report.md`

## 提交内容

### 1. 已盘点的现有组件

#### 复用的核心组件 ✅
- 租户/用户/权限体系
- 商品/内容/媒体领域模型
- 发布计划/快照/目标
- 提交账本（CommitIntent）
- Temporal调度器
- Outbox事件分发
- 自动化包签名

#### 需要扩展的组件 📝
- DeviceRow（新增fencing_counter, maintenance）
- PlatformAccountRow（新增verified_fingerprint, capabilities）
- MobileTaskRow → PlatformTaskRow（统一状态机）

### 2. 新增组件边界

#### 设备控制面
- **DeviceLeaseRow**: 统一AUTO/REMOTE写锁
- **AccountDeviceBindingRow**: 每平台单账号绑定
- **控制原则**: 同设备FIFO，单写者，epoch fencing

#### 视频流面
- **新服务**: services/video-relay/（WebRTC信令）
- **协议**: WSS + ICE + TURN
- **APK组件**: MediaProjection + PeerConnection
- **目标**: 720p@20fps，自适应15-30fps

#### Recipe引擎
- **RecipeManifestRow**: 签名的状态机定义
- **本地执行**: APK解释执行，云端不逐步控制
- **安全**: 动作白名单，有界循环，签名验证

#### 远控协议
- **协议**: RemoteAction (session_id, epoch, seq, ttl)
- **路径**: Web → WSS → APK → AccessibilityService
- **安全**: REMOTE lease, epoch验证, TTL防过期

### 3. 明确的复用边界

#### 必须复用（禁止重复创建）
- ✅ Tenant隔离体系
- ✅ Product/Content数据库
- ✅ MediaAsset存储
- ✅ PublishPlan业务流程
- ✅ CommitIntent账本
- ✅ Temporal调度
- ✅ 设备注册enrollment

#### 明确不做（一期范围外）
- ❌ 转转、拼多多等其他平台
- ❌ 自动客服、采购系统
- ❌ 多客户注册/计费（二期）
- ❌ Root/Device Owner依赖
- ❌ Edge Gateway生产依赖（ADR 0004）

### 4. 迁移策略

#### 阶段1A: 基础设施（T003-T011）
- 新增表：DeviceLease, AccountDeviceBinding, RecipeManifest
- 扩展表：Device, PlatformAccount, MobileTask
- Alembic迁移，支持回滚

#### 阶段1B: 双轨并行（T012-T025）
- 旧step-based继续运行
- 新recipe-based逐步启用
- Feature flags控制切换

#### 阶段1C: 完整迁移（T026-T120）
- 逐平台切换
- 废弃旧路径
- 清理兼容代码

## 已满足验收标准

1. ✅ 盘点了所有现有租户、账号、设备租约、PublishPlan/Snapshot、commit ledger、自动化包签名和outbox
2. ✅ 明确保留Control API模块化服务，不新增微服务（除video-relay）
3. ✅ 确定业务任务云端创建，APK下载Recipe本地执行
4. ✅ 确定复用Temporal调度，DB为任务事实，Redis仅信令分发
5. ✅ 创建了ADR 0005文档，列明复用/新增边界
6. ✅ 定义了统一设备写锁约定
7. ✅ 声明了Root/Device Owner非一期前提
8. ✅ 列出了字段/API新增位置与旧路径迁移策略

## 未满足项/阻塞
无

## Excel状态
已完成

## 数据库迁移
待后续任务（T006开始）创建实际migrations

## 测试命令
```bash
# 验证ADR文档存在
ls -la docs/adr/0005-phase1-architecture-reuse.md

# 验证架构审阅文档
ls -la docs/phase1/T003_architecture_review.md
```

## 证据路径
- `docs/adr/0005-phase1-architecture-reuse.md`
- `docs/phase1/T003_architecture_review.md`
- `docs/phase1/T003_completion_report.md`

## 下一步行动
- T004: 逐字段盘点及31项闲鱼目录覆盖
- T005: 生产API真相与真实登录态
- T006: 统一设备/文件/版本发布权限

