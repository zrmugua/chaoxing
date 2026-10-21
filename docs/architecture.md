# 项目架构

Vue 3 / Naive UI 提供管理网页，FastAPI 提供管理员鉴权与配置 API，SQLite 保存账号、任务和日志。Android 前台服务承载 Web 服务与 Worker。Worker 管理原版 yatori-go-console 进程的生命周期。

| 路径 | 职责 |
| --- | --- |
| `third_party/yatori-go-console/` | 固定版本的原版 Console 运行源码 |
| `engine/original-console.json` | 原版源码与运行库校验信息 |
| `engine/console_bridge/query.go` | 课程查询入口与父进程存活监测 |
| `backend/app/console_process.py` | 生成私有配置、启动程序、采集输出与结束进程 |
| `backend/app/worker.py` | 持久队列、账号串行、运行记录 |
| `frontend/` | 配置、课程、进程状态与日志展示 |
| `android/` | AndroidKeyStore、前台服务、原生可执行文件打包 |

学习任务不设置查询模式环境变量，直接运行原版 `main()` → `YatoriConsoleInit()` → `logic.Lunch()`。每个账号一次启动一个 Console 进程，一次运行包含所选课程。原版负责登录、视频、文档、章测、作业、考试与内部并发。查询请求通过同一可执行文件的专用入口调用原版 Console 登录和 Core 聚合接口。

账号凭据和服务密钥加密保存在 SQLite。执行时配置写入应用私有目录 `console/<account_id>/config.yaml`，进程结束后清理配置、代理与查询文件。每个账号使用独立的 cwd 与缓存目录，避免 Console 单实例锁相互冲突。stdout 和 stderr 合并后按任务与账号保存，保留原文并过滤敏感值。

Android 将 `libyatori_console.so` 作为可执行文件打包到 `nativeLibraryDir`，使用解压原生库模式；ONNX 从同目录加载。程序包含原版模型资源。Go 查询入口附加父进程监测，管理服务退出后子进程随之结束。Worker 取消任务时发送进程终止信号，超时后强制结束并回收。

暂停与重启后恢复均通过重新启动 Console 完成。进程退出成功只标记「执行结束」；课程或章节完成依据查询结果展示。升级迁移停止旧任务并保留历史，旧任务需从账号页重新创建。管理 API 保留账号加密、CSRF、登录限流和局域网来源校验。

仓库保留 0.5.x 适配器源码与回归样本用于历史兼容研究，位于 `engine/runtime`、`engine/consolelogic` 与 `backend/tests/legacy_worker.py`。0.6.0 的 Worker 与 Android 构建使用上述原版 Console 路径。
