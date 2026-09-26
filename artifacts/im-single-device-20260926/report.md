# I10：单机优先与 Jev 原生接入，2026-09-26

## 状态

用户调整优先级后停止扩展 B11 保活排查，先做一台闲鱼真实入站到网页，再扩三台。只收不发。

**已完成本地 Jev 配置及协议验证；未完成单机真实消息网页验收，未启用线上模型过滤。** 无云端部署/迁移，无手机安装或业务操作。I10 原软件验收记录保留，新增范围进入 `IN_PROGRESS / DEVICE_WAIT`。

## 交付

- 后端 `im_classifier.py`：Jev 原生 SystemOne 客户端，固定四类来源判断；只传平台、标题和正文，不传设备/租户/绑定信息。
- `settings.py`：默认关闭、SecretStr 密钥、HTTPS 地址校验、10 秒总时限和 0.95 阈值。
- `scripts/check_im_classifier.py`：默认 dry-run；显式执行仅能选择三个内置虚构样本，不接受真实消息文本参数。读取 owner-only 配置，不显示密钥。
- 私有文件位于 `.cloudctl-secrets/jev.env`，`0600`，父目录 `0700`，Git 忽略。实际密钥未进入源码、报告、网页或命令参数。
- 此配置仅在本机，检查脚本显式读取；运行中的云端服务未加载新配置，`ImService.ingest` 没有新增模型调用。当前不能声称“已过滤线上系统通知”。

## 供应商取证

用户提供的 base URL 归一化为 `https://api.fengshao1227.com/v1`，模型别名 `jev-latest`。

| 请求/样本 | 实测结果 |
| --- | --- |
| GET `/models` | HTTP 200，包含 `jev-latest`、`jev-1.13.0` |
| 早期聊天兼容请求 | HTTP 500，`convert_request_failed / not implemented`；不是确认密钥失效 |
| 原生 POST `/systemone` 首个虚构买家询问 | HTTP 200，`HUMAN_MESSAGE / 0.99`，报告模型 `jev-1.13.0` |
| 增加保守来源说明后，买家询问复测 | HTTP 200，客户端 `UNKNOWN / NEEDS_REVIEW / 0.87`；检查脚本 exit 1 表示未达到明确分类，不是网络失败 |
| 虚构系统通知 | HTTP 200，`SYSTEM_NOTICE / 1.0`，exit 0 |
| 虚构营销推送 | HTTP 200，`PROMOTION / 1.0`，exit 0 |

没有降低阈值、重试到“通过”或将少量英文样本当中文真实通知精度。不同提示词的两次买家询问不构成同一请求的随机性证明。上述样本不包含真实用户内容。

超时、HTTP 错误、重定向、无效结果、超限内容和低置信度均保留 UNKNOWN/待判断。没有返回“删除/发送”动作。正式过滤仍需真实样本校准及可复核隔离设计。

## 单机准入快照

- 只读核对 VOG `APH0219624006517`：Companion `0.1.0`，安装时间 2026-09-17 13:26:44；闲鱼 `7.27.30`；CloudCtl 无障碍 Bound。手机未被触屏或改配置。
- 2026-09-26 19:06:47 云端只读统计：VOG 有 `IN=5`，最新入库时间 17:51:04。它们早于本轮新测试消息安排，未核实是真实人际消息，不标单机通过。
- 同次查询有效租约和非终态任务均为 0。没有创建任务、发回复或更新监听设置。
- VOG 没有单独的 `im_monitor_config` 行；不能把缺行写成关闭。本地源码缺行默认开启闲鱼 NOTIFICATION；运行中旧服务器的默认行为还需与实际设备/接口核对。
- 浏览器 task space 18 打开现有 `/cloudctl-mobile/im` 返回 `ERR_INVALID_AUTH_CREDENTIALS`，已交还用户正常登录；未伪造身份、绕过 Basic Auth 或更改安全配置。

## 验证

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q \
  tests/unit/test_im_classifier.py tests/integration/test_im_aggregation.py \
  tests/integration/test_im_fleet_ownership.py --tb=short -p no:cacheprovider
.venv/bin/ruff check services/control-api/src/cloudctl_api/im_classifier.py \
  services/control-api/src/cloudctl_api/settings.py scripts/check_im_classifier.py \
  tests/unit/test_im_classifier.py
.venv/bin/pyright services/control-api/src/cloudctl_api/im_classifier.py \
  services/control-api/src/cloudctl_api/settings.py scripts/check_im_classifier.py
.venv/bin/mypy services/control-api/src/cloudctl_api/im_classifier.py \
  services/control-api/src/cloudctl_api/settings.py scripts/check_im_classifier.py
python3 scripts/plan_guard.py docs/current/tasks.json
```

定向回归 **78 passed**。修复初次检查中的导入排序、Pydantic `_env_file` 类型声明不匹配和 Settings 局部变量重名；未忽略类型错误或减少测试断言。源码格式、Ruff、Pyright、mypy 和任务图检查通过。最终日志见 [测试日志](tests.log)。

## 下一步

1. 用户通过正常流程登录现有云控网页，确认 VOG 闲鱼账号。
2. 由用户安排外部账号发一条固定测试消息；本助手不代发、不伪造通知或数据库记录。
3. 对照手机采集、服务器入站及网页，同一正文/设备/时间全链通过后再扩三台。
4. 基于真实来源证据设计系统/营销隔离与未知待核查，再受控启用 Jev。长期保活仍单独保留待验。
