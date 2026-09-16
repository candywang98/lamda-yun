# K10/K11/K12 合同冻结证据（2026-09-16，W1）

## 命令与退出码
- python3 contracts/fleet/v1/tools/check_fixtures.py -> 0（算法与 steps-identity-golden.json parity OK，期望摘要已钉入 fixture）
- python3 contracts/ui-observation/v1/tools/check_fixtures.py -> 0（treeDigest/nodeDigest 钉入 fixture）
- python3 contracts/delivery-delta/v1/tools/check_fixtures.py -> 0（deliveryDigest/expansionIds 钉入 fixture）
- python3 scripts/plan_guard.py docs/current/tasks.json -> valid（A10/B10/C10 等进入 ready）

## 交付物
- contracts/fleet/v1/：fleet-identity-v1.md + 4 fixtures + tools/check_fixtures.py
- contracts/ui-observation/v1/：ui-observation-v1.md + 5 fixtures + tools/check_fixtures.py
- contracts/delivery-delta/v1/：delivery-delta-v1.md + 4 fixtures + tools/check_fixtures.py

## 关键冻结
- K10：online/executable 分离；动态授权信封不入 actionKey/parameterHash；账户写互斥 ACCOUNT_BUSY；open UNKNOWN 阻断重领；固定 steps payloadIdentity+commandRegistryVersion；现状债务（steps 家族 account_id=device_id）显式登记
- K11：快照 source 标签四值；Observation/treeDigest 规范化；Resolved/Ambiguous 二值（禁自动选择）；防误选 wrapper 排除；InputProof.inconclusive=失败；删除证明=IdentityProof of absence≥2源；banner 位移≠进展；P09 门禁改动须 ADR
- K12：mediaDeliveryId=有序列表摘要（顺序敏感）；字段证明引用 ui-observation；多设备展开逐项显式绑定（FANOUT_ACCOUNT_UNBOUND 整批拒绝）；订单去重键 Unique(tenant,platform,platformOrderId)；SKU/拍卖/价格页/其它平台 PENDING_VERIFICATION 台账

## 未测项
- 新 fixtures 的 Kotlin/Python 镜像测试：消费者义务（A10/A11/B10/B12/B14），契约已钉死期望摘要供断言
- 未触碰生产代码与已发布 Recipe 字节
