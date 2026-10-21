# 学习通管理台

安卓本机运行的 yatori-go-console 管理前端。App 启动本机管理服务，网页负责账号、配置、课程查询、进程启停和原始日志。每个账号的学习任务由独立的原版 Console 可执行程序运行。

## 安装与使用

Android 8.0 及以上。提供 ARM32 / ARM64 通用包，以及各架构独立安装包；不确定架构时选择通用包。安装后启动服务，在同一局域网浏览器打开 App 显示的地址。账号管理中添加账号，完成登录验证与课程同步，再进入「配置与启动」选择课程和规则。确认摘要后，Console 在安卓设备上执行，关闭浏览器仍可继续。

[下载 APK 与对应源码](https://github.com/zrmugua/chaoxing/releases/tag/android-v0.6.1)。安装、覆盖升级与 UFI Tool 操作见 [Android 指南](docs/android.md)。

## 配置与运行

系统设置提供默认学习规则，以及所有账号共用的 AI、题库、邮件和日志配置。账号保存独立规则后，使用自己的课程范围、视频模式和答题设置；「跟随默认配置」恢复使用系统规则。

每次账号启动生成一份单账号 `config.yaml`，启动原版 Console 的 `main()`。多课程与多任务点模式由 Console 内部处理。暂停、停止会结束该进程；继续或重试时重新启动，由 Console 读取平台状态。任务显示「执行结束」表示进程退出，课程进度通过课程、章节同步查看。

日志页直接接收 Console 的 stdout / stderr，支持按学习通账号和任务筛选。密码、Cookie、令牌及终端颜色控制码会被过滤。升级到 0.6.0 会保留账号、配置和历史记录，并停止旧任务；请在账号页核对规则后重新创建任务。

0.6.1 使用共享 OCR 模型与 Android 资源打包，通用 APK 约 81 MiB，单架构 APK 约 59 MiB。首次启动会清理旧账号目录中可重新生成的模型副本和 Windows 工具缓存。

## 构建与验证

需要 JDK 17、Android SDK 35、NDK 30.0.16248370、Go 1.27、Python 3.11 和 Node.js 22。

```sh
npm --prefix frontend ci
npm --prefix frontend run build
python scripts/build_original_console.py
python scripts/collect_go_licenses.py --original
android/gradlew -p android -PconsoleSplitApks=true :app:assembleDeviceRelease :app:testDeviceReleaseUnitTest
python -m pytest -q
```

配置 `JAVA_HOME`、`ANDROID_HOME`、`ANDROID_NDK_HOME`；Windows 使用 `gradlew.bat`。完整流程见 [Android 指南](docs/android.md)。桌面与服务器可使用 `python scripts/build_original_console.py --host` 构建原版程序，需要对应平台 C 编译器；部署见 [部署指南](docs/deployment.md)。

## 维护

- [架构](docs/architecture.md)：管理服务与原版程序边界。
- [Console 接入](docs/yatori-console.md)：运行入口、配置与查询桥接。
- [功能与设置](docs/yatori-features.md)：参数对应和使用说明。
- [来源与校验](UPSTREAM.md)：固定提交和 Android 运行库适配。
- [验证记录](docs/verification.md)：实际检查及设备验证范围。
- [第三方声明](THIRD_PARTY_NOTICES.md)：依赖、许可文本与源码分发。

平台使用 GPL-3.0。安装包与对应源码、构建脚本和第三方声明一起发布。学习通课程执行仍需在目标设备和账号上验收。
