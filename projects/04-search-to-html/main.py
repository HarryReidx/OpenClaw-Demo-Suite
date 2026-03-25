from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.config import get_settings
from shared.qwen_client import simple_chat
from shared.search import search_web
from shared.tools import execute_demo_tool


class ReportRequest(BaseModel):
    query: str


settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
REPORTS_DIR = settings.demo_outputs_dir / "search-reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="04. 联网检索并生成网页报告")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/reports", StaticFiles(directory=str(REPORTS_DIR)), name="reports")


def _report_slug(query: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", query).strip("-")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{slug[:24] or 'report'}-{timestamp}.html"


def _recent_reports(limit: int = 6) -> list[dict[str, str]]:
    files = [path for path in REPORTS_DIR.glob("*.html") if path.is_file()]
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return [
        {
            "name": path.name,
            "url": f"/reports/{path.name}",
            "updated_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for path in files[:limit]
    ]


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"reports": _recent_reports()})


@app.get("/api/reports")
async def list_reports() -> dict[str, list[dict[str, str]]]:
    return {"reports": _recent_reports()}


@app.post("/api/generate")
async def generate_report(payload: ReportRequest) -> dict[str, object]:
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入搜索主题。")

    results = search_web(query, max_results=6)
    if not results:
        raise HTTPException(status_code=502, detail="没有抓到可用搜索结果，请稍后重试。")

    prompt_lines = [
        "你是公司内部 AI 研究助理。",
        "请基于以下联网搜索结果，输出一段适合内部分享的中文摘要，结构必须包含：",
        "1. 三句话概览",
        "2. 值得分享的 3 个重点",
        "3. 风险或不确定性提醒",
        "不要编造未提供的事实。",
        "",
        f"查询主题：{query}",
        "",
        "搜索结果：",
    ]
    for item in results:
        prompt_lines.append(f"- 标题：{item.title}")
        prompt_lines.append(f"  摘要：{item.snippet}")
        prompt_lines.append(f"  链接：{item.url}")
    try:
        summary = simple_chat(
            "\n".join(prompt_lines),
            system_prompt="你擅长把零散网页信息整理成适合公司同事阅读的中文简报。",
            temperature=0.3,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"大模型生成摘要失败: {exc}") from exc

    rendered_html = templates.get_template("report_template.html").render(
        query=query,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        summary=summary,
        results=results,
    )

    filename = _report_slug(query)
    tool_result = execute_demo_tool(
        "write_demo_html",
        {"filename": f"search-reports/{filename}", "html": rendered_html},
    )
    report_url = f"/reports/{filename}"
    saved_path = str(Path(tool_result["path"]).resolve().relative_to(settings.root_dir))

    activities = [
        {"label": "分析用户需求", "status": "done", "detail": f"已理解：{query}"},
        {"label": "调用 web search", "status": "done", "detail": f"获取 {len(results)} 条结果"},
        {"label": "整理总结内容", "status": "done", "detail": "生成面向管理层的速读总结"},
        {"label": "生成页面", "status": "done", "detail": f"写入 {report_url} 并保存"},
    ]
    skills = ["联网搜索", "报告撰写"]
    return {
        "query": query,
        "summary": summary,
        "saved_path": saved_path,
        "report_url": report_url,
        "results": [item.__dict__ for item in results],
        "reports": _recent_reports(),
        "activities": activities,
        "skills": skills,
    }


if __name__ == "__main__":
    uvicorn.run(app, host=settings.app_host, port=settings.search_html_port)
