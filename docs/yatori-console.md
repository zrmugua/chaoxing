# Yatori Console 执行接入

更新日期：2026-10-21，适用于 Android 0.5.4。学习通执行器通过 `engine/consolelogic/` 使用固定版本 Console 业务逻辑的服务适配，运行在每个账号独立的 Go 进程中。Python Worker 管理持久任务、并发、暂停与恢复，网页负责配置和日志展示。

## 来源与编入范围

- [yatori-go-console](https://github.com/yatori-dev/yatori-go-console/tree/017711107803f5232fea59446a5b8c801d4ca8b2)：`017711107803f5232fea59446a5b8c801d4ca8b2`，MIT 许可。
- Console 采用的 [Core 业务函数](https://github.com/yatori-dev/yatori-go-core/blob/ddf52f884145ba9ab7e2ac9e187ba36205eec6ce/aggregation/xuexitong/XueXiTongCardAction.go)：`ddf52f884145ba9ab7e2ac9e187ba36205eec6ce`，用于章测解析提取。
- 底层 API 依赖固定于 `cf6134fdb2bd0640758216d03c947a2a13b2b16a`，清单见 `engine/upstream.json`。

`engine/console-upstream.json` 记录原文件、所用函数、SHA-256、服务适配说明和编入文件哈希。`scripts/verify_yatori_console.py` 在桌面执行器及 Android AAR 构建前校验清单。RPC 初始化结果返回 `execution: yatori-go-console`、`console_upstream` 和底层 API 的 `upstream`，供调用方核对来源。

| 执行范围 | 原版依据 | 编入入口 |
| --- | --- | --- |
| 视频、音频 | `ExecuteVideo`、`ExecuteAudio` | `consolelogic.Runner.ExecuteMedia` |
| 文档、阅读、外链 | `ExecuteDocument`、`ExecuteHyperlink` | `consolelogic.Runner` 对应执行方法 |
| 任务卡刷新 | `nodeRun` 中重新读取卡片并完善任务 DTO | `runtime.refreshJob` |
| 章测读取与解析 | `ParseWorkQuestionAction`、`WorkInformInputWorkDTO`、`cleanText` | `Runner.ChapterPage`、`ParseWorkQuestionPage` |
| 作业、考试状态选择 | `writeCourseWorkAndExam` | `consolelogic.AssessmentReady`，通过 RPC 返回 `ready` |
| 执行顺序与日志 | `nodeRun`、Core `lg.LogInit` / `lg.Print` | Worker 分阶段执行及独立进程控制台回传 |

上述函数用于服务运行，接口和错误返回适配了现有 RPC 与任务检查点。Console 许可证随 APK、镜像和对应源码分发。作业与考试的题目读取、保存及交卷继续调用 Yatori API，并由平台保留提交策略和写入确认。

## 任务流程

Worker 先读取课程与章节，再按任务类型处理视频/音频、文档/阅读、章节测验及外链。启用多任务点模式时，章测前等待已启动的媒体与文档任务结束。每次实际执行任务或读取章测前，重新获取对应任务卡，校验任务身份并更新执行参数；已完成的测验直接跳过。

章测通过 `WorkFetchQuestion` 读取。接口明确返回“无效的权限,code=2”时，按原版流程尝试 `WorkFetch2Question`。正常题目页交给从 Core 提取的解析函数，保留题型、表单信息、真实选项标识与选项内容的对应关系。显示顺序打乱的选择题按 `id-param` 映射和保存答案。

保存章测时保留原表单字段及未覆盖答案，按配置选择暂存、交卷或答案完整才交卷。课程作业与考试采用 Console 的可执行状态，包括作业“未交/待重做”、考试“待重考”，并兼容接口返回的其他待做标签。当前验证要求、试卷截止或单独通知页返回具体原因供任务记录。

## 媒体执行与完成确认

视频和音频从服务端播放位置续学，上报位置受实际经过时间约束。正常报告间隔沿用 Console 的 58 秒流程；到达末尾后，每 5 秒继续确认，直到服务端 `isPassed` 返回完成或等待窗口耗尽。等待窗口为 `max(500, 视频时长/2)` 秒，并受任务执行时限与暂停/停止控制约束。

执行进程返回后，Worker 再回读任务卡和章节状态。服务端未确认的任务保留检查点，供后续同步与恢复核对。

## 账号日志与设置

Console 适配会输出章节数量、视频观看时间、提交状态、末尾确认等待、文档/外链状态，以及试卷保存与交卷状态。输出通过账号进程的 stdout/stderr 回传，脱敏后绑定账号及任务，管理日志保留自己的来源。

Worker 将系统日志级别与账号显示名传给执行进程，由 Core `lg.LogInit` 初始化。Core 原版支持 INFO 和 DEBUG，按所选级别相等匹配输出；INFO 用于学习进度，DEBUG 用于核心诊断。事件携带级别，网页可按学习通账号、来源与级别筛选。设置对新建执行进程生效。

## 验证

离线回归覆盖实际 Yatori 请求入口、任务卡刷新、备用章测读取、乱序选项保存、已有答案保留、任务跳过、延迟完成确认、取消等待，以及日志配置和账号归属。构建同时校验 Console 与 Core 源码清单。具体测试、APK 内容和设备验证范围见 [验证记录](verification.md)。
