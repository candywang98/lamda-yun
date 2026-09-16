# A05 交付报告：网页业务对象 → CommandV1 + 稳定 publishTargetId（2026-09-16）

执行：W-F 子代理（死于 API 故障，实现+测试主体已写）+ W0 主会话接手收尾（修 3 处：operationId 进 create fields、content revision snake_case、archive reason 体）。

## 交付内容
- `mint_publish_command`（command_factory.py +475）：Product→xianyu.publish_listing.v1 / ContentRevision→xiaohongshu.publish_note.v1 双铸币；publishTargetId = uuid5(固定namespace, content_id+revision_no+platform+account_id+device_id) 确定派生（同目标重铸同 id，跨修订/账号/设备即不同）；铸币前校验矩阵：媒体（存在/租户/顺序/上限 xy50 xhs18/图片类型）404/403/422 按语义、账号绑定 BOUND+平台匹配、recipe ref 冻结（builtin_recipe_ref）
- `platform_task_create_fields`：mint 输出映射到 PlatformTaskCreate 既有盖章通道（publishTargetId/mediaDeliveryId/**operationId**/productId/expectedBindingVersion）
- OPEN_ONLY 结果语义：OPEN_ONLY_RESULT_OUTCOME=「到达确认点」+ 证据 ref 键；validate_open_only_task_result 拒绝任何发布完成表述（测试断言不把探针/开页/填完标成功）
- 测试：单测 20 过（含 PUBLISH_TARGET_NAMESPACE 固定断言）；集成 6 过（幂等重铸同 id、xhs 跨修订新 id、fail-closed 矩阵 422/404/403/409、媒体上限/类型、claim 后 CommandV1 形状+legacyStepsEnabled=false）
- 门禁：全量 702 passed / 1 skipped（基线 681/1，+21 无新失败）

## 契约符合性
K05 §4 open-only / §6 媒体顺序与上限 / §7 结果身份（禁「已发布」表述）逐条有测试；K03 §2 身份链 operationId 创建冻结接入。
