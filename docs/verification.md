# 0.6.0 验证记录

日期：2026-10-21。Android 版本 0.6.0 / versionCode 12。

## 已完成

- 原版 Console 的 45 个运行文件通过固定提交逐文件哈希校验。
- 原版程序及查询入口编译为 Android ARM32、ARM64、x86_64 可执行程序。
- Python 测试：109 项通过，1 项本机 Java 工具路径检查跳过；Android Gradle 的 Java 单元测试另行通过。
- 网页 TypeScript 检查和生产构建通过。
- Android device release、emulator debug、Android instrumentation APK 与 3 项 Java 单元测试构建通过。
- Android 31 x86_64 模拟器：APK 安装、管理员初始化/登录、HTTP Cookie、账号数据加密保存、Worker 心跳、服务停止与重启通过。
- 在 App UID 下调用安装目录原版 Console，两个独立账号目录的 OCR 模型与 ONNX 初始化通过；原版 `main()` 的控制台输出可被 Python 捕获。
- Android 下子进程终止与回收、临时配置清理通过；本机测试覆盖标准输出/错误捕获、密钥过滤、账号日志归属、单账号串行、多课程合并、查询失败与旧任务迁移。

## 发布核验

签名 APK 发布前核对应用 ID、版本、最低 Android 版本、签名证书、原生文件字节、网页资源、Python 源码和许可证。对应源码 ZIP 包含文件清单及 SHA-256，发布附件提供 APK 与源码的校验文件。可重复构建命令见 [Android 指南](android.md)。

## 验证范围

模拟器测试使用隔离测试账号和无课程配置，不登录真实学习通账号。ARM32/ARM64 已编译并打包，尚未连接用户的安卓真机验证。真实课程登录、章节、媒体、章测、作业/考试和邮件结果需要在目标设备与课程上核验。Docker 配置已更新为原版 Console 构建，本机未执行 Docker 镜像构建。

升级时先停止服务再覆盖安装。账号、配置和历史记录保留，旧任务停止；核对账号配置并重新创建 Console 任务。
