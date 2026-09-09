# OnePlus 9R recipe 安装修复现场证据

日期：2026-09-08（Asia/Shanghai）。设备 b0644fb5，deviceId 4aabc387-6e4b-4b59-a525-b1c119ec7f5b。

## 结果

- 17:41:23 companion 自行下载并安装已发布 recipe，未手工写入应用 recipes 目录。
- 文件：files/recipes/versions/01a07f6d-e5c0-7bb1-b360-a52fa3c06d3f/package.json。
- manifest.hash：825921a415b7b0eaeb832ce1fb6e97847f9f981a45bb57db990491f1001ebd1f。
- 安装日志中 downloadHeaderSha256 与上述 hash 相同。
- 目标任务 7f292679-aa07-4908-81b4-07f7dbcb891e 已 claim；attempt=1，startedAt=2026-09-08T09:41:24.891611Z。
- 任务最终 FAILED / WRONG_ACTIVE_PACKAGE，completedAt=2026-09-08T09:41:26.095338Z。这是领取后的执行错误；本次没有扩展修改前台包检查或重新派发任务。

## 根因证据

- before-crypto-probe.txt：真机系统 KeyFactory 和 Signature 的 Ed25519 初始化均抛 NoSuchAlgorithmException。
- before-recipe-probe.txt：使用已安装旧 APK 实际 CanonicalJson、BuildConfig 和 RecipeSignatureVerifier；graphBytesEqual=true，signBytesEqual=true，trustedKeyPresent=true，但 verifyPackage 失败。
- after-recipe-probe.txt：修复 APK 在同一手机、同一输入下 verifyPackage=PASS。
- after-sync-logcat.txt：真实应用进程 Recipe installed 记录，包含已解析下载头；观察期未出现 Recipe synchronization failed。

## 修复及验证

- RecipeSignatureVerifier 使用随 APK 携带的 Bouncy Castle 1.85.2 lightweight Ed25519Signer，不依赖系统 JCA Ed25519 支持，不修改全局 Provider。
- 保留原公钥、签名、canonical graph hash 及下载头检查。
- CompanionSyncService 增加同步失败日志和首次安装成功日志。
- 新增 6 项回归测试与已发布包/签名字节 fixture；全部 78 项 debug 单元测试通过，无失败、无跳过；assembleDebug 成功。
- 新旧 APK 签名证书一致，adb install -r 覆盖安装保留数据。

## 约束与回退

没有关闭签名校验、重新 publish、操作闲鱼或 65000，也没有读取 secrets.xml。未读取或导出 companion Bearer。
before/ 保存本次变更前的三个源码文件，before-installed.apk 保存手机原安装包，repair.patch 仅含本次生产代码变更。工作区原有大量未提交修改，未执行整库回退或提交。
临时真机探针只读取公开样本和 APK 代码；探针文件验证后删除。
