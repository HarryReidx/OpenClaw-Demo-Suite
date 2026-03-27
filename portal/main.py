from __future__ import annotations

import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.config import get_settings


settings = get_settings()
app = FastAPI(title="AI深入浅出小龙虾")
templates = Jinja2Templates(directory=str(settings.root_dir / "portal" / "templates"))
app.mount("/static", StaticFiles(directory=str(settings.root_dir / "portal" / "static")), name="static")


DEMO_APPS = [
    ("01", "最简单 LLM 一问一答", settings.basic_qa_port, "先让大家看到 prompt 到 response 的最基础形态。"),
    ("02", "带记忆的多轮对话", settings.memory_chat_port, "让上下文被保留，体验模型记住前后文后的变化。"),
    ("03", "可以新建文件并写文案的 Agent", settings.file_agent_port, "演示 Agent 调用本地工具执行写作任务。"),
    ("04", "联网搜索并生成网页报告", settings.search_html_port, "让 Agent 先去互联网上找资料，再交付一个可展示的网页报告。"),
    ("05", "AI 资讯定时推送", settings.ai_news_push_port, "演示立即获取、企业微信推送和定时刷新能力。"),
    ("06", "上传文档的知识库 RAG", settings.rag_port, "上传文档、检索片段，再让大模型基于资料回答。"),
    ("07", "模拟 OpenClaw 综合工作台", settings.mobile_openclaw_port, "把记忆、RAG、联网搜索、看图和定时任务整合到最终演示位。"),
]


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"apps": DEMO_APPS, "host": request.url.hostname or "localhost"},
    )


if __name__ == "__main__":
    uvicorn.run(app, host=settings.app_host, port=settings.portal_port)
