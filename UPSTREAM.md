# Yatori 来源与构建

0.6.1 运行 [yatori-dev/yatori-go-console](https://github.com/yatori-dev/yatori-go-console/tree/017711107803f5232fea59446a5b8c801d4ca8b2) 的固定提交 `017711107803f5232fea59446a5b8c801d4ca8b2`。原版主程序与学习逻辑保存在 `third_party/yatori-go-console/`，共 45 个运行所需文件；逐文件 SHA-256 见 `engine/original-console.json`。

Core 使用原版 `go.mod` 的 `v0.0.0-20261020163355-ddf52f884145`。依赖通过 Go 模块校验下载。Console / Core 为 MIT，版权 Copyright (c) 2023 ChangBaiQi。

## Android 兼容

构建脚本 `scripts/build_original_console.py` 先核对原版源码，再将 `engine/console_bridge/query.go` 加入临时构建目录。学习任务进入原版 `main()`；查询模式由额外入口调用原版登录与 Core 聚合函数。管理进程存活监测用于服务退出时结束子进程。

原版 OCR 依赖 `github.com/Changbaiqi/ddddocr-go` 固定为 `v0.1.5-0.20251217103242-1896343369f8`。脚本在构建副本中选择 Android 资源。三份原版 OCR 模型逐字节校验后打包到共享资源目录，由 `YATORI_MODEL_DIR` 提供读取位置；ONNX 通过 `YATORI_ONNX_LIBRARY` 从安装目录加载。Android 库为 Microsoft ONNX Runtime 1.22.0（API 22），AAR 的 SHA-256 固定在来源清单中。Core 初始化的构建副本移除 `tencentCollect.exe` 和 `tencentPowSolve.exe` 的嵌入与释放条目；这两个 Windows 工具由 ICVE 专用验证代码调用。学习通业务文件与 Console 主程序保持原版。资源适配输入和模型哈希见 `engine/android-resources.json`，Android OCR 加载入口见 `engine/android_resources/ocr_init.go`。所有适配只修改临时构建副本。

OCR 模块的该提交未附独立许可证文件；该事实与源码地址保存在 `engine/licenses/ORIGINAL_CONSOLE_LICENSES.txt`。ONNX 的 MIT 和第三方声明保存在 `android/licenses/onnxruntime-*`。

## 校验与更新

```sh
python scripts/build_original_console.py --verify
python scripts/build_original_console.py
python scripts/collect_go_licenses.py --original
```

更新时核对上游提交与依赖，重新生成原版源码清单，在 Android 上执行初始化、查询、日志和进程停止测试，并在目标账号验收课程行为。构建输出的每个 ABI 哈希见 `artifacts/original-console-build.json`。

历史 0.5.x 的 API 适配来源与哈希保留在 `engine/upstream.json` 和 `engine/console-upstream.json`，相应回归样本保留用于兼容研究。
