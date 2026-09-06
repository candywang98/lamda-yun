# V1-05 验收报告：来源连接器协议和字段映射

**任务ID**: V1-05  
**完成日期**: 2026-09-05  
**执行者**: AI  
**状态**: ✅ 完成

## 实施内容

### 1. 数据库模型（db.py）

新增四个表模型：

- **SourceConnectionRow**: 外部数据源连接配置
  - 租户隔离（tenant_id + connection_name 唯一）
  - 支持多种来源类型（source_kind）
  - 凭据引用（secret_ref）而非明文存储
  - 连接测试状态记录

- **SyncRunRow**: 同步运行记录
  - 游标持久化（cursor_before/cursor_after）
  - 统计信息（读取/创建/更新/失败记录数）
  - 支持预览/全量/增量模式

- **SourceRecordLinkRow**: 外部记录到内部实体映射
  - tenant_id + connection_id + external_id 唯一约束
  - 记录哈希值用于增量检测
  - 支持逻辑删除（tombstoned_at）

- **SyncErrorRow**: 行级同步错误
  - 精确到外部ID和字段名
  - 记录快照用于调试
  - 支持重试和解决标记

### 2. Schema 定义（source_schemas.py）

- **SourceConnectionCreate/Response**: 连接管理
- **SourceRecordPreview**: 预览单条记录（含原始数据和标准化结果）
- **SourcePreviewResponse**: 批量预览响应
- **SyncRunRequest/Response**: 同步运行控制
- **SyncErrorResponse**: 错误详情

### 3. 来源连接器服务（source_service.py）

#### 抽象协议（SourceConnector）
- `test_connection()`: 连接测试
- `read_page(cursor, page_size)`: 分页读取
- `fetch_asset(asset_ref)`: 获取二进制附件
- `normalize_record(raw_record)`: 记录标准化
- `get_external_id(record)`: 提取外部ID

#### CSV 文件实现（CSVFileConnector）
- 支持本地 CSV 文件读取
- 行偏移量作为游标
- 产品字段标准化：
  - product_id → spu_code
  - 价格格式转换
  - 媒体引用解析（分号分隔）
- 媒体字段标准化：
  - SHA256 长度校验
  - 尺寸类型转换
  - 内容类型验证

#### 工厂和预览
- `create_connector()`: 连接器工厂
- `preview_source()`: 预览模式（不写数据库）
  - 连接测试 → 读取样本 → 逐条验证
  - 返回有效/无效记录统计和详细错误

### 4. 集成测试（test_source_connections.py）

**15 个测试用例，全部通过**：

#### CSV 连接器基础（9个）
- ✅ 连接测试成功
- ✅ 文件不存在失败
- ✅ 分页读取（第一页/第二页/超出范围）
- ✅ 产品标准化（有效/缺失必填字段/无效价格）
- ✅ 媒体连接器读取
- ✅ 媒体标准化（有效/无效SHA256）

#### 工厂和预览（6个）
- ✅ 工厂创建 CSV 连接器
- ✅ 工厂拒绝未知类型
- ✅ 预览产品源
- ✅ 预览媒体源
- ✅ 预览连接失败
- ✅ 预览租户隔离（不写数据库）

## 验收标准检查

✅ **一页真实样本可转换为标准数据**
- 读取 demo-data/products.csv 前 3 条记录
- 全部成功标准化为 Product 格式
- 读取 demo-data/media-manifest.csv 前 5 条记录
- 全部成功标准化为 Media 格式

✅ **错误精确到外部ID/字段**
- 缺失 product_id → "Missing required field: product_id"
- 无效价格 → "Invalid price format: not-a-number"
- SHA256 长度错误 → "Invalid SHA256 length: 10, expected 64"

✅ **无明文凭据**
- 所有连接使用 secret_ref 字段（可选）
- CSV 示范数据无需凭据
- 日志中无敏感信息泄露

## 测试结果

```bash
# 来源连接器测试
$ pytest tests/integration/test_source_connections.py -v
15 passed in 0.97s

# 完整测试套件
$ pytest -q
407 passed in 16.41s

# 类型检查
$ pyright services/control-api/src/cloudctl_api/source_*.py
0 errors, 0 warnings, 0 informations

# 代码格式
$ ruff check services/control-api/src/cloudctl_api/source_*.py
All checks passed!
```

## 实现的来源类型

**已实现**:
- ✅ csv_file: 本地 CSV 文件（用于 V1 示范数据）

**未实现**（留待后续任务）:
- ⏳ API 连接器（飞书多维表格/其他 SaaS）
- ⏳ 数据库连接器（PostgreSQL/MySQL）
- ⏳ 文件夹监听（inotify/文件变化检测）

## 设计亮点

1. **协议可扩展**: 抽象基类定义清晰接口，新来源只需实现 4 个方法
2. **租户隔离**: 所有表都有 tenant_id + 业务唯一键约束
3. **游标持久化**: 支持中断恢复，不依赖内存状态
4. **预览模式**: 验证配置和字段映射无需实际写入
5. **错误可追溯**: 保留外部记录快照，便于调试和重试
6. **凭据安全**: 只存引用，不存明文

## 依赖任务完成情况

- ✅ V1-02: ADR 0004 定义架构边界
- ✅ V1-03: source-profile.json 和示范数据

## 下游任务解锁

本任务完成后，以下任务可以开始：
- ✅ V1-06: 幂等增量同步与附件入库（依赖 V1-05）

## 文件清单

**新增文件**:
- `services/control-api/src/cloudctl_api/source_schemas.py` (125 行)
- `services/control-api/src/cloudctl_api/source_service.py` (332 行)
- `tests/integration/test_source_connections.py` (304 行)

**修改文件**:
- `services/control-api/src/cloudctl_api/db.py` (+109 行)

**证据文件**:
- `artifacts/v1/V1-05/summary.md` (本文件)
- `artifacts/v1/V1-05/test-output.txt`

## 备注

- 本地文件读取使用同步 I/O（标记 `noqa: ASYNC230`），因为：
  1. 示范数据小（10 产品 + 20 媒体）
  2. 避免引入 aiofiles 依赖
  3. 生产环境应使用 API 连接器而非本地文件
- V1-06 将实现实际的数据库写入和幂等性逻辑
