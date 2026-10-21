# 0.5.4 验证记录

日期：2026-10-21。Android 版本为 0.5.4 / versionCode 11。此次更新将 Yatori Console 的学习通执行逻辑移植为账号独立的服务模块，范围见 [Console 执行接入](yatori-console.md)。

## 执行与日志

- Go 全套测试通过。新增回归验证任务卡刷新后使用新参数、特定权限提示的备用读取、乱序选项按真实标识保存、原有答案保留、已完成测验跳过、当前验证要求处理、视频延迟确认及等待取消。
- RPC 初始化校验 Console 来源提交；Core DEBUG 设置及控制台采集测试通过。视频、音频、文档和外链使用 Console 适配模块执行。
- Python 3.12 与 Python 3.11 / Android 依赖环境各 98 项测试通过，覆盖日志配置传入、日志事件级别和账号绑定，以及普通/多任务点模式下媒体先于章测执行。
- 作业“未交/待重做”和考试“待重考”状态通过真实 Yatori 读取及保存接口的模拟响应回归验证。
- Console 适配文件、原始来源文件及 Core 的 45 个编入文件清单校验通过。TypeScript 检查及 Vite 生产构建通过，Git 差异检查通过。

## Android 包

- Android AAR 与设备 release APK 构建成功；3 项 Java Fernet 单元测试通过。
- 支持 ARM32 / ARM64，最低 Android 8 / API 26。
- 官方 apksigner 验证 v2 / v3 签名通过，证书延续已发布版本；16 KiB zipalign 检查通过。
- APK 内 24 个 Python 源文件与当前源码一致，27 个网页资源与当前生产构建逐字节一致。
- 两个 ARM 原生库与本次 AAR 一致；Core、Console 及主要运行时许可证内容一致。
- APK 大小为 51,692,643 字节。

```text
APK SHA-256:
146e8bc0ccb55db94f2e685d44978dd024ee0a2e998c94aaaff407c8bb39d6dc

签名证书 SHA-256:
75e872fa679fd280c81018f6013604c714815c9930d7ddd30dfba8902a1062ac
```

## 验证范围与更新

网络和试卷回归使用本地 HTML / JSON 样本及模拟响应，覆盖实际 Yatori API、Console 适配、RPC 和 Worker 调用链。尚未连接安卓设备或真实学习通账号，目标课程运行、设备上的日志和覆盖安装仍需实机确认。

升级前停止管理台服务，覆盖安装 0.5.4，重新启动服务并重试原任务。INFO 日志用于学习进度，DEBUG 用于 Core 诊断，设置对新执行进程生效。账号、配置、已有日志和任务检查点保留。

安装见 [Android 指南](android.md)，实现分工见 [项目架构](architecture.md)。历史记录：[0.5.3](history/verification-0.5.3.md)、[0.5.2](history/verification-0.5.2.md)、[0.5.1](history/verification-0.5.1.md)、[0.5.0](history/verification-0.5.0.md)。
