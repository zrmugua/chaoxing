# 代码来源与许可证

## 管理平台

管理平台按 GNU GPL version 3 分发，全文见根目录 `LICENSE`。Web 控制台、管理 API、任务调度、Yatori 适配及 Android 服务保留该许可证。分发安装包或镜像时随附完整对应源码、构建脚本、依赖声明和许可证。

项目开发历史始于 [zrmugua/chaoxing](https://github.com/zrmugua/chaoxing)，其源自 [Samueli924/chaoxing](https://github.com/Samueli924/chaoxing)。原项目采用 GPL-3.0。历史源码和原版权声明可由 Git 历史查阅。

## Yatori 执行核心

- 来源：[yatori-dev/yatori-go-core](https://github.com/yatori-dev/yatori-go-core)。
- 固定提交：`cf6134fdb2bd0640758216d03c947a2a13b2b16a`。
- 版权：Copyright (c) 2023 ChangBaiQi。
- 许可证：MIT，完整文本见 `third_party/yatori-go-core/LICENSE`。
- 编入源码清单、原始/编入文件哈希和受控请求出口调整见 `engine/upstream.json`、`scripts/vendor_yatori.py` 和 `UPSTREAM.md`。

APK 和镜像同时包含 Yatori 的 MIT 许可证。Yatori 的第三方 Go 依赖及 Go 标准库许可文本汇总为 `engine/licenses/THIRD_PARTY_GO_LICENSES.txt`，使用 `scripts/collect_go_licenses.py` 按实际链接包重新生成。

## 产品与界面参考

[yatori-dev/yatori-go-console](https://github.com/yatori-dev/yatori-go-console) 的提交 `017711107803f5232fea59446a5b8c801d4ca8b2` 用于 `engine/consolelogic/` 的学习通执行移植，版权为 Copyright (c) 2023 ChangBaiQi，MIT 许可。章测解析同时取自其 Core 提交 `ddf52f884145ba9ab7e2ac9e187ba36205eec6ce` 的业务函数。来源、选用函数与适配文件哈希见 `engine/console-upstream.json`；许可证见 `third_party/yatori-go-console/LICENSE` 和 `third_party/yatori-go-core/LICENSE`。

[yatori-dev/yatori-config-generate](https://github.com/yatori-dev/yatori-config-generate) 的提交 `f4aba3eb3ee53b54478461c964e6dd3929ada531` 用于研究学习通配置字段、表单流程与 YAML 格式。对应字段转换和控制台表单在本项目中实现。

[yatori-dev/yatori-go-android](https://github.com/yatori-dev/yatori-go-android) 的提交 `cb479146973ac7aca5abedf81dfc53fa4c5d298c` 用于学习通功能、规则配置和设置分组研究，采用 AGPL-3.0-or-later。其 Android 实现未纳入本项目源码；控制台及适配逻辑在本项目中实现。对照范围见 `docs/yatori-features.md`。

[userchengyang/chaoxing-platform-v2](https://github.com/userchengyang/chaoxing-platform-v2) 的提交 `da7a3f2819bb9d6e992652b78acf74ecec81235f` 用于 Web 产品形态、多账号和调度设计研究。其许可证为 GPL-3.0。

[zrmugua/newapi-scheduler](https://github.com/zrmugua/newapi-scheduler) 的提交 `75d4944d81ef8f913f0570c3f710968a3937108c` 用于控制台布局、主题和管理页面设计参考。本控制台使用 Vue 3 与 Naive UI 实现。

## 运行时依赖

Vue、Naive UI、Vite、FastAPI、Uvicorn、Cryptography、HTTPX 和 Filelock 等组件保留各自许可证。Python 依赖声明见 `requirements.txt` 和 `android/requirements.txt`，前端声明见 `frontend/package.json` 和锁文件。

前端生产依赖许可汇总为 `/assets/THIRD_PARTY_LICENSES.txt`，随网页和 APK 分发。Go 运行时和 gomobile 使用 BSD 许可证，其许可文本随原生库包含。Android 服务使用 Chaquopy 17.1（Copyright Chaquo Ltd and contributors，MIT）、Python 3.11（PSF）、Android Gradle Plugin、Gradle Wrapper 与 AndroidX Test（Apache-2.0）。对应声明保存在 `android/licenses/`。

APK 的「源代码与许可证」说明源码随包提供；构建者设置 `SOURCE_URL` 后可直接打开该构建源码页面。签名私钥和运行凭据独立于源码保存。

YAML 配置读写使用 PyYAML 6.0.3，MIT，Copyright (c) 2017-2021 Ingy döt Net；Copyright (c) 2006-2016 Kirill Simonov。完整许可文本见 `android/licenses/pyyaml-MIT.txt`，随安装包和源码分发。

Android PyYAML 依赖 LibYAML 0.2.5，MIT，Copyright (c) 2017-2020 Ingy döt Net；Copyright (c) 2006-2016 Kirill Simonov。完整许可文本见 `android/licenses/libyaml-MIT.txt`。
