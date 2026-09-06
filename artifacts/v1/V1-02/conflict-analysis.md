# V1-02 架构冲突分析与解决方案

## 旧架构与 ADR 0003 的冲突点

### 1. 主执行路径定位不清

**冲突**：
- 旧文档将 Edge + LAMDA 描述为主要执行路径
- ADR 0003 已接受 Companion APK 直连为生产路径
- README.md 中 "Real Edge Hub/Gateway startup requires..." 暗示 Edge 是必需组件

**解决**：
- ADR 0004 明确 Companion 和 API Publisher 是 V1 生产路径
- Edge/LAMDA 降级为开发/调试工具
- README.md 更新，清晰说明各路径的用途

### 2. 设备执行器并发冲突

**冲突**：
- AGENTS.md 规则 4 要求单一 Runner
- 未明确 Companion 与 Edge 是否可以同时运行
- 可能导致两个执行器争抢同一设备的写入权限

**解决**：
- ADR 0004 明确互斥原则：Companion 持有任务租约时，Edge 不能发起写操作
- Edge 可以观察和捕获证据，但不持有写租约
- 单设备、单活动租约的约束得到强化

### 3. 平台范围未冻结

**冲突**：
- 原始架构包提到多个竞品平台
- 没有明确 V1 的具体交付边界
- 可能导致范围蔓延

**解决**：
- ADR 0004 冻结 V1 平台为四个：闲鱼、小红书、抖音、微信公众号
- 其他平台保留为扩展点，不在 V1 验收标准内
- 实施方案明确引用此边界

### 4. 文档分散且术语不统一

**冲突**：
- AGENTS.md、README.md、ADR 文档使用不同术语
- "Mobile-local"、"Companion"、"APK 直连" 指代同一概念
- 缺少统一的架构决策文档

**解决**：
- 创建 ADR 0004 作为权威边界定义
- 统一术语：生产用 "Companion mobile-local" 和 "API publisher"
- 所有文档引用 ADR 0004

## 新 ADR 0004 的范围与取代关系

### 适用范围
- V1 完整交付的执行边界
- 四个平台的明确列表
- Companion 与 Edge/LAMDA 的职责划分
- 生产 vs. 开发/调试工具的区分

### 取代关系
- 取代历史文档中将 LAMDA 作为主要执行路径的描述
- 与 ADR 0003 互补：ADR 0003 定义 Companion 如何工作，ADR 0004 定义边界和范围
- 不改变 ADR 0001 的三层架构原则

### 不变的约束
- 单设备单 Runner（AGENTS.md 规则 4）
- commit_once 语义（AGENTS.md 规则 4）
- LAMDA 导入隔离（AGENTS.md 规则 1）
- 设备端口隔离（AGENTS.md 规则 2）

## 文档一致性验证

已更新以下文档以保持一致：

1. **ADR 0004** (`docs/adr/0004-v1-execution-boundary.md`)
   - 新增：明确执行边界、平台范围、Runner 互斥规则

2. **AGENTS.md**
   - 新增："V1 execution ownership" 章节
   - 明确 Companion、API Publisher、Edge/LAMDA 的所有者和用途
   - 列出四个 V1 平台

3. **README.md**
   - 更新："Production execution paths" 章节
   - 明确 Companion 和 API Publisher 是生产路径
   - Edge/LAMDA 标注为开发/调试工具

4. **docs/v1/02-实施方案.md**
   - 更新主链路说明，引用 ADR 0003 和 ADR 0004
   - 明确两条执行路线及其互斥关系

## 验证结果

执行以下命令验证术语一致性：

```bash
rg -n "Mobile-local|Companion|LAMDA|V1" AGENTS.md README.md docs/adr
```

结果显示：
- ✓ Companion mobile-local 在所有文档中一致指代生产执行路径
- ✓ Edge + LAMDA 在所有文档中一致标记为开发/调试工具
- ✓ V1 平台范围在所有文档中一致为四个平台
- ✓ 无相互矛盾的执行路线描述

## 后续影响

### 对开发的影响
1. Companion 开发是 V1 的关键路径，无 Edge 依赖
2. Edge/Studio 开发专注于调试体验，不阻塞生产交付
3. API Publisher 模块独立开发，无设备依赖

### 对测试的影响
1. Companion 验收测试（ADR 0003）无需 USB/Edge
2. Edge 测试明确标记为开发/调试
3. 硬件门控（blocked_hardware）保持不变

### 对部署的影响
1. 生产环境可以不部署 Edge Gateway
2. Companion APK 需要独立的 HTTPS 端点
3. API Publisher 需要服务端凭据管理

## 总结

通过 ADR 0004，我们：
- 解决了执行路径定位混淆的问题
- 明确了 V1 的四个平台范围
- 强化了单 Runner 互斥约束
- 建立了文档一致性

所有变更都向后兼容现有代码，只是澄清了架构边界和文档描述。
