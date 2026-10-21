# Web 平台部署与运行

源码部署需要 Python 3.11+、Go 1.27、对应平台 C 编译器和 Node.js 22。Docker 构建会生成前端和 Yatori 原生执行文件。源码运行前执行 `python scripts/build_original_console.py --host`。

## Docker Compose

在 Linux VPS 安装 Docker Engine 与 Compose 插件，克隆本仓库后执行：

```bash
python3 scripts/configure.py
docker compose build
docker compose up -d
docker compose ps
```

`configure.py` 只使用 Python 标准库，生成独立 MASTER_KEY 与随机 SETUP_TOKEN；已有 `.env` 会保留。Linux 文件权限为 0600。请从服务器 `.env` 中读取 SETUP_TOKEN，首次打开网页时填写令牌并创建管理员。初始化后使用管理员账号登录，后续管理通过网页完成。

Compose 启动 `web` 与 `worker` 两个容器，使用同一镜像和 `console-data` 数据卷。页面与 API 统一由 8080 提供；宿主机监听 `127.0.0.1:${PORT:-8080}`。Worker 独立于浏览器执行，健康检查读取数据库心跳。保持一个 Worker 实例；课程并发通过系统设置调整，同账号始终串行，原版 Console 在进程内执行多课程和多任务点模式。

生产环境将域名经 Nginx/Caddy 反向代理到 `http://127.0.0.1:8080` 并配置 TLS。`COOKIE_SECURE=true` 要求浏览器使用 HTTPS。反向代理需要传递 Host、X-Forwarded-Proto，任务日志通过控制台轮询读取。

Nginx 的 location 示例，放入已经配置证书的 HTTPS server 块中：

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    client_max_body_size 1m;
}
```

环境变量：

| 名称 | 用途 |
| --- | --- |
| `MASTER_KEY` | Fernet 加密密钥，必须与已有数据匹配 |
| `SETUP_TOKEN` | 首次管理员初始化令牌，至少 24 个字符 |
| `DATA_DIR` | 本地数据目录，Compose 固定为 `/data` |
| `COOKIE_SECURE` | 生产为 `true`；本机 HTTP 调试由启动脚本临时设置 |
| `PORT` | 宿主机回环监听端口，默认 8080 |
| `YATORI_CONSOLE_BINARY` | 源码部署可指定 Yatori 原生执行文件路径；默认位于项目 `bin/` |

## 本机运行

Linux：

```bash
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-web.txt
python scripts/build_original_console.py --host
python scripts/configure.py
cd frontend
npm ci
npm run build
cd ..
python scripts/run.py --dev-cookie
```

在第二个终端激活同一虚拟环境，从项目根目录启动 Worker：

```bash
python scripts/run.py --worker
```

Windows PowerShell：

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-web.txt
.venv\Scripts\python.exe scripts/build_original_console.py --host
.venv\Scripts\python.exe scripts/configure.py
npm --prefix frontend ci
npm --prefix frontend run build
.venv\Scripts\python.exe scripts/run.py --dev-cookie
```

第二个 PowerShell 终端运行 `.venv\Scripts\python.exe scripts/run.py --worker`。访问 [http://127.0.0.1:8080](http://127.0.0.1:8080)。`--dev-cookie` 仅适用于本机 HTTP 调试，生产环境通过 HTTPS 访问。启动脚本加载项目 `.env`，Web 模块工厂与 Worker 使用相同数据库配置。

## 首次管理流程

1. 使用 SETUP_TOKEN 创建管理员，登录控制台。
2. 添加本人授权的学习通账号，创建登录验证任务；验证码或平台限制在任务中提示人工处理。
3. 同步课程，查看课程章节和任务点，再为指定课程创建学习任务。
4. 在任务中心暂停、停止、重试或同步确认，在运行记录与日志查看结果。
5. 核对“本地执行状态”与“服务端确认状态”；服务端未确认时前往学习通检查，刷新/确认后再继续。

AI 为可选设置。启用 OpenAI 兼容 API 后可查看题目答案预览；Key 加密保存。首次配置建议先用少量题目确认端点、模型与输出，检查外部服务费用和题目内容发送范围。

## 持久化、备份与恢复

数据卷保存 `console.sqlite3`、SQLite WAL/SHM、运行记录与 Worker 锁。凭据、Cookie、AI Key 的数据库字段为密文，解密依赖 `.env` 中的 MASTER_KEY。容器重建保留命名数据卷；`docker compose down -v` 会删除数据卷，属于数据清除操作。

创建在线一致性快照：

```bash
docker compose exec worker python scripts/backup.py
```

快照位于数据卷的 `/data/backups/`。可复制到宿主机：

```bash
docker compose cp worker:/data/backups ./backups
```

本地部署可执行 `python scripts/backup.py --data-dir ./data --output ./backups/console.sqlite3`。备份使用 SQLite backup API，适用于 WAL 模式；另将 `.env` 存入安全备份位置。

恢复步骤：停止 Web 和 Worker，使用同一 MASTER_KEY；把目标数据库替换为快照，清理该目标数据库旧的 `-wal` 和 `-shm` 文件，确认文件所有者为容器 UID/GID 10001，再启动服务。替换前先保留现有数据目录副本。容器数据恢复可以临时挂载 `console-data` 卷到维护容器进行复制；务必先确认卷名和路径。

Worker 重启后回读未完成任务的服务端状态；视频依据服务端 `playTime` 续播，文档/阅读等请求结果不确定的任务交由人工确认。暂停、停止和恢复均以控制台实际状态为准。

## 升级和诊断

升级前备份，按 `UPSTREAM.md` 完成代码合并和回归，再运行 `docker compose up -d --build`。初版 schema 通过版本表记录；未来破坏性 schema 更新需提供专用迁移和回滚说明。

```bash
docker compose logs --tail=100 web worker
docker compose exec worker python scripts/worker_health.py
```

管理 API 需要登录；`GET /api/health` 只返回基本健康状态。Worker 失去心跳时检查容器日志、数据卷权限、磁盘空间和环境密钥。密码或 Cookie 失效请重新验证账号；403、验证码或人工确认请到学习通完成处理，再按控制台提示恢复。

## 验证边界

Docker 配置在本次开发环境中未执行镜像构建或容器启动；上线前需在具备 Docker 的环境完成构建、健康检查、持久化与备份恢复验收。当前没有真实学习通凭据，登录、课程和任务接口的线上效果待授权账号实测。离线自动化测试只证明相应管理逻辑与给定响应样本下的行为。
