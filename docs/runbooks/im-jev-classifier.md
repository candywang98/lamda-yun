# Jev 消息分类配置与验证

## 范围

`ImMessageClassifier` 是后端可选分类客户端，只返回判断，不写数据库、不删除消息、不调用回复或手机任务。当前未接入 `ImService.ingest`，不宣称线上过滤已启用。Jev 分类与单机消息到网页的闭环分开推进，不能用模型可用替代真实消息验收。

用户指定的配置：

- base URL：`https://api.fengshao1227.com/v1`
- 模型别名：`jev-latest`
- 专用接口：`POST /systemone`，请求为 `model + state + questions`
- 本机私有配置：`.cloudctl-secrets/jev.env`，权限 `0600`；父目录 `0700`，Git 忽略。
- `CLOUDCTL_IM_CLASSIFIER_ENABLED=false`。显式检查命令只为当前虚构样本调用临时启用，不改文件或线上服务。

不要把密钥写入前端 `VITE_*`、命令行参数、Git、截图或验收日志。对话中已出现的密钥应后续轮换。本机配置不等于服务器环境已配置；上线需单独完成变更窗口、兼容和回退准入。

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

`HUMAN_MESSAGE` 仍是模型分类，不是对发送者身份的证明；正式启用前需校准真实闲鱼通知并设计可复核的隔离状态。不能承诺“只记录真实用户消息且绝不误杀”。

接口依据：Typesafe 官方 API Reference，`https://docs.typesafe.ai/api`，2026-09-26 核对；供应商适配另有上述实际请求验证。
