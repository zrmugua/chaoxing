# 0.2 系列历史验证记录

本页保留 0.2 系列构建的测试和发布结果。当前 Yatori 版本的结果见 [验证记录](../verification.md)。

日期：2026-10-20。测试和样本中的虚拟账号/响应仅用于离线测试；生产适配器请求真实学习通接口。

## 已执行的维护脚本检查

- `python scripts/verify_core.py`：30 个核心/CLI/资源/原测试文件与上游提交 `45d2106b16764231c2de2038fb042e71b23d878f` 的 SHA-256 一致，统一文本 CRLF/LF 后校验。
- 原 README 保留检查：Web 入口之后的原文与上述提交的 README 全文一致。
- 临时目录配置检查：生成的 MASTER_KEY 解码为 32 字节，SETUP_TOKEN 长度合格，默认 Secure Cookie；再次生成返回失败且已有配置字节保持一致。
- SQLite WAL 备份检查：连接保持打开并启用 WAL 时创建快照，校验样本数据和数据库完整性；已有备份目标得到保护。
- Worker 健康检查：有效心跳返回成功，超过 90 秒的心跳返回失败。
- Compose YAML 解析检查：服务命令、回环端口和共享数据卷配置匹配预期；此检查不执行 Docker。

以上脚本检查在本机 Python 环境运行，临时配置与数据库已清理。

## 集成测试

- 本机 Python 3.12 执行 `python -m pytest -q`：90 项通过，耗时 20.78 秒；Python 3.11 执行相同测试：90 项通过，耗时 18.46 秒。覆盖原 CLI、适配层、状态恢复、管理 API、安全校验、Worker、私网来源校验、HTTP 会话、Pydantic 兼容与 Java/Python Fernet 互通。
- `python main.py --help` 正常退出；`pip check` 通过。
- Web 与 Worker 使用独立验收数据目录 `artifacts/smoke-data` 启动，浏览器已验证管理员初始化、账号添加与编辑、运行设置保存和主题切换。
- 界面整合后执行 `npm run build`：Vue TypeScript 检查和 Vite 生产构建通过。
- 浏览器在 1440px 与 390px 宽度检查仪表盘、账号、课程、任务、运行记录、日志和设置页，页面宽度均在视口范围内；表格与移动导航在各自容器中滚动。
- 本次界面验收验证了侧栏折叠/展开、账号编辑弹窗、运行设置保存、管理员退出后重新登录及深浅主题切换。移动设置页的当前导航项可见，浏览器错误日志为空。

## GitHub Actions

- [Web platform](https://github.com/zrmugua/chaoxing/actions/runs/39373828440)：Python 3.13 回归与 CLI 检查、前端构建、Docker 镜像构建均通过。
- [原 CI](https://github.com/zrmugua/chaoxing/actions/runs/39373828477)：通过。
- [Android APK](https://github.com/zrmugua/chaoxing/actions/runs/39373828473)：Python 3.11 兼容门禁、双 ARM 架构打包、原生单元测试及模拟器运行验证均通过。

## Android 0.2.3 任务数据对象选择

- 解析页面中 `mArg` 的 JSON 对象赋值，兼容初始化空字符串、空对象和后续真实任务数据。仅含初始化值或 `$mArg` 模板的卡片按上游语义返回空结果；章节仍有任务而全部卡片为空时返回诊断，课程完成继续通过服务端回读确认。合成样本对照原核心解码器验证；注释和字符串中的赋值示例保持为文本。
- 附件列表、任务参数省略时按原核心约定使用空集合。JSON 无法解码、字段类型异常和任务数据对象冲突分别返回诊断；桌面与 Android RPC 保留有界卡片序号，仅使用本地错误文案。
- Python 3.12 完整回归 135 项通过（24.36 秒），Python 3.11 完整回归 135 项通过（20.46 秒）；30 个核心基线文件校验通过。
- 使用者反馈 0.2.2 在第一个章节读取任务卡时出现 `card_data_invalid`。已复现首次初始化赋值被误读，以及可省略字段被强制要求的兼容问题；使用者实际响应内容与升级后真实课程执行仍待验收。
- APK 构建源码：`646beeae2e1ff113ca1b6839f5cf44788128fc1d`。[Android CI](https://github.com/zrmugua/chaoxing/actions/runs/39378643774)、[Web CI](https://github.com/zrmugua/chaoxing/actions/runs/39378643723) 和[原项目 CI](https://github.com/zrmugua/chaoxing/actions/runs/39378643725) 均通过。Android 12 / API 31 的 x86_64 模拟器集成场景通过（7.087 秒），3 项 Java 加密测试通过；独立安装后的 HTTP 健康、网页访问及未登录接口拒绝验证通过。
- 设备 APK 为 0.2.3 / versionCode 4，包含 ARM32 / ARM64，v2 / v3 签名验证通过，证书与 0.2.2 一致。已逐一比对 APK 中适配器、任务对象提取模块、RPC 契约、Android 桥接和 Worker 源码与构建提交一致。大小为 42,950,786 字节，SHA-256 为 `3e730424806c67981f9c691b6e182684a554a1d7da4d6574d08124e2ccc2d1d6`。

## Android 0.2.2 任务卡兼容回归

- 适配层接受显式空任务卡，按上游语义过滤普通资源附件，并保留缺少 `job` 标记但具有任务编号的任务。`job` 与 `isPassed` 同时缺失时保留未知完成状态，Worker 等待章节回读确认。
- 日志记录章节读取序号、任务点数量和失败操作；RPC 错误文字使用本地白名单，测试校验远端私有异常文字不会进入日志消息。
- 新增合成样本覆盖 [上游问题 #597](https://github.com/Samueli924/chaoxing/issues/597) 的字段结构，以及空卡片、混合附件、任务状态缺失与 Worker 调度。Python 3.12 完整回归 105 项通过（22.63 秒）；Python 3.11 完整回归 105 项通过（19.32 秒）。30 个核心基线文件校验通过。
- 使用者反馈 0.2.1 在其环境中可登录学习通并获取课程章节，执行任务时出现适配错误。上述兼容问题已由离线样本复现；该使用者的具体响应和修复后真实学习任务仍待验收。
- 构建源码提交：`7210ef56b4f07ace87df829d5103750ee307297e`。[Android CI](https://github.com/zrmugua/chaoxing/actions/runs/39376504474)、[Web CI](https://github.com/zrmugua/chaoxing/actions/runs/39376504455) 与[原项目 CI](https://github.com/zrmugua/chaoxing/actions/runs/39376504443) 均通过。
- Android 12 / API 31 的 x86_64 模拟器集成场景通过（6.897 秒），验证 HTTP 管理访问、鉴权、账号隔离与服务重启；3 项 Java 加密单元测试通过。独立安装后通过 ADB 端口转发验证健康接口、网页与未登录请求拒绝。
- 设备 APK 的版本为 0.2.2 / versionCode 3，包含 ARM32 / ARM64；v2 / v3 签名验证通过，签名证书与 0.2.1 一致。已核对 APK 内适配器和 Worker 源文件与构建提交一致，包含 Web 资源和 GPL 许可证。APK 大小为 42,950,786 字节，SHA-256 为 `411681bf5911ea5146899c380c363266aa68530e0a93ed636306c7228517113b`。

## Android 0.2.1

APK 构建源码提交：`57a5618c14329dde2ab1b1efabb1ca08225d8b8f`。局域网入口为 `http://设备IP:8080`，应用显示并复制该地址。应用 ID 为 `cn.zrmug.chaoxing`，versionCode 为 2，最低 Android 8.0 / API 26，设备包包含 `armeabi-v7a` 与 `arm64-v8a`。

- HTTP 会话测试通过：Cookie 自动保持管理员登录，写操作校验 CSRF，退出后管理接口恢复 401。Android 会话使用独立 Cookie 名称。
- JDK 17 上的 3 项 Java Fernet 单元测试通过。
- Android 12 / API 31 的 x86_64 模拟器集成场景通过，耗时 6.808 秒：HTTP 管理接口、管理员初始化、HttpOnly / SameSite Cookie、账号加密保存、Worker 在线、独立进程 Cookie 隔离与服务重启后数据保留。
- 独立安装并启动模拟器 APK 后，宿主机通过 ADB 端口转发使用 HTTP 访问。健康接口返回 `{"status":"ok"}`，网页 HTML 返回成功，未登录访问账号接口返回 401。报告、截图和 HTTP 响应位于本次 Android CI 的 `android-verification` 产物。
- 签名后的双 ARM release APK 已检查 manifest、版本、访问地址、ABI、网页资源和源码链接，官方 apksig 库验证 v2/v3 签名通过。APK 与 0.2.0 使用同一签名，可覆盖升级；安装包大小为 42,950,786 字节。

```text
APK SHA-256:
1c4fa473ce9444fbb96dcfb31996008b64eb05f5840d3293215d56ec305327e4
```

## Android 0.2.0

本节保留 0.2.0 的发布验证记录，对应 [Android CI](https://github.com/zrmugua/chaoxing/actions/runs/39372026918)。

APK 构建源码提交：`a904a8ce8f577a738b03da9701e8d83a234475a2`。应用 ID 为 `cn.zrmug.chaoxing`，最低 Android 8.0 / API 26，设备包包含 `armeabi-v7a` 与 `arm64-v8a`。发布包为 release 构建，应用备份关闭，未启用 debuggable；网页、原核心、GPL 与第三方许可证均包含在 APK 内。

同次构建在 JDK 17 上执行 3 项 Java Fernet 单元测试，Unicode 往返、随机 IV、篡改拒绝与无效密钥校验均通过。

Android 12 / API 31 的 x86_64 模拟器实际执行：

- 1 项集成场景通过，耗时 13.730 秒：HTTPS、设备 CA 校验、未登录请求拒绝、管理员初始化/登录、Secure Cookie、账号密文保存、Worker 在线状态。
- 同一集成场景验证真实核心的离线 Cookie 隔离、Java 管道与 Python RPC 互通、适配进程销毁和新进程状态清空，以及服务重启后数据、主密钥和 CA 保留。
- 集成测试结束后独立安装 APK 并启动，通过 ADB 端口转发在宿主机使用 `curl --cacert` 校验 HTTPS，健康接口返回 `{"status":"ok"}`，网页 HTML 返回成功，未登录读取账号接口返回 401。截图、测试报告和 HTTP 响应保存在该 CI 的 `android-verification` 产物中。

双 ARM release APK 在本机使用独立长期密钥签名，官方 apksig 库验证 v2/v3 签名通过；检查了成品 manifest、ABI、内置网页与对应源码链接。签名包大小为 46,245,230 字节。

```text
APK SHA-256:
f0147df8c0e6ef16d5102d8a5b52a52b6e3cb25c9a1cccc1bbcc89f10e220bfa

签名证书 SHA-256:
75e872fa679fd280c81018f6013604c714815c9930d7ddd30dfba8902a1062ac
```

## 待目标环境验收范围

U30 Air 实机、ARM 设备运行、物理局域网连接、厂商固件的开机/后台策略尚待设备验收。模拟器的独立安装与端口转发验证不覆盖这些硬件和网络条件。本机无 Docker 可执行程序；镜像构建已由 CI 验证，目标服务器的容器健康、数据卷重建与恢复仍需部署验收。

维护环境没有真实学习通账号凭据。使用者已反馈 0.2.1 登录和获取课程章节成功；视频/文档/阅读执行与回读、0.2.3 的真实任务兼容性仍待验收。音频独立类型、自动测验保存/提交、通知和定时计划列入后续阶段。字段缺失或无法判定完成的接口继续保持未知/待确认状态。
