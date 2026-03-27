# Android Shell for OpenClaw Workbench

这个目录是给当前工程里的“模拟 OpenClaw 综合工作台”准备的独立安卓壳，不会影响现有 Python/FastAPI 代码。

## 方案

- 安卓端使用原生 `WebView` 封装现有 `projects/05-mobile-openclaw`
- 业务逻辑、知识库、定时任务、流式对话、图片理解仍然由现有 Python 服务提供
- App 首次启动会要求填写服务地址
- 真机通常填写：`http://你的电脑局域网IP:8105/`
- Android 模拟器默认可直接访问：`http://10.0.2.2:8105/`

## 已支持能力

- WebView 加载现有完整工作台
- HTTP 明文访问局域网服务
- 文件上传
- 图片选择与拍照
- WebView 返回栈
- 菜单内切换/重置服务地址

## 构建前提

1. 本机已安装 Android Studio 或 Android SDK
2. 当前仓库的 Python 服务可正常启动
3. 真机与电脑在同一局域网

## 本地启动现有服务

在仓库根目录运行：

```powershell
.\launch_all.ps1
```

如果只需要综合工作台，也可以直接运行：

```powershell
.\.venv\Scripts\python.exe .\projects\05-mobile-openclaw\main.py
```

## 构建 APK

在这个目录执行：

```powershell
gradle assembleDebug
```

构建产物默认位于：

`app\build\outputs\apk\debug\app-debug.apk`

## 备注

- 这是“安卓安装包封装”，不是把 Python 后端重写进 APK。
- 如果要做成完全离线、后端也内置到手机里的单包应用，需要单独把后端迁移到 Android 可运行栈，工作量和风险都会明显增加，不属于当前最快最稳路线。
