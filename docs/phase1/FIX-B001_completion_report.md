# FIX-B001 完成报告

## 问题描述
- **问题ID**: B001
- **严重程度**: P0（阻塞性）
- **问题**: 商品分组外键错误
- **状态**: ✅ 已修复

## 根本原因

### 错误分析
代码尝试将 `ProductRow` 的ID写入 `ContentGroupMembershipRow.content_id`，但该字段的外键约束指向 `content_item.id`，导致：
1. 外键约束违反
2. 商品和内容分组逻辑混淆
3. 商品分组功能完全不可用

### 错误代码位置
- `services/control-api/src/cloudctl_api/services.py:1279-1323` - `batch_update_product_group()`
- `services/control-api/src/cloudctl_api/services.py:1459-1464` - `filter_products()`

## 修复方案

### 1. 创建独立的Product分组表

**新增表**: `ProductGroupRow`
```python
class ProductGroupRow(Base, TimestampMixin):
    __tablename__ = "product_group"
    id: Mapped[str]
    tenant_id: Mapped[str]
    name: Mapped[str]
    description: Mapped[str | None]
    created_by: Mapped[str]
```

**新增表**: `ProductGroupMembershipRow`
```python
class ProductGroupMembershipRow(Base, TimestampMixin):
    __tablename__ = "product_group_membership"
    id: Mapped[str]
    tenant_id: Mapped[str]
    group_id: FK("product_group.id")
    product_id: FK("product.id")  # ✅ 正确的外键
    added_by: Mapped[str]
```

### 2. 修复services.py

**修复点1**: `batch_update_product_group()`
- 将 `ContentGroupRow` 改为 `ProductGroupRow`
- 将 `ContentGroupMembershipRow` 改为 `ProductGroupMembershipRow`
- 将 `content_id` 改为 `product_id`

**修复点2**: `filter_products()`
- 将 `ContentGroupMembershipRow` 改为 `ProductGroupMembershipRow`
- 将 `content_id` 改为 `product_id`

### 3. 更新导入语句
在 `services.py` 中添加：
```python
from .db import (
    ...
    ProductGroupRow,
    ProductGroupMembershipRow,
    ...
)
```

## 修改文件清单

1. **services/control-api/src/cloudctl_api/db.py**
   - 新增 `ProductGroupRow` 类
   - 新增 `ProductGroupMembershipRow` 类

2. **services/control-api/src/cloudctl_api/services.py**
   - 更新导入语句
   - 修复 `batch_update_product_group()` 方法
   - 修复 `filter_products()` 方法

3. **services/control-api/migrations/versions/001_add_product_group_tables.sql**
   - 新增数据库迁移脚本

## 验证

### ✅ 语法检查通过
```bash
ruff check services/control-api/src/cloudctl_api/services.py
# 无错误
```

### ✅ 导入验证通过
```python
from cloudctl_api.db import ProductGroupRow, ProductGroupMembershipRow
# ✅ Import successful
# ProductGroupRow: product_group
# ProductGroupMembershipRow: product_group_membership
```

### ⚠️ 需要运行数据库迁移
```sql
-- 执行 001_add_product_group_tables.sql
-- 创建新表
```

## 验收标准

✅ 已满足:
1. 创建了独立的 ProductGroup 和 ProductGroupMembership 表
2. 外键正确指向 product.id
3. 代码中所有使用 ContentGroupMembership 处理 Product 的地方已修复
4. Python语法检查通过
5. 导入测试通过

⏳ 待执行:
6. 数据库迁移（需要运行SQL脚本）
7. 集成测试（需要完整服务栈）

## 架构说明

### 分离原则
- **ContentGroup**: 用于 ContentItem（帖子、笔记等）
- **ProductGroup**: 用于 Product（商品、SPU等）
- 两者独立，不应混用

### 数据模型
```
ProductGroup (1) ----< (N) ProductGroupMembership (N) >---- (1) Product
ContentGroup (1) ----< (N) ContentGroupMembership (N) >---- (1) ContentItem
```

## 遗留问题

### 数据迁移（如果需要）
如果之前有错误写入的数据（虽然会因外键约束失败），新表创建后是空的。
如果确实需要从 ContentGroupMembership 迁移数据，可执行：
```sql
INSERT INTO product_group_membership (...)
SELECT ... FROM content_group_membership cgm
JOIN product p ON p.id = cgm.content_id
WHERE ...
```

但由于原代码会因外键约束失败，预计没有脏数据。

## 完成时间
2026-09-06 21:15

## 下一步
- 运行数据库迁移
- 继续修复其他P1级问题（B004, B007, B012）
- 或继续T004及后续任务
