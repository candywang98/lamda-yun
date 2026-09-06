# 本轮审核证据

日期：2026-09-05。本目录保存本轮实际执行与文件清理证据。

- `verification.json`：各项检查的结果、日志、退出码和限制。
- `device.json`：ADB只读盘点；未读取账号密码、聊天记录或私人媒体。
- `android-summary.json`：实际JUnit XML汇总，41项测试通过。
- `cleanup-manifest.json` / `cleanup-backup.zip`：9个文件的原文副本和SHA；其中8个从活动目录移除，1个仅删除测试无用解构变量。
- `workbook-validation.json`：实际重新打开Excel后校验任务、公式引用、工作表、问题和场景数量。
- `build-plan.py` / `build-workbook.py`：生成任务卡/JSON与Excel的本轮脚本。

## 命令及范围

源码根目录运行：

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pyright
pnpm typecheck
pnpm test
pnpm lint
pnpm build
bash scripts/check-security-boundaries.sh
./mobile/companion/build-external.sh testDebugUnitTest lintDebug
pnpm --filter @cloudctl/web e2e:product
```

检查没有全部通过，准确结果见 verification.json，不能把命令清单理解为成功清单。Ruff/format/Pyright、Android、完整前端构建为清理前基线；清理后重新执行Web40项单测和前端类型检查通过，Web lint由5个变为4个错误。生产逻辑未在本次业务修复，原问题留在任务表。

独立端口 smoke 使用临时 `apps/web/playwright.review.config.ts`，完成后已删除。配置继承原测试配置，排除 `product.spec.ts`（该项单独使用产品配置），将 baseURL 改为 `http://127.0.0.1:4189`，启动命令如下，`reuseExistingServer:false`：

```sh
VITE_OPERATIONS_MOCK_ENABLED=true vite --host 127.0.0.1 --port 4189 --strictPort
```

浏览器使用本机 Google Chrome，测试输出在 e2e-isolated.log 与 browser-results/。16通过、4失败、8跳过；失败为两处 getByText 非精确匹配导致 strict-mode violation。未改断言以制造全绿。默认 e2e.log 的4173端口实际是其他项目，应标环境污染而非当前源码失败。Studio浏览器测试未运行；Studio单测、类型检查、构建已运行。

## 清理恢复

ZIP条目以交接包根目录为相对根。按 cleanup-manifest.json 选择需要恢复的单个文件，解压到临时目录核对 SHA 后再放回原路径；不要无差别覆盖新的计划与后续改动。代码目录本来不是 Git 仓库，本轮没有创建或声称存在任何 Git commit。

旧历史架构任务和验收报告仍有工具引用，保留作历史证据；活动开发入口已切到 docs/v1/README.md。真实平台发布、账号切换、APK安装、权限修改均未在本轮执行。
