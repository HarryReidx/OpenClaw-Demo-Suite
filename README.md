# OpenClaw For Tsingyun

这是一个用于公司内部演示的大模型与 Agent 能力的渐进式项目集合。整套仓库统一使用 `Python + FastAPI + Jinja2 + vanilla JS + SQLite + Qwen(OpenAI兼容接口)`，并拆成 7 个可以独立讲解的子工程。

## 子工程

1. `projects/01-basic-qa`
   最简单的 LLM 一问一答。
2. `projects/02-memory-chat`
   带会话记忆的多轮对话。
3. `projects/03-file-agent`
   可以调用工具在本地创建文件并写入文案的 Agent。
4. `projects/04-search-to-html`
   从互联网抓取信息，自动生成网页报告。
5. `projects/05-mobile-openclaw`
   手机友好的 OpenClaw 风格工作台，支持图片理解。
6. `projects/06-ai-news-push`
   定时抓取 AI 资讯并通过企业微信 webhook 推送的演示模块。
7. `projects/07-ai-rag`
   上传简单文档并基于知识库问答的 RAG 演示。

## 快速启动

```powershell
.\launch_all.ps1
```

启动后访问：

- 演示总入口: `http://127.0.0.1:8000/`
- 也可以把 `127.0.0.1` 换成你的局域网 IP，在手机或局域网其他设备上访问。

## 环境变量

项目使用根目录 `.env` 读取配置。默认已经按本次需求写入大模型接口和企业微信 webhook 配置。如果这个仓库要被分享，请务必替换或轮换密钥。

## 共享底座

- `shared/config.py`: 环境变量与目录配置
- `shared/qwen_client.py`: 文本、多模态、工具调用封装
- `shared/db.py`: SQLite 持久化
- `shared/tools.py`: 安全的演示版文件写入工具
- `shared/search.py`: 联网搜索
- `shared/news.py`: AI 资讯聚合
- `shared/scheduler.py`: 定时任务
- `shared/rag.py`: 简单知识库索引与召回

