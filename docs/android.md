# Android 本地服务版

APK 将 Vue 控制台、FastAPI、Python Worker 与 Yatori Go 核心打包到安卓设备。安装并启动后，同一局域网中的手机或电脑通过浏览器管理账号、课程和任务。浏览器关闭后，任务由安卓前台服务继续执行。

## 设备要求

- Android 8.0 / API 26 及以上。
- ARM 32 位 `armeabi-v7a` 或 ARM 64 位 `arm64-v8a`。同一个 device APK 包含这两种架构。
- 可写的应用私有存储、可用的 AndroidKeyStore、允许安装自有 APK。
- 设备连接 Wi-Fi、以太网或开启热点，管理端可以访问设备的私网地址。

应用常规运行使用安卓应用权限。中兴 U30 Air 的系统版本、固件后台限制和实际可用内存以设备为准；建议任务并发保持默认的 1。通过 UFI Tool 的终端可以查询：

```sh
getprop ro.build.version.release
getprop ro.build.version.sdk
getprop ro.product.cpu.abilist
```

## 安装与首次管理

1. 安装签名的 device APK，打开「学习通管理台」。
2. 点击「启动服务」，允许通知，并在系统电池设置中允许应用持续后台运行。
3. 手机或电脑连接同一局域网，在浏览器访问应用显示的 `http://设备IP:8080`。
4. 点击应用的「查看初始化令牌」，在网页首次初始化时填写，并创建管理员账号。以后使用管理员账号登录。

管理入口使用局域网 HTTP，适用于可信的家庭网络或个人热点。登录 Cookie 使用 HttpOnly / SameSite；账号凭据、学习通 Cookie 和 AI Key 在数据库中加密，数据主密钥由 AndroidKeyStore 保护。初始化令牌只在本机界面或设备所有者终端显示，管理 API 需要管理员鉴权和写操作校验。网络访问检查实际连接来源，只接受私网、链路本地和回环地址。

设备地址改变后，使用应用显示的新地址访问。首次初始化完成后，妥善保管管理员密码与设备访问权限。

## U30 Air 与 UFI Tool 终端

在 UFI Tool 提供的安卓终端中，进入有权限的 shell 后可以安装并打开应用。文件路径按实际上传位置调整：

```sh
pm install -r /sdcard/Download/chaoxing-console-0.5.2.apk
am start -n cn.zrmug.chaoxing/.MainActivity --ez start_service true
```

服务启动后，Root 或 ADB shell 可读取本机状态、局域网地址、HTTP 端口和初始化令牌：

```sh
content call --uri content://cn.zrmug.chaoxing.device --method status
```

根据返回的地址和端口，在浏览器中打开 `http://设备IP:8080`。终端输出含初始化令牌，请只在自己的管理终端查看。可以设置开机恢复：

```sh
content call --uri content://cn.zrmug.chaoxing.device --method auto_start --arg true
```

应用仅在用户已启动服务、开启开机恢复的情况下响应开机广播。固件可能限制开机广播、前台服务、锁屏联网或后台应用；这些行为需要在 U30 Air 上验收。系统「强行停止」后，需要手动打开应用。重启后的首次解锁也可能是访问应用加密存储的前提。

## 数据与升级

账号、加密会话、任务、进度与日志保存在应用私有目录。Worker 使用 SQLite 持久化状态，重启后进入恢复核对流程，学习通服务端确认状态与本地状态分别保存。每次账号操作租用独立安卓进程，结束时销毁该进程。

升级使用同一应用 ID、同一签名证书的 APK 覆盖安装；先停止服务再升级，数据会保留。卸载、清除应用数据会删除记录和密钥。应用自动备份已关闭，单独复制数据库不能在另一设备恢复 AndroidKeyStore 密钥。当前版本应通过网页查看记录，迁移或重置设备前先保留所需信息。

首次交付的本地签名密钥保存在构建电脑的 `android/.signing/`，不进入 Git 仓库。维护者应离线备份整个签名目录，包括密钥库和口令文件；后续分发使用同一签名。GitHub Actions 产物标为 unsigned，经过发布签名后才能安装。

## 源码构建

需要 JDK 17、Android SDK 35、NDK 30.0.16248370、Go 1.27、完整 Python 3.11（含 `venv`）和 Node.js 22。设置 `JAVA_HOME`、`ANDROID_HOME`、`ANDROID_NDK_HOME` 后执行：

```sh
npm --prefix frontend ci
npm --prefix frontend run build
python scripts/vendor_yatori.py
python scripts/collect_go_licenses.py
python scripts/build_android_engine.py
android/gradlew -p android :app:assembleDeviceRelease :app:testDeviceReleaseUnitTest
```

Windows 使用 `android/gradlew.bat`。`CHAOXING_BUILD_PYTHON` 可指定构建用 Python 3.11；`SOURCE_URL` 可设置本次构建的源码页面。Go 工具版本固定在 `engine/go.mod`，Yatori 原生库由脚本生成到 `android/app/libs/`，包含 ARM32、ARM64 与 x86_64。

Windows 的工作目录含中文且 JDK 测试进程无法读取类路径时，可给 Gradle 传入 `-PconsoleBuildRoot=C:/CodexBuild/chaoxing`，把中间产物和测试类输出到该目录。APK 随之输出到该目录的 `app/outputs/apk/`。

应用前台服务运行 Web/Worker，独立账号服务加载 Go 库处理匿名管道 RPC。账号服务结束时销毁进程，确认死亡后复用。Python 服务依赖独立固定在 `android/requirements.txt`。

APK 包含平台 GPL-3.0、Yatori MIT、Go、Python、Chaquopy 和前端组件许可证。发布签名 APK 时同时提供对应完整源码与构建说明，签名密钥独立备份。

Gradle 生成的 release APK 为 unsigned。分发前使用 Android SDK 的 `apksigner` 和维护者密钥签名，再执行 `apksigner verify --verbose --print-certs <已签名APK>` 核对签名。覆盖升级的证书必须与已安装版本一致。
