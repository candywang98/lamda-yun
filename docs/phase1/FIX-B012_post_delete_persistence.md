# FIX-B012: 帖子删除只写localStorage修复

## 问题描述

**编号**: B012  
**严重程度**: P1  
**模块**: apps/web  
**位置**: `apps/web/src/api/post-catalog.ts`

### 症状
`remove()`方法没有调用后端API的archive端点，只操作localStorage，导致删除操作不持久化。

### 根本原因
在`remove`方法中（93-105行），即使配置了Control API且不在local模式，代码也只是读取列表、过滤后写回localStorage，完全没有调用后端API。

```typescript
// 错误的代码
async remove(ids: string[]): Promise<void> {
  if (!usingLocal && controlApiConfigured) {
    try {
      const keep = (await this.list()).filter((item) => !ids.includes(item.id))
      saveLocal(keep)  // ❌ 只写localStorage，没有调用API
      return
    } catch (error) {
      if (!isMissingApi(error)) throw error
      usingLocal = true
    }
  }
  saveLocal(loadLocal().filter((item) => !ids.includes(item.id)))
}
```

## 修复方案

### 步骤1: 添加archiveContent方法到API client

**文件**: `packages/api-contracts/typescript/src/types.ts`

添加ContentArchiveRequest接口：
```typescript
export interface ContentArchiveRequest {
  reason: string
}
```

**文件**: `packages/api-contracts/typescript/src/client.ts`

1. 添加类型导入：
```typescript
import type {
  // ... existing imports ...
  ContentArchiveRequest,
  // ... rest ...
}
```

2. 添加archiveContent方法：
```typescript
archiveContent(contentId: string, body: ContentArchiveRequest): Promise<ContentView> {
  return this.request(`/api/v1/content/${segment(contentId)}:archive`, { method: 'POST', body })
}
```

### 步骤2: 修复remove方法调用API

**文件**: `apps/web/src/api/post-catalog.ts`

```typescript
async remove(ids: string[]): Promise<void> {
  if (!usingLocal && controlApiConfigured) {
    try {
      // Archive each content item via API
      await Promise.all(ids.map((id) => api.archiveContent(id, { reason: '用户删除' })))
      return
    } catch (error) {
      if (!isMissingApi(error)) throw error
      usingLocal = true
    }
  }
  // Fallback to local storage
  saveLocal(loadLocal().filter((item) => !ids.includes(item.id)))
}
```

## 验证结果

### TypeScript类型检查
```bash
$ pnpm typecheck
✅ packages/api-contracts/typescript: Done
✅ apps/studio: Done
✅ apps/web: Done
```

### 前端测试
```bash
$ pnpm test
✅ Test Files: 21 passed (21)
✅ Tests: 95 passed (95)
```

### 构建
```bash
$ pnpm build
✅ apps/web: built in 6.90s
✅ apps/studio: built in 4.03s
```

## 影响分析

### 修复前行为
1. 用户在Web界面删除帖子
2. 前端只从localStorage中移除
3. 刷新页面后，如果从API重新加载，删除的帖子会再次出现
4. 数据不一致

### 修复后行为
1. 用户在Web界面删除帖子
2. 前端调用`api.archiveContent(id, { reason: '用户删除' })`
3. 后端将content的status设为ARCHIVED
4. 删除持久化到数据库
5. 其他设备/会话也能看到删除

### 向后兼容性
- ✅ 保留localStorage fallback机制
- ✅ API不可用时自动降级
- ✅ 不影响现有的local-only工作流

## 修改的文件

1. `packages/api-contracts/typescript/src/types.ts`
   - 添加ContentArchiveRequest接口

2. `packages/api-contracts/typescript/src/client.ts`
   - 添加ContentArchiveRequest导入
   - 添加archiveContent()方法

3. `apps/web/src/api/post-catalog.ts`
   - 修复remove()方法调用API

## 技术细节

### 为什么使用archive而不是delete？
后端Content API遵循软删除模式：
- `archive` - 将status设为ARCHIVED（推荐）
- 不提供物理删除端点（符合数据保留策略）

### reason字段
- 后端schema要求reason字段（min_length=3, max_length=1000）
- 用于审计和数据恢复
- 使用固定值"用户删除"满足业务需求

### 并发删除
使用`Promise.all()`并行删除多个帖子，提升性能。

## 后续建议

1. **统一删除操作**: 在Product catalog中也存在类似问题，建议一并修复
2. **UI反馈**: 添加删除进度提示（删除中/已删除/失败）
3. **批量API**: 考虑添加批量archive端点减少请求数
4. **撤销功能**: 利用archive机制实现"撤销删除"

## 问题状态

- [x] B012: 帖子删除只写localStorage - ✅ 已修复
- [x] archiveContent API方法 - ✅ 已添加
- [x] ContentArchiveRequest类型 - ✅ 已添加
- [x] 类型检查 - ✅ 通过
- [x] 测试 - ✅ 95/95通过
- [x] 构建 - ✅ 成功

## 完成时间
2026-09-06

---
**修复人**: ZCode Agent  
**验证**: typecheck ✅, test ✅, build ✅
