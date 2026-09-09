# FIX-B001: 修复商品分组外键错误

## 问题描述
- **问题ID**: B001
- **严重程度**: P0（阻塞性）
- **位置**: `services/control-api/src/cloudctl_api/services.py`
- **问题**: `batch_update_product_group` 写入 `content_id=product_id`，但外键指向 `content_item`
- **影响**: 商品分组功能完全不可用，会触发外键约束违反

## 根本原因

### 数据库模型分析
1. **ProductRow** - 商品表（line 171）
2. **ContentItemRow** - 内容表（line 232）
3. **ContentGroupMembershipRow** - 内容分组成员表（line 252）
   - `content_id` 外键指向 `content_item.id`

### 错误代码
```python
# services.py: batch_update_product_group
ContentGroupMembershipRow(
    content_id=product_id,  # ❌ 错误：product_id 不是 content_item 的ID
    content_group_id=group_id,
    ...
)
```

## 修复方案

根据ADR 0005和T058/T060任务，需要创建独立的Product分组表。

### 方案：创建ProductGroup表

