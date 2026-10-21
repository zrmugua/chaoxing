# Yatori Console 执行流程对照

核对日期：2026-10-21。本记录对照官方 Console 源码与本平台 Android 0.5.3，记录学习通执行流程、日志来源和后续适配依据。

## 源码基线

- [yatori-go-console](https://github.com/yatori-dev/yatori-go-console/tree/017711107803f5232fea59446a5b8c801d4ca8b2)：`017711107803f5232fea59446a5b8c801d4ca8b2`。
- Console 的 `go.mod` 指向 [yatori-go-core](https://github.com/yatori-dev/yatori-go-core/tree/ddf52f884145ba9ab7e2ac9e187ba36205eec6ce)：`ddf52f884145ba9ab7e2ac9e187ba36205eec6ce`。
- 本平台当前编入的 Core 为 `cf6134fdb2bd0640758216d03c947a2a13b2b16a`，清单见 `engine/upstream.json`。

Console 和 Core 均为 MIT 许可。此次核对阅读源码及调用关系，运行结果仍以实际接入和目标课程验证为准。

## 执行入口与分层

Console 的入口为 `main.go` → `YatoriConsoleInit` → `logic.Lunch`。初始化核心资源后，读取 YAML 配置，调用 `lg.LogInit` 设置日志，再将学习通账号交给 `UserLoginOperation` 和 `RunBrushOperation`。

学习通执行链主要位于 [`logic/xuexitong/XueXiTongPart.go`](https://github.com/yatori-dev/yatori-go-console/blob/017711107803f5232fea59446a5b8c801d4ca8b2/logic/xuexitong/XueXiTongPart.go)：

```text
UserLoginOperation
  → RunBrushOperation
  → UserBlock
  → courseStudy
      → chapterStudy
          → 拉取章节、查询任务点完成情况
          → nodeRun
              → 拉取卡片、解析任务 DTO
              → 刷新当前任务卡、补全执行参数
              → 执行视频 / 文档 / 章测等任务
      → writeCourseWorkAndExam
```

| 层次 | Console 使用方式 | 本平台 0.5.3 使用方式 |
| --- | --- | --- |
| 配置与调度 | Console 的 `config`、`logic`，按账号组织课程任务 | Python 配置、SQLite Worker 与任务检查点 |
| 业务流程 | Core 的 `aggregation/xuexitong`，封装读取、解析及部分错误处理 | `engine/runtime` 实现课程、章节、试卷及执行适配 |
| 底层请求 | Core 的 `api/xuexitong` | 同一 API 包，通过平台请求出口调用 |
| 日志 | Console 流程调用 `lg.Print`，Core 也产生诊断输出 | 采集当前执行进程 stdout/stderr，另存 Worker 管理日志 |

本平台源码导入脚本以 `api/xuexitong` 为起点收集依赖，当前编入清单包含该 API 所需源码。Console 使用的聚合业务包在完整 Core 仓库中；仅替换 Core 提交不会自动接入 Console 的执行流程。

## 章节测验

Console 的 `nodeRun` 在识别到章测任务后，再次调用 `PageMobileChapterCardAction` 获取该任务卡，并用 `PointWorkDto.AttachmentsDetection` 补全参数，再交给 `ParseWorkQuestionAction`。

[`ParseWorkQuestionAction`](https://github.com/yatori-dev/yatori-go-core/blob/ddf52f884145ba9ab7e2ac9e187ba36205eec6ce/aggregation/xuexitong/XueXiTongCardAction.go#L339) 的正常读取流程包括：

1. 调用 `WorkFetchQuestion`。返回明确的“无效的权限,code=2”错误时，尝试 `WorkFetch2Question`。
2. 用 `ParseWorkInform` 提取试卷表单信息，通过 `WorkInformInputWorkDTO` 写入题目实体。
3. 在 `div.chapter-content` 中读取截止状态，再用 `ParseQuestionSets` 分题。
4. 按题型解析题目与答案字段。选择题读取 `em.choose-opt` 的 `id-param`，保留真实选项标识与选项内容的对应关系。
5. Console 按答题配置取得答案，再按保存、交卷或答案完整才交卷的策略执行，并记录服务器返回信息。

本平台当前也读取任务卡、调用 `WorkFetchQuestion`、保留表单字段并使用 `ParseQuestionSets`。需进一步对齐的差异是：

- `chapterPaper` 使用前次解析的任务 DTO；原版在读取每个测验前再次刷新对应任务卡。
- 当前读取失败直接返回错误，尚未接入上述特定错误的备用读取接口。
- 当前遇到选项 `id-param` 与显示顺序不同时，将该题交给人工确认；原版保留真实选项映射。
- 当前自行构造章测保存表单；适配验证需同时覆盖题目解析、原有答案保留、隐藏字段和服务器返回结果。

0.5.3 已调整验证提示识别，区分题目、脚本和明确隐藏的元素。用户课程具体触发条件仍需结合实际返回页面核对。

## 日志来源和配置

原版显示的课程开始、章节数量、视频观看时间、任务跳过原因和试卷提交结果，许多来自 Console 的 `XueXiTongPart.go`，由业务流程主动调用 `lg.Print` 产生。采集底层 API 调用的 stdout/stderr，只能得到这些调用实际产生的输出。

[`logic.Lunch`](https://github.com/yatori-dev/yatori-go-console/blob/017711107803f5232fea59446a5b8c801d4ca8b2/logic/Lunch.go#L134) 调用 `lg.LogInit` 传入日志级别、文件开关、颜色与路径。[Core 日志实现](https://github.com/yatori-dev/yatori-go-core/blob/ddf52f884145ba9ab7e2ac9e187ba36205eec6ce/utils/log/LogUtils.go#L70) 只有 INFO、DEBUG 两种级别，按所选级别相等匹配输出，日志文本自带时间。

本平台的系统日志级别目前用于数据库与管理日志过滤。RPC 初始化尚未传入 Core 日志级别，也未调用 `lg.LogInit`；因此在系统设置中选择 DEBUG，并不会开启 Core 的 DEBUG 输出。这是日志配置对齐时需要处理的实际差异。

账号筛选可继续使用本平台的独立执行进程和任务绑定：上游实际产生的控制台输出经脱敏后保存到该账号，平台调度事件保留各自来源。适配后的流程日志需要明确其实现来源。

## 视频末尾状态

Console 的 `ExecuteVideo` 在到达视频末尾后，根据服务端 `isPassed` 继续上报及等待，另有等待上限。本平台 `video` 目前在末尾两次上报后返回，再由 Worker 回读任务卡和章节状态；未获完成确认时保留待确认状态。

两者等待服务端确认的窗口不同。对齐时需覆盖“已到末尾但完成状态尚未更新”的样本，验证等待、超时和服务重启后的检查点行为。用户日志中的视频未确认状态是否与该差异有关，尚待目标课程验证。

## 后续适配验收

实现以以上固定源码为依据，优先核对任务卡刷新、章测备用读取、真实选项映射、Core 日志设置和视频末尾确认。复用业务函数前需检查包级依赖、Android 原生依赖、取消操作及错误返回；Console 的 CLI 入口中存在 `os.Exit` / `log.Fatal`，服务端接入应将错误交还任务调度器。

验收覆盖账号配置到执行参数的传递、账号间日志归属、真实请求与解析路径、答案保存和交卷边界、任务取消与恢复，以及目标设备上的课程运行。代码阅读用于确定实现依据，离线样本和真实课程结果分别记录。
