# B11：息屏后 UID 冻结的真机对照，2026-09-26

## 当前结论

本轮已把一加的一次心跳停顿定位到**内核 cgroup 冻结状态**，不再仅凭日志空窗推测协程调度问题。尚未证明冻结策略的发起者，也未完成修复验收。B11 保持 `IN_PROGRESS / DEVICE_WAIT`。

一加的系统“耗电管理”页面显示“允许完全后台行为”关闭；用户已被请求在系统界面手动开启，仅改变这一项。开关前后的因果对照待执行，不能仅凭关闭状态断言是唯一原因。

没有修改、构建或安装 APK，没有恢复业务执行，没有部署/迁移/重启云端，也没有真实发送、发布、删除、改价或评价。

## 本轮边界与基线

- 仓库基线：`59f85d6`；本轮不覆盖原未跟踪的 IM/输入证据。
- 用户连接手机后要求继续推进；本轮只在一加做非业务诊断、息屏/亮屏对照和系统设置页导航。
- ADB 识别两台：一加 `b0644fb5`、华为 P30 Pro `APH0219624006517`。P30 `GBGDU19830002425` 未在 ADB 列表出现，但其云端设备记录的认证请求时间持续更新，不能称其完全离线。
- 三台云端最新认证请求均有推进。查询时有效租约、未取消租约、非终态任务、启用 schedule、有效 preview 均为 0；这是取证时间点快照。
- 一加仍安装 `0.1.0-connectivity-20260926` 诊断包；PID `661`。服务 `CompanionSyncService` 存在且 `isForeground=true`，无障碍服务 Bound。这些事实没有阻止后续冻结。
- 按 SOP 获得一加本地锁 fencing `7`，holder `codex-b11-20260926`。未获取或驱动华为设备写锁。
- 没有修改任何系统权限、后台策略、白名单或 cgroup 文件；系统开关留给用户操作。

## 现场证据

### 1. 亮屏和息屏对照

手机诊断日志的时间均为北京时间：

| 时刻/阶段 | 观察 |
|---|---|
| 17:53–17:55，亮屏 | 同一 PID 心跳 HTTP 200，成功后的等待约 20,002–20,007 ms |
| 息屏后 17:56:08.068 | `interactive=false`，开始最后一轮网络检查 |
| 17:56:08.413 | 心跳成功 |
| 17:56:08.422 | 进入 `heartbeat_delay` |
| 停顿期间，外部读取 | UID 与子进程 cgroup 均报告 `frozen=1`；31 条线程的 `wchan` 采样为 `get_signal` |
| 亮屏后 18:01:18.262 | 同一 PID 恢复 `network_check`，距上个阶段 309,839 ms；`sleep=0` |
| 18:01:18.674 | 心跳再次 HTTP 200 |
| 18:01:38.686 | 下次等待回到 20,003 ms |

`KEYCODE_SLEEP` 与 `KEYCODE_WAKEUP` 只切换屏幕状态；未打开平台应用或触发业务。手机当时 `locked=false` 且 USB 充电，本轮是息屏对照，**不是实际锁屏或脱离电脑验收**。

### 2. 内核冻结证据

实际 `/proc/661/cgroup` 中 unified membership 为 `/uid_10269/pid_661`。

| 层级 | 息屏停顿期间 `freeze / frozen` | 亮屏恢复后 `freeze / frozen` |
|---|---|---|
| `/sys/fs/cgroup/uid_10269` | `1 / 1` | `0 / 0` |
| `/sys/fs/cgroup/uid_10269/pid_661` | `0 / 1` | `0 / 0` |

原始输出：[frozen-cgroup.txt](frozen-cgroup.txt)、[awake-cgroup.txt](awake-cgroup.txt)。两个文件的行顺序都是：UID freeze、UID events、PID freeze、PID events。

这些是顺序读数，不是原子快照，不能用两个采样点证明整个五分钟连续冻结。祖先请求 `1` 与后代有效状态 `frozen=1` 一致；本层请求 `0` 不代表未被冻结。

Linux Kernel Documentation 的 `cgroup.freeze` 定义确认：冻结请求作用于本 cgroup 及所有后代，完成后 `cgroup.events/frozen` 变为 `1`；冻结中的进程不能继续运行，直到解冻。来源：`https://docs.kernel.org/admin-guide/cgroup-v2.html`，2026-09-26 获取正文核对。

因此可以确认**本次采样时的冻结机制**，但不能将其扩大为：

- 具体哪个 Oplus/HANS/第三方服务发起冻结；
- 上午完整 777,691 ms 空窗与本次具有相同原因；
- 华为两台存在相同故障；
- 只更换协程 dispatcher 或增加线程就能解决；
- 开启“完全后台行为”一定能解决。

### 3. 系统状态的差异

- AMS 当时仍显示 `isFrozen=false`、`virtualFreeze=false`，有前台服务。这不能覆盖内核 cgroup 的直接读数。
- `dumpsys deviceidle whitelist` 包含 `user,com.company.cloudctl.companion,10269`。
- `RUN_ANY_IN_BACKGROUND` 返回默认 `allow`。
- 系统耗电管理页“允许完全后台行为”关闭，“允许唤醒前台”开启；自启动和关联启动也关闭，但本轮只请求用户改变“完全后台行为”。[现场截图](app-battery.png)
- `debuggerd -j 661` 返回需要 root，未重试或获取 root。向本应用发送了一次标准 SIGQUIT 请求线程转储；没有取得可引用的 Java 栈，不将其当作定位依据。未强停或杀死应用。

## 软件交付与验证

新增 `scripts/companion_freezer_probe.py`，默认 dry-run，显式执行后仅使用选定 serial 的 `pidof`/`cat`；无网络、无安装、无 input、无 shell 拼接或特权回退。两轮读取本层/祖先，起始及每轮结束复核 boot ID、PID、启动 tick 和 cgroup 归属；空组、失败保留未知，状态切换与 PID 复用不假报稳定状态。相符只代表检查点相符，不保证检查之间从未迁移。

实际一加运行结果保存在 [awake-probe.json](awake-probe.json)：只证明对应采样时刻未冻结，不证明后台持续在线。诊断阶段日志的相关节选见 [transition-trace.log](transition-trace.log)，仅有阶段、时钟、电源状态和 HTTP 状态，不含 token、消息正文或用户内容。

命令：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q \
  tests/ops/test_companion_freezer_probe.py tests/ops/test_device_lock.py \
  --tb=short -p no:cacheprovider
.venv/bin/ruff check scripts/companion_freezer_probe.py tests/ops/test_companion_freezer_probe.py
.venv/bin/ruff format --check scripts/companion_freezer_probe.py tests/ops/test_companion_freezer_probe.py
.venv/bin/pyright scripts/companion_freezer_probe.py
python3 scripts/companion_freezer_probe.py --serial b0644fb5 --execute-read-only
python3 scripts/plan_guard.py docs/current/tasks.json
```

最初定向探针测试 36 项通过；补充重复畸形事件和 serial 校验后，探针加设备锁回归 65 项通过。Ruff lint 和探针 Pyright 通过；最终复核见本记录收尾部分。没有运行 Android/全仓回归，因为本轮未改运行时、APK 或业务 API。

独立只读审查确认应优先核实 cgroup 状态与系统策略，不再追加进程内定时探针。探针实现另有定向审查，不混同此前诊断 APK 尚缺的完整生命周期安全审查。

## 收尾

- 独立审查提出空 cgroup/中途迁移和跨重启身份复用两项边界，已补 `populated`、boot ID、每轮身份复核及回归。身份字段使用 `identityMatchesAtChecks`，不宣称全区间稳定。
- 最终定向测试 **71 passed / 0 failed**（探针 49 项、设备锁 22 项），见 [tests.log](tests.log)。补测期间一个 FakeReader 用例先返回新 PID、却提供旧 PID 的 stat，正确触发 UNKNOWN；已修正夹具使其模拟一致的新进程身份，未放宽生产判断。
- Ruff lint、Ruff format check、探针 Pyright、任务图校验、`git diff --check` 均通过。
- 18:18 再次只读截图显示“允许完全后台行为”仍关闭；未执行开关后的实验。
- 18:19:46 释放 fencing `7`，最终本地状态 `FREE`，见 [lock-release.json](lock-release.json)。
- 收尾云端只读快照见 [cloud-final.json](cloud-final.json)。没有改维护模式、设备绑定、任务、服务或数据库。
- 本轮不是持续在线修复完成；没有提升 B11、消息 C6、Q13/Q14 或其他业务验收状态。

## 下一步

1. 用户手动开启一加“允许完全后台行为”后，重新核查设备锁/占用，重复息屏实验，比较实际 cgroup 状态与成功心跳。
2. 若仍被冻结，保留内核证据，继续查具体策略；不要全局关闭系统限制或通过 sysfs 解冻。
3. 候选方案通过后，依次执行前台 5 分钟、后台 15 分钟、真实锁屏且脱离电脑 30 分钟验收。
4. 恢复经授权、匹配签名及绑定的业务 APK 后，再做只读任务和三机消息 C6。当前诊断 APK 禁用业务，不能直接推进业务验收。

验收标准与只读工具说明见 [Companion 后台冻结 runbook](../../../../docs/runbooks/companion-background-freeze.md)。
