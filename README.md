# OpenClaw For Tsingyun

面向公司内部演示的多阶段 AI / Agent 示例仓库。

项目统一使用 `Python + FastAPI + Jinja2 + SQLite`，当前包含 portal 和 `01-07` 七个演示模块，并补充了 Android APK、Docker 镜像、Harbor 发布和服务器部署文件。

## 模块说明

1. `portal`
   演示总入口，默认端口 `8100`
2. `projects/01-basic-qa`
   基础问答，默认端口 `8101`
3. `projects/02-memory-chat`
   带会话记忆的多轮对话，默认端口 `8102`
4. `projects/03-file-agent`
   Agent 调工具写本地文件，默认端口 `8103`
5. `projects/04-search-to-html`
   联网检索并生成报告页，默认端口 `8104`
6. `projects/05-mobile-openclaw`
   综合工作台，支持图片理解、RAG、联网搜索、定时任务和无头浏览器操作，默认端口 `8105`
7. `projects/06-ai-news-push`
   AI 资讯获取与推送，默认端口 `8106`
8. `projects/07-ai-rag`
   文档上传与知识库问答，默认端口 `8107`

## 关键变更

- 默认模型接入已切换到 `172.24.0.5` 上的 Ollama
  - 文本模型：`qwen3:8b`
  - 视觉模型：`qwen2.5vl:7b`
- 已提供统一 Docker 镜像和 Harbor 部署编排
- portal 的 `07` 改为 APK 下载入口，不再从 portal 直接打开网页
- Android 发布包名称与应用名称统一为 `🦞小清虾`
- `05` 中涉及网页访问、登录、点击、读取页面内容的任务，统一走无头浏览器执行
- 针对“基模 / 模型 / 厂商 / 供应商”等问题，统一通过系统提示引导自然回复：
  - 本系统由清云智通武汉研发中心设计、研发并提供

## 本地启动

### Python 服务

```powershell
.\launch_all.ps1
```

默认访问地址：

- portal: `http://127.0.0.1:8000/`
- 局域网访问时，将 `127.0.0.1` 替换成实际 IP

### Android APK

Android 工程目录：

- `android-openclaw-webview`

构建 release APK：

```powershell
cd D:\1-workspace\6-ai\openclaw-dev\android-openclaw-webview
D:\3-env\gradle-8.5\bin\gradle.bat --no-daemon assembleRelease -POPENCLAW_BASE_URL=http://172.24.0.5:8105
```

APK 输出：

- `android-openclaw-webview/app/build/outputs/apk/release/app-release.apk`
- portal 下载文件：`portal/static/download/🦞小清虾.apk`

## Docker 与 Harbor

### 主要文件

- `Dockerfile`
- `.dockerignore`
- `docker/start_app.py`
- `docker-compose.harbor.yml`
- `harbor.env.example`

### 镜像命名

- `harbor.tsingyun.net/platform/ai-openclaw-dev-portal:1.0`
- `harbor.tsingyun.net/platform/ai-openclaw-dev-01:1.0`
- `harbor.tsingyun.net/platform/ai-openclaw-dev-02:1.0`
- `harbor.tsingyun.net/platform/ai-openclaw-dev-03:1.0`
- `harbor.tsingyun.net/platform/ai-openclaw-dev-04:1.0`
- `harbor.tsingyun.net/platform/ai-openclaw-dev-05:1.0`
- `harbor.tsingyun.net/platform/ai-openclaw-dev-06:1.0`
- `harbor.tsingyun.net/platform/ai-openclaw-dev-07:1.0`

### 服务器端口规划

- `8100` -> portal
- `8101` -> 01
- `8102` -> 02
- `8103` -> 03
- `8104` -> 04
- `8105` -> 05
- `8106` -> 06
- `8107` -> 07

### 服务器部署

将以下文件放到服务器部署目录：

- `docker-compose.harbor.yml`
- `.env`（可由 `harbor.env.example` 复制）

示例命令：

```bash
docker login harbor.tsingyun.net -u admin
docker compose --env-file .env -f docker-compose.harbor.yml pull
docker compose --env-file .env -f docker-compose.harbor.yml up -d
```

## 重要说明

- `07` 在 portal 中只提供 APK 下载入口
- portal 中 `07` 已标注“暂不支持 iPhone 用户”
- 如果需要重新发布 APK，建议先打包再覆盖 `portal/static/download/🦞小清虾.apk`
- 如果需要重新发布镜像，重新 `docker build` 并推送 Harbor 即可

## 共享基础能力

- `shared/config.py`
  环境变量和目录配置
- `shared/qwen_client.py`
  文本、视觉、工具调用封装
- `shared/browser.py`
  无头浏览器访问、登录和页面读取
- `shared/db.py`
  SQLite 持久化
- `shared/search.py`
  联网搜索
- `shared/news.py`
  AI 新闻聚合与推送
- `shared/rag.py`
  简单知识库索引与检索
