# C4 主会话直接验证与接入阻塞

日期：2026-09-23，Asia/Shanghai。执行方式：主会话直接修改、测试与检查；未使用工作流或子智能体。

## 结论

IM-M3 受影响软件门通过；全仓类型门仍有既有错误，不宣称全仓全绿。未部署后端/前端、未执行生产迁移、未安装手机 APK、未发送闲鱼消息。三机接入停在只读准入：两台华为 ADB shell 超时，需要现场恢复可响应连接及人工授权。C6 真实消息和30分钟观察未执行。

## C4 发现并修复的问题

1. **解除暂停崩溃**：`ImUploadHold.apply` 返回操作是否成功，不是目标 held 值。旧接收器 `check(apply(...) == held)` 在 held=false 且成功时必然抛异常。已改为检查成功结果。先前归因于 Robolectric/SQLite 的说法错误，测试曾弱化为直接调 helper，不能证明接收器解除路径。本轮恢复真实 receiver 调用、数据库重开、解除暂停、发送一次并确认的回归测试；已通过。
2. **绑定身份隔离**：持久 outbox 的发送查询原先未限定当前 binding deviceId。现发送只读取该绑定的行；旧绑定未确认消息保留、不会冒名上传。新增旧/新绑定共库测试。
3. **HTTP 确认边界**：原 task outbox 策略的 `409 mobile task lease` 不能当作 IM 消息已确认。IM 路径现保留永久失败而不确认消息；新增回归测试。
4. **跨端 canonical 证据**：新增 `contracts/fixtures/im-m3-canonical.json`，Android 与 Python 实际读取同一份固定 SHA-256。覆盖2000、2001、4500码点及补充平面字符截断边界。
5. **消息顺序与分页**：旧补传不能倒退 lastMessageAt；新增 `latest=true` 查询（默认仍保留旧 API 顺序），Web 获取最新200条；after 游标采用时间/id严格递增，避免重复锚点。SQLite 输出补 UTC 时区，避免浏览器按本地时间误解。
6. **迁移验证**：既有0032使用 PostgreSQL-only ALTER COLUMN，导致 SQLite 完整迁移测试失败。本轮只补SQLite batch_alter_table分支，PostgreSQL原语义保持。移除本轮0033测试中的 stamp 绕过；完整 SQLite 迁移、回退保护以及隔离 PostgreSQL upgrade/downgrade/upgrade 均实跑通过。
7. **格式门**：db.py 原有六处格式差异已用仓库 Ruff 机械换行，无业务改变。受影响文件格式和lint通过。
8. **API 契约**：重新导出 OpenAPI，仅增加入站 platform 必填/枚举和 latest 查询字段；TypeScript契约包编译通过。

## 最终执行结果

| 门 | 实际结果 | 证据 |
|---|---|---|
| IM集成+迁移回归 | 41 passed，含SQLite/PostgreSQL参数化与隔离PG迁移 | C4-backend-final.log |
| Web全量Vitest | 41 files / 304 tests passed | C4-web-final.log |
| Web类型与生产构建 | vue-tsc -b、vite build均exit 0；有大chunk警告 | C4-web-final.log |
| Web改动文件ESLint | exit 0 | C4-web-final.log |
| Android acceptance IM | 87 tests / 0 failures / 0 skips | testAcceptanceUnitTest XML |
| Android debug全量JVM | 1204 tests / 0 failures / 0 skips | testDebugUnitTest XML |
| Android lint及APK | lintDebug、lintAcceptance、assembleDebug、assembleAcceptance均exit 0 | C4-android-final.log |
| 受影响Python类型 | pyright 0 errors；mypy 5 source files无问题 | C4-pyright-scoped.log、C4-mypy-scoped.log |
| 受影响Python格式/lint | 7 files already formatted / All checks passed | C4-format.log、C4-ruff.log |
| 计划图 | valid=true | C4-plan-guard.json |
| 安全边界 | passed | C4-security.log |
| 全仓Pyright | 39 errors，失败文件均未在本轮修改 | C4-pyright-all.log |
| 全仓mypy | 134 errors in 31 files（158 source files）；错误涉及未修改模块 | C4-mypy-all.log、C4-type-baseline-files.json |

这些门只证明软件结果，不冒充真机。测试中的回复回归是内存/本地测试库，不连接真实设备或外发闲鱼消息。

命令均使用仓库 `.venv/bin/python/.venv/bin/ruff/.venv/bin/pyright/.venv/bin/mypy`，Web用已装node_modules内的Vitest/vue-tsc/Vite/ESLint；绕过本机pnpm 11与项目pnpm 10启动器版本不一致，不更改依赖/锁文件。Android使用绝对gradlew和显式 `-p mobile/companion`、`--offline`。

最新 APK 路径、字节数与 SHA-256 见 `C4-apk-manifest.json`；C2文件中的旧哈希代表较早构建，不应再用于安装校验。acceptance仅用于受控验收，不是签名/身份已验收的生产升级包。正式 release 受控发布公钥门未配置，不宣称正式release构建或签名升级完成。

## C5 只读现场结果

详见 `C5-readonly-device-state.json`（2026-09-23 02:19+08:00）。

- APH0219624006517（此前VOG）：ADB devices显示online，但包查询20秒超时，再次getprop 8秒超时；本次无法复核绑定、签名、授权，停止该设备。
- GBGDU19830002425（此前ELE）：ADB devices显示online，getprop 8秒超时；无法确认安装/绑定/授权，停止该设备。
- b0644fb5（OnePlus LE2100）：USB只读成功；生产 Companion 已安装，CloudCtl无障碍处于Bound；acceptance包未安装。
- OnePlus现有绑定deviceId：4aabc387-6e4b-4b59-a525-b1c119ec7f5b；cloudUrl=https://43.133.243.154.sslip.io。仅读取非秘密身份字段，未输出token。
- OnePlus已装生产APK证书SHA-256：67a6d9af9e400326e1254b87ea310f34b1a1395664ca89424f141dbabba57796。这是已装包读数，不代表新acceptance可覆盖升级；包名/签名/绑定均需按C5契约处理。
- 未驱动OnePlus Wi-Fi别名；未使用settings put、清数据、卸载、安装、触屏或通知注入。

## 不放行项

全仓类型门不是全绿；两台华为需要现场恢复可响应ADB连接，之后再核对签名/绑定并由用户手动授权。生产更新需另做部署准入和升级兼容性确认；本轮没有修改远程服务。C6仍缺三台真实外部入站、重投/重启恢复及30分钟观察，D必须保持进行中。
