# Jev 消息分类配置与验证

## 范围

`ImMessageClassifier` 是后端可选分类客户端，只返回判断，不写数据库、不删除消息、
不调用回复或手机任务。2026-09-26 19:47 的 `im-3a1d306` 已接入
`ImService.ingest` 提交后的 `ImClassificationObserver` 旁路队列。
这不等于自动过滤，不能用模型可用替代真实消息到网页的验收。

用户指定的配置：

- base URL：`https://api.fengshao1227.com/v1`
- 模型别名：`jev-latest`
- 专用接口：`POST /systemone`，请求为 `model + state + questions`
- 本机私有配置：`.cloudctl-secrets/jev.env`，权限 `0600`；父目录 `0700`，Git 忽略。
- `CLOUDCTL_IM_CLASSIFIER_ENABLED=false`。显式检查命令只为当前虚构样本调用临时启用，不改文件或线上服务。

以上 enabled=false 是本机检查文件。云端通过独立 rollout 环境文件启用，
密钥文件仍为 0600，仅后端读取；未写入前端或 APK。

## 云端观察

- 发布：`/home/ubuntu/cloudctl-mobile/releases/im-3a1d306`。
- `CLOUDCTL_IM_CLASSIFIER_DEVICE_IDS` 显式限定为 VOG 设备 ID
  `050cdb78-c815-4989-8744-2a519d33079a`；默认空列表不观察任何手机。
- 接收入库成功后只对新消息排队；去重命中及事务回滚不向模型发送内容。
- 队列最多 100 条、单消费者，云端单次总时限 5 秒。发送字段仅平台、标题和正文；
  不向供应商发送 deviceId、tenantId、绑定凭据或原始通知对象。
- 日志包含消息 ID、设备 ID、类别、置信度和状态，不含标题、正文、密钥或异常正文。
- 队列满、超时、模型错误、关闭进程均不删除接收消息。该观察队列非持久化，
  重启前未完成的分类不会自动补跑；尚无持久复核箱，不承诺每条分类。
- `CLOUDCTL_IM_RECEIVE_ONLY=true` 拒绝回复任务，网页隐藏回复输入框。
- 旧闲鱼 APK 省略平台字段的兼容仅限 `CLOUDCTL_IM_LEGACY_XIANYU_DEVICE_IDS`；
  正常三机契约仍须显式平台，不能把白名单兼容等同于新版 Android 验收。

云端原生接口合成系统通知测试为 HTTP 200、`SYSTEM_NOTICE / 1.0`。正式发布及租户
归属阻塞见 [发布报告](../../artifacts/im-cloud-20260926/report.md)。

不要把密钥写入前端 `VITE_*`、命令行参数、Git、截图或验收日志。对话中已出现的密钥
应后续轮换。以后每次更新仍须完成变更窗口、兼容和回退准入。

## 可重复检查

```bash
.venv/bin/python scripts/check_im_classifier.py
.venv/bin/python scripts/check_im_classifier.py --execute-synthetic --fixture human
.venv/bin/python scripts/check_im_classifier.py --execute-synthetic --fixture system
.venv/bin/python scripts/check_im_classifier.py --execute-synthetic --fixture promotion
```

默认 dry-run，不联网；显式执行也只有脚本内置虚构样本，没有真实用户消息、deviceId、租户、账号或设备绑定凭据。脚本拒绝非普通文件及组/其他用户可读的配置文件。

## 实测与限制（2026-09-26）

- `/v1/models` HTTP 200，列出 `jev-latest` 和 `jev-1.13.0`。
- 最初按聊天接口请求 `/v1/chat/completions` 返回 HTTP 500、`convert_request_failed / not implemented`；没有据此判为密钥失效。改用 Jev 原生 `/v1/systemone` 后 HTTP 200，网关报告模型 `jev-1.13.0`。
- 原生协议首个虚构买家询问：`HUMAN_MESSAGE / 0.99`；补入更保守的“来源不确定则 UNKNOWN”说明后复测，客户端得到 `NEEDS_REVIEW / 0.87`。两次提示不同，不能据此断言同一请求的随机波动。
- 虚构系统通知：`SYSTEM_NOTICE / 1.0`；虚构营销推送：`PROMOTION / 1.0`，均 HTTP 200。
- 保持阈值 `0.95`，不为测试结果下调；上述少量英文虚构样本不是中文真实通知的精度评估。

分类规则固定在服务端。通知字段只是 `state` 数据，不拼接进指令。超时、HTTP 错误、重定向、非法输出、超限响应、低置信度均返回 UNKNOWN/待判断，不重试、不跟随重定向、不输出供应商错误正文，不改变消息内容或发送权限。请求有总时限，响应上限 16 KiB。

`HUMAN_MESSAGE` 仍是模型分类，不是对发送者身份的证明；正式自动过滤前需校准真实闲鱼
通知并设计可复核的隔离状态。不能承诺“只记录真实用户消息且绝不误杀”。

接口依据：Typesafe 官方 API Reference，`https://docs.typesafe.ai/api`，2026-09-26 核对；供应商适配另有上述实际请求验证。
