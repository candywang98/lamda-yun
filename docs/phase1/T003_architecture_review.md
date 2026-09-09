# T003 分层ADR与复用边界

## 任务信息
- **任务ID**: T003
- **任务名称**: 写分层ADR并确定复用边界
- **优先级**: P0
- **状态**: 进行中
- **开始时间**: 2026-09-06 20:36

## 步骤1: 盘点已有架构组件

### 现有租户和身份模型
class TenantRow(Base, TimestampMixin):
    __tablename__ = "tenant"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)


class UserRow(Base, TimestampMixin):
    __tablename__ = "user_account"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), index=True)
    oidc_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    roles: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "oidc_subject"),)


class EdgeRow(Base, TimestampMixin):
--
class PlatformAccountRow(Base, TimestampMixin):
    __tablename__ = "platform_account"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    external_subject_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    display_label: Mapped[str] = mapped_column(String(160), nullable=False)
    secret_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    authorization_basis: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

### 现有设备租约模型
class DeviceRow(Base, TimestampMixin):
    __tablename__ = "device"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    edge_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("edge_node.id"))
    logical_name: Mapped[str] = mapped_column(String(160), nullable=False)
    android_version: Mapped[str | None] = mapped_column(String(32))
    lamda_version: Mapped[str | None] = mapped_column(String(32))
    target_app_versions: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    labels: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    maintenance: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fencing_counter: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
--
class DeviceLeaseRow(Base, TimestampMixin):
    __tablename__ = "device_lease"
    device_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    lease_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    owner_workflow_id: Mapped[str] = mapped_column(String(255), nullable=False)
    fencing_token: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommitIntentRow(Base, TimestampMixin):
    __tablename__ = "commit_intent"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    target_id: Mapped[str] = mapped_column(
--
class MobileBindingRow(Base, TimestampMixin):
    __tablename__ = "mobile_binding"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("device.id"), index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    app_instance_id: Mapped[str] = mapped_column(String(128), nullable=False)
    companion_version: Mapped[str] = mapped_column(String(128), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("device_id", "app_instance_id"),)


class MobileTaskRow(Base, TimestampMixin):
    __tablename__ = "mobile_task"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

## 步骤2: 现有架构决策文档(ADR)

### ADR-0003: Mobile Local Execution (已接受)
**核心决策**: APK独立执行，不依赖USB/ADB
**关键点**:
- Companion APK通过HTTPS主动连接云端
- 本地AccessibilityService执行UI自动化
- 不依赖Edge Gateway的USB连接
- 适用于闲鱼、小红书等平台

### ADR-0004: V1 Execution Boundary (已接受)  
**核心决策**: 明确V1范围和执行边界
**关键点**:
- 闲鱼商品、小红书笔记、抖音视频、公众号文章
- Companion直连用于移动端
- API Publisher用于服务端(公众号)
- 共享业务领域模型和提交账本

**结论**: ✅ 架构方向已明确，不需要冲突的LAMDA主线


## 步骤3: 关键实体盘点

### 已有实体（复用）

#### 租户和身份
- ✅ TenantRow - 租户隔离
- ✅ UserRow - 用户账号
- ✅ PlatformAccountRow - 平台账号（需扩展）

#### 设备和注册
- ✅ DeviceRow - 设备注册
- ✅ EdgeRow - Edge节点（诊断用）
- ✅ MobileBindingRow - APK绑定（需确认）

#### 业务对象
- ✅ ProductRow, ProductMediaRow - 商品
- ✅ ContentItemRow, ContentRevisionRow - 内容版本
- ✅ MediaAssetRow - 媒体资产
- ✅ MediaUploadRow - 上传管理
- ✅ MediaDerivativeRow - 派生资产

#### 发布流程
- ✅ PublishPlan, PublishTarget, PublishSnapshot
- ✅ CommitIntent - 提交账本
- ✅ AutomationVersionRow - 包版本管理

#### 基础设施
- ✅ Temporal workflows - 调度
- ✅ Outbox pattern - 事件分发

### 需要新增的实体

#### 设备控制（T016）
- ❌ DeviceLeaseRow - 统一写锁
- ❌ 扩展DeviceRow.fencing_counter

#### 账号绑定（T010, T011）
- ❌ AccountDeviceBindingRow - 设备绑定
- ❌ 扩展PlatformAccountRow字段

#### Recipe引擎（T019, T020）
- ❌ RecipeManifestRow - Recipe版本
- ❌ RecipeExecutionStateRow - 执行状态

#### 视频流（T029-T032）
- ❌ VideoSessionRow - 会话元数据
- ❌ 新服务: services/video-relay/

#### 任务扩展（T013, T014）
- ❌ PlatformTaskRow - 统一任务
- ❌ TaskEventRow - 事件日志
- ❌ TaskCheckpointRow - 恢复检查点

## 步骤4: 服务边界确认

### Control API (保留模块化单体)
- 不为百台设备新增微服务
- 保持现有路由结构
- 新增：video-relay单独服务（WebRTC信令）

### Temporal Worker (复用)
- 复用现有调度逻辑
- 新增Recipe触发器
- 新增预约/周期任务

### Outbox Dispatcher (复用)
- 复用现有事件分发
- 新增Recipe下发
- 新增视频会话通知

### APK Companion (重构)
- 新增Recipe解释器
- 新增WebRTC视频
- 新增远控协议
- 保留AccessibilityService

## 步骤5: 数据流确认

### 发布流程
```
Web → Control API (create PlatformTask)
  → Outbox → Temporal → APK (claim)
  → Recipe download → Local execution
  → Event upload → Result reconciliation
```

### 视频流程
```
Web → Video Relay (WSS signaling)
  ← APK MediaProjection → WebRTC → TURN → Browser
```

### 远控流程
```
Web → Video Relay (WSS) → APK AccessibilityService
  → Action execution → ACK
```

## 步骤6: 迁移策略

### 阶段1A: 基础扩展（T003-T011）
1. 创建新表（migrations）
2. 扩展现有表字段
3. 保持向后兼容

### 阶段1B: 双轨运行（T012-T025）  
1. 旧step-based任务继续工作
2. 新recipe-based任务走新路径
3. Feature flags控制切换

### 阶段1C: 逐步替换（T026-T120）
1. 逐平台切换到Recipe
2. 废弃旧执行路径
3. 清理兼容代码

## 步骤7: 不做的事情（明确边界）

### ❌ 不创建的系统
- 第二个产品数据库
- 第二个媒体存储
- 第二个任务队列
- 第二个提交账本
- 第二个设备注册

### ❌ 不扩展的范围
- 转转、拼多多等其他平台
- 自动客服、采购系统
- 设备物理摆放管理
- 计费和多客户UI（二期）

### ❌ 不承诺的能力
- Root权限自动化
- Device Owner静默安装
- 绕过人机验证
- 后台无限读剪贴板

## 步骤8: ADR文档创建

✅ **已创建**: `docs/adr/0005-phase1-architecture-reuse.md`

### 核心决策
1. 复用现有业务领域模型
2. 新增设备控制面（DeviceLease）
3. 新增视频流服务
4. 新增Recipe引擎
5. 统一任务状态机
6. 每平台单账号绑定
7. 渐进式迁移策略

### 关键约束
- 单设备单写者（epoch fencing）
- Recipe本地执行（非云端逐步控制）
- 视频不入关系数据库
- REMOTE不是任务状态（是控制模式）

## 完成时间
2026-09-06 20:45

