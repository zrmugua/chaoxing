# 项目架构

平台使用 Vue 3、TypeScript、Naive UI、FastAPI、SQLite 和 Yatori Go 核心。Web API 与 Worker 共享数据库和加密配置；每次账号操作或学习任务启动独立执行进程。浏览器负责操作与展示，后台服务持续调度任务。

## 目录

| 目录 | 职责 |
| --- | --- |
| `frontend/` | 中文控制台、主题、账号/课程/任务与日志页面 |
| `backend/app/` | 鉴权、SQLite 持久化、加密配置、Worker 与管理 API |
| `backend/app/adapters/yatori/` | Yatori JSON RPC 客户端与本地错误文案 |
| `engine/runtime/` | 上游 API 适配、课程与任务数据转换、执行及网络策略 |
| `engine/mobile/` | Android 原生管道入口 |
| `third_party/yatori-go-core/` | 固定版本的 Yatori API 与依赖源码 |
| `android/` | 安卓前台服务、私有存储密钥和浏览器管理入口 |
| `scripts/` | 构建、源码校验、备份和验证脚本 |

## 账号和请求边界

账号凭据、学习通 Cookie 和 AI Key 加密写入 SQLite。管理员登录使用 HttpOnly/SameSite Cookie，写操作校验 CSRF。Android 主密钥由 AndroidKeyStore 包装，HTTP 入口限制私网来源。

每个执行进程拥有独立 Yatori `XueXiTUserCache`。凭据通过匿名管道传递，进程结束后销毁；进程间只交换结构化结果、进度和本地白名单错误。上游的原始日志和错误响应不会直接进入管理日志。

请求策略校验学习通 HTTPS 域名、端口和重定向目标，限制请求时限及响应大小。证书使用系统信任链。安全验证转人工处理。账号并发由 Worker 控制。普通模式同账号串行，多课程模式允许不同课程并行；登录及同步与同账号活动任务互斥。

## 任务与恢复

SQLite 保存 `accounts`、`courses`、`chapters`、`tasks`、`runs`、`logs`、`question_sets` 和设置。任务使用事务领取，持久化本地执行状态、服务端确认状态和待核对任务点检查点。

`learning_rules` 保存账号规则，`account_preferences` 加密保存账号通知邮箱与代理配置，`assessments` 保存作业和考试列表状态。全局规则可被账号规则覆盖；任务创建时将有效规则存入检查点。题库、AI 和 SMTP 敏感配置整体加密保存。

`configuration.py` 转换 Yatori 生成器的 YAML 格式；导入使用事务写入账号和加密服务配置。启动摘要包含规则与课程名单的摘要值，创建任务时验证摘要并保存已确认的规则。`answering.py` 选择答案来源并按题型精确规范化，`assessment_worker.py` 持久化打开试卷、答案写入和保存响应。

原生适配层保留试卷隐藏字段，复用上游作业/考试读取与提交 API。章节测验表单根据固定版 Yatori 协议生成，并保留未覆盖答案。只有任务点、章节和作业/考试状态回读确认后才记录服务端完成；未知写入结果继续保留检查点。

多任务点模式给每个任务点单独建立执行进程并重新读取卡片。Worker 按父进程加任务点并发数预留槽位，总计不超过 8；检查点更新加锁，任务结束后逐点回读。邮件在任务结果落库后发送，邮件失败保留已记录的任务结果。

服务重启后，原运行任务进入 `recovering`，重新读取服务端章节和任务卡。已完成任务跳过；中断视频读取服务端 `playTime` 后续学。缺少进度依据的未确认操作进入待确认状态。视频上报位置受已保存位置加实际经过时间约束，完成结果由任务卡及章节回读确认。

Yatori 提供卡片列表 API，适配层按其返回的卡片顺序读取 `AttachmentSetting` 或任务 JSON 对象，并使用上游 DTO 解析执行字段。未知任务和不完整数据保留可诊断状态。

## Android

`:server` 进程运行 FastAPI 与 Worker。8 个可租用的账号服务进程通过 `gomobile` 原生库执行同一个 Yatori RPC。Binder 传递匿名管道描述符和 PID，账号数据在管道中传输。取消任务后销毁执行进程，确认死亡后复用槽位。

应用使用 Android 8/API 26 作为最低版本，设备包包含 ARM32 与 ARM64，模拟器包使用 x86_64。管理入口为局域网 HTTP。用户停止或设备系统结束服务时，数据库保留恢复检查点。
