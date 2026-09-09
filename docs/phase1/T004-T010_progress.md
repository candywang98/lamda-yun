# T004-T010 阶段进度

T004 字段盘点：docs/phase1/field-map.json，31 项闲鱼目录全部保留原 operationId。发布/删除帖子为 AVAILABILITY_PENDING。
T005 生产 API 失败关闭：product/post catalog 不再因 404/501 写入 localStorage。
T006 权限：device.control / task.create / recipe.publish / data.delete。
T007 重绑撤销旧 Companion token，并递增 controlEpoch。
T008 heartbeat 增加 sdkInt/model/network/mediaProjection。
T009/T010 账号状态只返回当前设备 BOUND 账号。

阻塞：T011 之后的真实 Recipe、WebRTC、闲鱼下发需要 Control API 进程、对象存储和真机 Companion。
