# 0.3.0 验证记录

本页保留 0.3.0 构建的执行结果。当前版本见 [验证记录](../verification.md)。

日期：2026-10-20。当前版本使用 Yatori 固定提交 `cf6134fdb2bd0640758216d03c947a2a13b2b16a`。本页记录本地执行结果；[0.2 系列历史记录](verification-0.2.md) 对应其各自构建。

## 执行核心与后台

- `python scripts/vendor_yatori.py`：45 个上游及受控补丁文件的清单、LF 规范化 SHA-256 全部通过。
- Go 1.27.3 执行 `go test ./... -count=1 -cover` 通过，`engine/runtime` 语句覆盖率 67.3%；上游 `api/xuexitong` 包的测试通过。
- 离线测试通过实际 Yatori API 生成请求，覆盖登录加密、课程与章节转换、文档执行后回读、视频按服务端进度和实际经过时间推进、只读测验预览、未知状态、人工验证、重定向边界和请求取消。响应由测试传输提供。
- Windows Python 3.12：40 项测试通过（13.24 秒）；独立 Python 3.11 环境使用 Android 依赖组合：40 项通过（12.67 秒）。包括真实原生子进程的版本握手、Cookie 隔离、状态清空和取消销毁，及管理 API、持久化恢复、加密、HTTP 会话与 Java/Python Fernet 互通。两套环境的 `pip check` 通过。
- 临时独立数据库上实际启动 FastAPI 与 Worker，通过 HTTP 验证健康接口、Vue 网页入口、管理员初始化、已登录接口访问、Worker 在线和退出。未登录与退出后的管理请求均返回 401；验收进程已结束。

## 前端和部署配置

- Vue TypeScript 检查、Vite 生产构建、前端许可证生成通过。
- Compose 与两个 GitHub Actions 工作流 YAML 解析通过；校验了统一 Dockerfile、共享数据卷、Worker 命令与宿主机回环端口。
- 本机没有 Docker 可执行程序，本版镜像构建及容器启动尚未执行。当前源码尚未推送，0.3.0 工作流尚未在 GitHub Actions 执行。

## Android 构建与签名

- JDK 17、Android SDK 35、NDK 30.0.16248370 和完整 Python 3.11 构建通过。固定版本的 `gomobile` 生成 ARM32、ARM64、x86_64 原生库。
- device release、emulator debug 与 Android 集成测试 APK 构建通过；3 项 Java Fernet 单元测试通过。
- 设备安装包为 `0.3.0 / versionCode 5`，应用 ID `cn.zrmug.chaoxing`，最低 API 26。包含 ARM32/ARM64 的 Yatori JNI 库、管理后端、Vue 资源及 GPL/MIT/Go/Python/Chaquopy/前端许可证。局域网 HTTP 已在 manifest 中启用，自动备份关闭。
- 官方 apksig 验证 v2/v3 签名通过，证书与已交付版本一致，可覆盖安装。包大小 50,503,970 字节。
- 逐一比对包内 17 个后端 Python 源文件、22 个网页资源和来源/许可文本与本次源码及前端构建一致；设备包恰有 ARM32、ARM64 两份 Yatori JNI 库。

```text
APK SHA-256:
d3c25001be4b2f1054cf361b0d0860b42038991654486300bb15ef56ed123569

签名证书 SHA-256:
75e872fa679fd280c81018f6013604c714815c9930d7ddd30dfba8902a1062ac
```

## 目标环境验收

本机 API 31 模拟器在硬件加速模式退出，软件模式也未进入可用状态。因此本版 Android HTTP、Binder/Go RPC、并发隔离与重启的集成测试已构建，运行验收尚未完成。历史版本的模拟器结果见历史记录。

维护环境没有真实学习通账号。本版登录、课程、视频、文档、阅读及进度回读仍需授权账号逐项实测；离线响应样本只验证相应协议和状态处理。U30 Air 的 ARM 运行、局域网连通、后台保活与开机恢复也需要实机验收。

章节测验目前提供题目与可选 AI 答案预览。自动提交、独立音频类型、通知和定时计划尚未接入管理流程。未知完成状态保持待核对，验证码和人工限制交由使用者在学习通处理。
