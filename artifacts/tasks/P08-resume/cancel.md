# P08 取消不可恢复（真机）

任务 `9c24680d-56bc-4705-866a-51aa23c83c0f`，OnePlus 9R，Companion 长等待、无发布。

1. 领取后暂停，ack 为 `PAUSED_WAITING_USER` / `REMOTE`。
2. cancel → `CANCELLED`。
3. 同 taskId `pageVerified=true` resume → **409** `only a paused task cannot be resumed`（现网文案；本地已改为 cancelled 专用冲突）。
4. 终态 `CANCELLED` / runner `FAILED`，`resumeCount=0`。
