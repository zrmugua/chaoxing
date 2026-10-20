# 0.5.0 验证记录

日期：2026-10-20。Yatori 核心固定为 `cf6134fdb2bd0640758216d03c947a2a13b2b16a`。配置对照官方生成器 `f4aba3eb3ee53b54478461c964e6dd3929ada531` 和 Android App `cb479146973ac7aca5abedf81dfc53fa4c5d298c`。使用流程与接入范围见 [功能文档](../yatori-features.md)。

## 本地检查

- Python 3.12、Python 3.11 / Android 依赖环境各 84 项测试通过，两套环境 `pip check` 通过。
- 回归覆盖 Yatori YAML 导入导出、事务回滚、敏感字段加密、启动摘要与配置快照、精确答案映射、保存状态与课程完成分离、未知写入恢复、日志过滤与文件输出、秘塔请求协议、本机与局域网题库。
- Go `go test ./... -count=1 -cover` 通过，运行时语句覆盖率 71.2%。新增协议响应覆盖章测部分保存和既有答案保留、三种提交策略、作业/考试入口和试卷读取、保存/交卷参数、隐藏签名字段隔离及人工验证处理。
- 固定版 Yatori 的 45 个源码及受控补丁文件清单、哈希校验通过；前后端语法、TypeScript 检查和 Vite 生产构建通过。
- 临时独立数据目录启动实际 FastAPI 与 Worker，通过 HTTP 验证健康检查、Vue 入口、管理员初始化、未登录 401、Worker 心跳、退出鉴权。
- 浏览器在本地验收账号与课程数据上验证四种答题模式、三种提交策略、课程多选、账号配置保存、重新读取及启动摘要。页面错误日志为空。截图保存在本地交付目录。

离线协议测试使用合成 HTML / JSON 与测试传输，验证真实解析和请求构造代码；界面验收数据用于检查操作流程。

## Android 构建

- JDK 17、SDK 35、NDK 30.0.16248370 构建原生 AAR、设备 release、模拟器 debug 与集成测试 APK 通过；3 项 Java Fernet 单元测试通过。
- APK 为 0.5.0 / versionCode 7，最低 Android 8 / API 26，支持 ARM32 / ARM64，浏览器管理入口为局域网 HTTP。
- PyYAML 6.0.3 和 LibYAML 0.2.5 的 Android 两种 ARM 依赖安装、打包成功，许可文本随包分发。
- 官方 apksig 校验 v2/v3 签名通过。核对 APK 内 24 个后台 Python 源文件、27 个网页资源、来源及许可证文本与本次构建一致；核对 ARM32 / ARM64 原生库。
- APK 大小为 51,491,807 字节。

```text
APK SHA-256:
85dfcb1585cd37ae1f06842a1bbc8840b863ec31b4bcbb0aa0d2372753f45093

签名证书 SHA-256:
75e872fa679fd280c81018f6013604c714815c9930d7ddd30dfba8902a1062ac
```

## 目标环境验证

本轮 ADB 设备列表为空，Android HTTP、Binder/Go RPC、ARM 执行、系统重启与 U30 Air 后台策略尚未进行设备集成验证。当前环境没有 Docker 可执行程序，容器构建与运行尚未执行。GitHub Actions 结果以对应提交的工作流记录为准。

当前没有真实学习通账号、题库、AI 或 SMTP 授权。真实课程的答题、保存、交卷、学习通内置 AI、服务端回读和邮件送达需在目标环境逐项验证；本地测试通过不代表上述场景已经实测。

历史记录：[0.4.0](verification-0.4.0.md)、[0.3.0](verification-0.3.md)、[0.2 系列](verification-0.2.md)。
