# 学习通管理台

安卓本机运行的 yatori-go-console 管理前端。进入学习通账号，即可查看全部课程、管理学习清单、查看当前活动、章节进度与原始日志。每个账号由独立的原版 Console 可执行程序运行。

## 安装与使用

Android 8.0 及以上。提供 ARM32 / ARM64 通用包，以及各架构独立安装包；不确定架构时选择通用包。安装后启动服务，在同一局域网浏览器打开 App 显示的地址。首页展示账号、课程与执行统计，通过「学习账号」进入课程管理。账号列表与详情页均提供「账号学习配置」，可设置各账号的视频方式、答题策略、通知与代理。添加账号后自动查询课程；进入账号，勾选课程并保存学习清单，即可开始学习。Console 在安卓设备上执行，关闭浏览器仍可继续。

[下载 APK 与对应源码](https://github.com/zrmugua/chaoxing/releases/tag/android-v0.7.5)。安装、覆盖升级与 UFI Tool 操作见 [Android 指南](docs/android.md)。

## 配置与运行

账号的学习清单长期保存。运行中增减课程并保存后，后台结束当前进程，再按最新清单启动；暂停时修改清单仍保持暂停，清空清单会停止学习。开始、暂停、继续、停止均在账号详情页完成，执行历史自动记录。

系统设置提供默认学习规则，以及所有账号共用的 AI、题库、邮件和日志配置。账号可保存专属的视频模式和答题设置，也可跟随默认规则。每次启动生成单账号 `config.yaml`，由原版 Console 的 `main()` 处理学习与内部并发。

账号详情持续显示 Console 原始 stdout / stderr，密码、Cookie、令牌及终端颜色控制码会被过滤。当前课程依据 Console 活动展示；章节完成比例来自平台同步，附带更新时间。每门课程均可单独刷新章节进度，顶部「同步课程列表」更新课程清单。查询期间临时结束该账号的学习进程，查询后按账号状态恢复。刷新失败会保留上次进度并显示平台提示。显示「执行结束」表示程序已退出，课程完成情况以平台查询为准。

服务重启后，正在学习的账号保持暂停，点击继续即可恢复。覆盖升级保留账号、课程、配置与历史记录。APK 使用共享 OCR 模型与按架构打包，通用包约 81 MiB，单架构包约 59 MiB。

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
