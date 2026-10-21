# yatori-go-console 本机运行

适用于 0.6.0。App 管理原版 Console 的配置、进程和输出，学习任务从原版主程序启动。

## 执行链路

1. 网页加载账号规则与课程列表，展示运行摘要。
2. Worker 为该账号保存课程名称与规则快照，排队等待账号空闲。
3. 生成原版 `config.yaml`；用 `includeCourses` 限定此次选中的完整课程名称。
4. 从 Android 安装目录启动 `libyatori_console.so`，原版 `main()` 负责执行。
5. 捕获 stdout / stderr，绑定任务和账号；原始程序退出后记录退出状态。

同名课程需要同时选择，因为原版按名称匹配。各账号具有独立工作目录和单实例锁缓存。系统并发数控制同时启动的账号进程数，视频多课程和多任务点并发交给 Console。

## 配置

`videoModel`、`cxNode`、`cxChapterTestSw`、`cxWorkSw`、`cxExamSw`、`shuffleSw`、`autoExam`、`examAutoSubmit` 与课程范围按原版字段写入。音频、文档、阅读、外链的处理跟随 Console 流程。原版 `videoModel=0` 也会影响其文档和外链分支。

AI 支持原版 Chat Completions 兼容接口及秘塔接口。题库使用 `apiQueSetting.url`。邮件使用原版 SMTP 配置，并在原版流程到达通知时发送。账号代理以 `ip.txt` 接入原版 HTTP 代理池。

`examAutoSubmit=0` 保存，`1` 自动交卷；`2` 对章测检查空题，对课程作业和考试仍自动交卷。界面按该版本的真实行为提示。

## 查询与状态

查询桥接文件作为额外 Go 文件编入同一可执行程序。设置 `YATORI_BRIDGE_MODE` 后进入课程、章节或作业/考试查询入口，调用原版登录和 Core 函数，把结果写入私有 JSON 文件；日志保持标准输出。桥接提供无账号 `selftest`，用于验证 Android 原生程序、模型和 ONNX 初始化。

暂停和停止会结束当前进程。继续、重试重新启动原版程序。服务重启后运行中的任务暂停，等待用户继续。退出码 0 记录「执行结束」，其实际结果查看原始日志；课程进度通过同步更新。

## 来源

Console 固定提交为 `017711107803f5232fea59446a5b8c801d4ca8b2`，Core 依赖为 `ddf52f884145`。原版源码逐文件校验，学习逻辑与主程序保持原样。Android 运行库加载适配与来源校验见 [UPSTREAM.md](../UPSTREAM.md)。
