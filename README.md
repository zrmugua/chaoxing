# 学习通管理台

基于 Yatori Go 核心的超星学习通管理平台。Vue 3 + Naive UI 提供中文控制台，FastAPI 负责管理员鉴权和配置，SQLite Worker 管理持久任务，每个账号通过独立 Yatori 执行进程访问学习通。

支持账号验证、课程与章节同步、视频/音频续学、文档/阅读/外链、章测/作业/考试答题、保存与交卷策略、任务暂停/停止/重试、日志、题库/AI 和邮件通知。课程完成以学习通服务端回读为依据。验证码、人工确认和受限任务在学习通处理后继续。

学习规则支持全局及账号配置，包含普通、多课程、多任务点模式、任务类型开关、随机顺序和课程筛选。规则在创建任务时保存，后台持续执行。完整范围见 [功能与设置](docs/yatori-features.md)。

在账号管理中完成「登录验证 → 配置与启动 → 选择课程及答题方式 → 核对启动摘要」。支持导入、导出官方 Yatori 配置生成器的 `config.yml`。源码：[zrmugua/chaoxing](https://github.com/zrmugua/chaoxing)。

## Docker 部署

```sh
python scripts/configure.py
docker compose up -d --build
```

默认监听宿主机 `127.0.0.1:8080`，服务器通过 HTTPS 反向代理访问。首次使用 `.env` 的 `SETUP_TOKEN` 初始化管理员；配置和数据库保存在独立数据卷。见 [部署指南](docs/deployment.md)。

## Android APK

Android 8.0 及以上，设备包支持 ARM32/ARM64。打开应用并启动服务，手机或电脑连接同一局域网，在浏览器访问 `http://设备IP:8080`。关闭浏览器后服务继续运行。安装、覆盖升级和 UFI Tool 命令见 [Android 指南](docs/android.md)。

APK 对应源码包与构建说明一同提供；可使用 `SOURCE_URL` 为构建设置源码页面地址。

## 本地开发

需要 Python 3.11+、Go 1.27 和 Node.js 22。

```sh
python -m pip install -r requirements.txt pytest
python scripts/build_engine.py
npm --prefix frontend ci
npm --prefix frontend run build
python scripts/configure.py
python scripts/run.py --dev-cookie
```

在另一个终端启动 `python scripts/run.py --worker --dev-cookie`。默认访问 `http://127.0.0.1:8080`。

```sh
python scripts/vendor_yatori.py
cd engine
go test ./...
cd ..
python -m pytest -q
```

## 维护与许可证

- [架构](docs/architecture.md)：模块边界、进程隔离和任务恢复。
- [Yatori 更新](UPSTREAM.md)：固定源码版本、受控补丁及更新门禁。
- [功能与设置](docs/yatori-features.md)：学习通功能、Yatori 设置对照和接口协议。
- [验证记录](docs/verification.md)：执行过的检查与真实环境验收范围。
- [第三方声明](THIRD_PARTY_NOTICES.md)：平台 GPL-3.0、Yatori MIT 和运行时许可证。

学习通接口因学校和课程类型而异。离线协议测试与本地服务验证记录见验证文档；真实账号的视频、文档、试卷答题及服务端回读需要按目标课程逐项验收。
