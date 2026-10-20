# Yatori 上游更新

执行核心来自 [yatori-dev/yatori-go-core](https://github.com/yatori-dev/yatori-go-core)，固定提交为 `cf6134fdb2bd0640758216d03c947a2a13b2b16a`。上游采用 MIT 许可证，版权为 Copyright (c) 2023 ChangBaiQi。

## 源码与边界

`third_party/yatori-go-core/` 保存学习通 API 所需的源码依赖闭包。`engine/upstream.json` 记录提交、每个原文件的 SHA-256 和编入版本的 SHA-256。`scripts/vendor_yatori.py` 校验文件清单和字节；文本统一 LF 后比较。

平台在 API 请求出口安装请求策略，统一校验 HTTPS 目标、超时、重定向、人工验证与错误分类。导入脚本将 API 的客户端发送调用接到 `platform_transport.go`。桌面资源初始化文件通过构建约束排除，平台独立初始化账号运行时。其余上游源码按原样保留。

`engine/runtime/` 将上游 API 和任务 DTO 转换为平台任务接口，负责实时视频推进及完成状态回读所需的数据。Web、数据库和 Worker 通过 JSON RPC 调用执行进程。

## 更新流程

先备份数据和密钥，在独立开发分支中检出已审核的上游提交：

```sh
git clone https://github.com/yatori-dev/yatori-go-core.git .research/yatori-go-core
git -C .research/yatori-go-core checkout <已审核的提交SHA>
python scripts/vendor_yatori.py --source .research/yatori-go-core --commit <已审核的提交SHA>
python scripts/build_engine.py
cd engine
go test ./...
go test github.com/yatori-dev/yatori-go-core/api/xuexitong
cd ..
python -m pytest -q
npm --prefix frontend run build
```

导入前校验当前固定版本；本地存在未记录的源码改动时停止，供维护者先检查差异。审核 `third_party/`、`engine/upstream.json` 和 Go 依赖锁文件的变化，再更新脱敏样本。新增学习通 API 调用须经过请求策略；校验具体的服务端完成依据和所需 Cookie 范围。

Android 更新还需运行 `scripts/build_android_engine.py`，构建 APK 并执行原生、HTTP、账号隔离和服务重启测试。`gomobile` 工具版本固定在 `engine/go.mod`。分发时保留许可证和完整对应源码包。

维护者使用授权账号验证少量课程的登录、章节、视频续学、文档和状态回读，并将课程类型与验证结果记入发布说明。遇到验证码和人工限制时保留人工处理状态。
