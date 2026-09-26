# Companion 后台冻结只读诊断

适用范围：B11 持续在线故障。运行在已获授权的开发电脑上，不是生产执行器，不建立新的远程 shell 入口。正常业务仍使用手机直连云端，不依赖 ADB。

## 不把不同事实混为一谈

- 手机联网、绑定有效、前台服务存在、心跳持续成功、业务执行就绪分别验收。
- `device.last_seen_at` 是最近认证请求，不是专用成功心跳指标；要结合具体 APK 与心跳日志。
- AOSP 电池优化豁免不证明厂商后台管理已放行。本次一加同时出现白名单已包含应用、系统“允许完全后台行为”关闭、UID cgroup 已冻结。
- AMS 的 `isFrozen=false` 不否定外部读取到的 cgroup 冻结状态。不同组件的记录不能互相替代。

## 只读检查

先读设备锁 SOP，确认具体设备、APK 和当前占用。读命令也可能扰动调度，应标记取证区间，不能将 ADB 连接期间的表现算作电脑独立验收。

```bash
python3 scripts/companion_freezer_probe.py --serial <exact-serial>
python3 scripts/companion_freezer_probe.py --serial <exact-serial> --execute-read-only
```

默认只显示计划。执行模式仅调用指定设备的 `pidof` 与 `cat`：

1. 读取 boot ID、精确包名的单一 PID、`/proc/<pid>/stat` 启动时刻、实际 cgroup 归属。
2. 在 `/sys/fs/cgroup` 对本层及非根祖先各读两轮 `cgroup.freeze` 和 `cgroup.events`，记录每次读取的开始/结束时间。
3. 每轮结束再检查 boot ID、PID、启动时刻和归属；发生手机重启、进程重启、PID 复用或 cgroup 迁移时不把样本归因给稳定进程。`populated` 不是 `1` 的组不用于认定目标进程未冻结。
4. 无 cgroup v2、无权限、缺字段、超时或进程不存在时保留未知，不使用 root/run-as/其他特权回退。

结果含义：

| 状态 | 允许的结论 |
|---|---|
| `FROZEN_OBSERVED` | 两轮读取均观察到本进程 cgroup 的 `frozen=1`，身份校验未变化；不证明整个区间连续冻结 |
| `NOT_FROZEN_AT_SAMPLES` | 两轮读取中本层及祖先均未显示冻结；不证明后台健康或以后不会冻结 |
| `TRANSITION_OBSERVED` | 两轮存在变化，或冻结请求与完成状态尚不一致 |
| `PROCESS_CHANGED` | 样本期间进程身份/归属变化，不能对目标进程作稳定归因 |
| `UNKNOWN` | 数据不足或读取失败；禁止转换为“未冻结” |

`freezeObserved` 只表示所读 cgroup 文件曾返回冻结值；必须结合 `identityMatchesAtChecks` 和整体状态解释。身份相符只描述检查点，不保证两次检查之间没有短暂迁移。所有读取是顺序采样，不是原子快照。`requestingPaths` 是设置了冻结请求的层级，不是发起该请求的应用/系统服务。

Linux cgroup v2 定义：祖先 `cgroup.freeze=1` 可冻结其后代；`cgroup.events` 的 `frozen=1` 表示冻结完成。因此本层 `freeze=0` 和本层 `frozen=1` 可以同时成立。
依据：Linux Kernel Documentation，Control Group v2，`cgroup.freeze`，2026-09-26 核对，`https://docs.kernel.org/admin-guide/cgroup-v2.html`。

## 后续实验与禁止动作

1. 先记录冻结状态和成功心跳时间，再在独占设备锁及用户授权内做息屏/亮屏对照。不能把亮屏恢复当作持续在线修复。
2. 系统权限/后台行为开关由用户在系统界面操作。一次只改一个设置，保存前后状态；禁止直接写 cgroup/sysfs、关闭全局冻结、强停 Companion、卸载、清数据或绕过权限。
3. 用用户允许的系统设置做单变量实验。不要仅凭某个开关关闭就认定它是唯一原因；要复测实际 cgroup 状态和服务器心跳。
4. 整个进程被冻结时，进程内额外线程、协程、定时器都不能自行执行。未证明原因前，不新增永久唤醒锁或第二套心跳调度。
5. 修复候选需分别通过前台至少 5 分钟、后台至少 15 分钟、真实 keyguard 锁定且脱离电脑至少 30 分钟。USB 充电、`interactive=false`、`locked=false` 不能标成锁屏/电脑独立通过。
6. 诊断 APK 只发心跳，不能领取业务、上传消息或自动升级。恢复正常 APK 与真实业务操作仍须单独确认版本和授权；发送/发布等继续禁止。

本轮现场记录：[2026-09-26 傍晚冻结对照](../../artifacts/delivery-20260916/B11/freezer-20260926/report.md)。
