# 0.4.0 验证记录

日期：2026-10-20。执行核心固定为 Yatori Go 提交 `cf6134fdb2bd0640758216d03c947a2a13b2b16a`；功能与设置参考 Yatori Android App 提交 `cb479146973ac7aca5abedf81dfc53fa4c5d298c`。功能范围见 [Yatori 功能与设置](yatori-features.md)。

## 后台与执行核心

- Python 3.12 与独立 Python 3.11 / Android 依赖环境各 62 项测试通过。两套环境的 `pip check` 通过。
- 新增回归覆盖全局/账号规则继承与重置、任务配置快照、课程包含/排除、同账号多课程调度、多任务点独立会话、进程资源预算、执行参数传递、敏感服务配置加密、题库协议及 AI 回退、Chat Completions / Responses、SMTP TLS 与事件选择、作业/考试列表和日志记录级别。
- Go `go test ./... -count=1 -cover` 通过，运行时语句覆盖率 69.7%；Yatori 上游学习通 API 包回归通过。协议样本覆盖视频/音频真实时间推进、移动端视频 API、外链 DTO 和服务端回读、只读作业/考试列表、解析异常与敏感入口参数过滤。
- 审查回归覆盖首次会话建立的串行引导、未知空列表保留旧记录、人工验证取消同组任务点、首个异常保留，以及发送前取消恢复检查点。原生进程测试确认发送前取消时管道写入次数为 0。
- 45 个 Yatori 源码与受控补丁文件的清单及规范化 SHA-256 校验通过。
- 使用临时独立数据库启动实际 FastAPI 和 Worker，通过 HTTP 检查健康、Vue 网页、管理员初始化、鉴权、Worker 心跳与退出后的 401。验收进程已结束。

## 控制台

- Vue TypeScript 检查、Vite 生产构建和前端许可证生成通过。
- 浏览器实际登录后验证多任务点模式、并发数量表单、规则保存与刷新后保留，以及题库、邮件设置面板。检查窄屏布局，页面错误日志为空；截图保存在本地交付目录。
- Compose、共享数据卷、回环端口、Worker 命令和 GitHub Actions YAML 校验通过。

## Android 安装包

- JDK 17 / SDK 35 / NDK 30.0.16248370 构建 device release、emulator debug 和 Android 集成测试 APK 通过；3 项 Java Fernet 单元测试通过。
- 设备包为 0.4.0 / versionCode 6，最低 Android 8 / API 26，支持 ARM32 / ARM64，管理入口使用局域网 HTTP。
- 官方 apksig 验证 v2/v3 签名通过。逐一核对 APK 内 21 个后端 Python 源文件、25 个网页资源、来源及许可证文本与本次源码/前端构建一致，并核对两种 ARM 架构的 Yatori JNI 库。
- APK 大小 50,655,847 字节。

```text
APK SHA-256:
c9f18d241619a486d0561bd322bad21e12622ef87984be196a9a6628f309b8ef

签名证书 SHA-256:
75e872fa679fd280c81018f6013604c714815c9930d7ddd30dfba8902a1062ac
```

## 目标环境验收

本机模拟器未能正常启动，本版 Android HTTP、Binder/Go RPC 和重启的集成场景尚未运行。U30 Air 实机、ARM 执行、局域网连接和系统后台策略需要设备验收。

本机没有 Docker 可执行程序，本版容器构建/运行尚未执行；源码尚未推送，0.4.0 GitHub Actions 尚未运行。

维护环境没有真实学习通账号，也没有实际题库、AI、SMTP 授权。相关离线测试使用合成响应或测试传输，真实课程执行、服务端回读与外部服务送达仍需目标环境验证。自动章测/作业/考试填写和交卷的接入范围详见功能文档。

历史结果：[0.3.0](history/verification-0.3.md)、[0.2 系列](history/verification-0.2.md)。历史测试结果对应其各自构建。
