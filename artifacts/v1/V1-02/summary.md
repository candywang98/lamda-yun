# V1-02 验收总结

**任务**: 冻结 APK 直连主线和 V1 业务范围  
**状态**: done  
**完成时间**: 2026-09-05  
**负责人**: AI 助手

## 完成内容

### 1. 创建 ADR 0004: V1 execution boundary and platform scope

新增架构决策记录，明确：
- **生产执行路径**：
  - Companion mobile-local（闲鱼、小红书、抖音）
  - API publisher（微信公众号）
- **开发/调试工具**：Edge + LAMDA（仅用于 Studio）
- **V1 平台范围**：四个平台冻结，其他平台延后
- **Runner 互斥**：Companion 与 Edge 不能同时持有设备写租约

文件：`docs/adr/0004-v1-execution-boundary.md`

### 2. 更新 AGENTS.md

新增 "V1 execution ownership" 章节：
- 明确 Companion、API Publisher、Edge/LAMDA 的组件所有者
- 列出各执行路径负责的平台
- 冻结 V1 平台范围为四个

变更：新增 15 行，明确执行所有权

### 3. 更新 README.md

重写 "Production execution paths" 章节：
- 区分生产路径 vs. 开发工具
- Companion mobile-local 的独立性说明
- Edge/LAMDA 降级为调试工具，不是生产依赖

变更：重构 18 行，明确生产执行边界

### 4. 更新 docs/v1/02-实施方案.md

更新主链路说明：
- 引用 ADR 0003 和 ADR 0004
- 明确 Companion 直连和 API Publisher 的职责
- 说明 Edge/LAMDA 与 Companion 的互斥关系

变更：重构 11 行，增强架构清晰度

## 架构冲突分析

识别并解决了 4 个关键冲突：

1. **主执行路径定位不清**
   - 问题：旧文档暗示 Edge 是必需的
   - 解决：ADR 0004 明确 Companion 是生产路径

2. **设备执行器并发冲突**
   - 问题：未明确 Companion 与 Edge 能否同时运行
   - 解决：强化单 Runner 约束，Edge 不持有写租约

3. **平台范围未冻结**
   - 问题：原始架构包提到多个竞品平台
   - 解决：冻结 V1 为四个平台，其他延后

4. **文档分散且术语不统一**
   - 问题：多个术语指代同一概念
   - 解决：统一术语，ADR 0004 作为权威定义

详见：`artifacts/v1/V1-02/conflict-analysis.md`

## 验证结果

执行验证命令：
```bash
rg -n "Mobile-local|Companion|LAMDA|V1" AGENTS.md README.md docs/adr
```

验收标准全部满足：
- ✓ 每种执行方式有唯一所有者（Companion: mobile/companion; API: services/control-api; Edge: edge/gateway）
- ✓ 同一提交语义（PublishPlan/Target/CommitIntent 共享）
- ✓ 明确文档入口（ADR 0004 为权威边界定义）
- ✓ 无相互矛盾的强制路线（生产 vs. 调试明确区分）

## 变更文件清单

### 新增文件 (1 个)
1. `docs/adr/0004-v1-execution-boundary.md` - 新 ADR 文档

### 修改文件 (3 个)
1. `AGENTS.md` - 新增 V1 执行所有权章节
2. `README.md` - 重构生产执行路径说明
3. `docs/v1/02-实施方案.md` - 更新主链路描述

**总计**: 1 个新增，3 个修改

## 架构决策要点

### ADR 0004 的关键决策

1. **生产路径明确**
   - Companion mobile-local 无需 USB/ADB/Edge
   - API publisher 无需设备
   - 两者共享业务域和提交账本

2. **平台范围冻结**
   - 闲鱼商品（Companion）
   - 小红书图文（Companion）
   - 抖音视频（Companion）
   - 微信公众号文章（API）
   - 其他平台延后至 V1 后

3. **执行器互斥**
   - 单设备单 Runner 约束
   - Companion 持有任务租约时，Edge 不发起写操作
   - Edge 可以观察，不能竞争写入

4. **文档一致性**
   - ADR 0004 是权威边界定义
   - 所有文档引用此 ADR
   - 术语统一使用

### 取代关系

- **取代**: 历史文档中 LAMDA 为主要执行路径的描述
- **补充**: ADR 0003（定义 Companion 如何工作）
- **保持**: ADR 0001（三层架构）、AGENTS.md 规则 1-7

## 后续影响

### 对开发的影响
- Companion 开发是 V1 关键路径
- Edge/Studio 专注调试体验
- API Publisher 独立开发

### 对测试的影响
- Companion 验收无需 USB/Edge
- Edge 测试标记为开发/调试
- 硬件门控保持不变

### 对部署的影响
- 生产环境可选不部署 Edge Gateway
- Companion APK 需要 HTTPS 端点
- API Publisher 需要服务端凭据

## 证据文件

- `conflict-analysis.md`: 详细的冲突分析
- `summary.md`: 本文档

## 下一步

V1-02 已完成验收，可以继续执行 V1-03（盘点用户真实商品库和素材库）。

V1-03 当前状态为 **blocked**，需要用户提供：
- 商品库和素材库的类型
- 只读访问入口和凭据
- 字段样本和主键信息
