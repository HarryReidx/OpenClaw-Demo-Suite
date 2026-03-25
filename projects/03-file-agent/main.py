from __future__ import annotations

import json
import re
import sys
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
from shared.qwen_client import chat_with_tools, simple_chat
from shared.tools import WRITE_FILE_TOOL, execute_demo_tool


class AgentTaskRequest(BaseModel):
    task: str


settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
APP_OUTPUT_DIR = settings.demo_outputs_dir / "file-agent"
APP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="03. 可写文件的 Agent")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _fallback_filename(task: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", task).strip("-")
    return f"file-agent/{clean[:24] or 'agent-output'}.md"


def _read_recent_files(limit: int = 8) -> list[dict[str, str]]:
    files = [path for path in APP_OUTPUT_DIR.rglob("*") if path.is_file()]
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    results: list[dict[str, str]] = []
    for path in files[:limit]:
        relative = path.relative_to(settings.root_dir)
        preview = path.read_text(encoding="utf-8", errors="ignore")[:180]
        results.append({"path": str(relative), "name": path.name, "preview": preview})
    return results


def _extract_saved_path(history: list[dict]) -> str | None:
    for item in reversed(history):
        if item.get("role") != "tool":
            continue
        try:
            payload = json.loads(item.get("content", "{}"))
        except json.JSONDecodeError:
            continue
        path = payload.get("path")
        if path:
            return str(Path(path).resolve().relative_to(settings.root_dir))
    return None


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"files": _read_recent_files()})


@app.get("/api/files")
async def list_files() -> dict[str, list[dict[str, str]]]:
    return {"files": _read_recent_files()}


@app.post("/api/run")
async def run_agent(payload: AgentTaskRequest) -> dict[str, object]:
    task = payload.task.strip()
    if not task:
        raise HTTPException(status_code=400, detail="请输入要交给 Agent 的任务。")

    messages = [
        {
            "role": "system",
            "content": (
                "你是公司内部演示用的 Agent。你的目标不是只回答，而是完成任务并把最终文案保存到本地文件。"
                "当用户让你写文案、通知、方案、总结、邮件或清单时，你必须调用 write_demo_file。"
                "文件名请放在 file-agent/ 目录下，使用清晰、简短的中文或英文文件名。"
                "工具执行完成后，再告诉用户你写了什么以及适合怎么用。"
            ),
        },
        {"role": "user", "content": task},
    ]

    try:
        answer, history = chat_with_tools(
            messages,
            tools=[WRITE_FILE_TOOL],
            executor=execute_demo_tool,
            temperature=0.2,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"大模型 Agent 调用失败: {exc}") from exc

    saved_path = _extract_saved_path(history)
    used_tool = bool(saved_path)

    if not saved_path:
        generated = simple_chat(
            f"请根据以下任务直接写出一份可交付文案，使用中文，结构清晰：\n\n{task}",
            system_prompt="你是资深内容策划，输出适合直接落盘的完整文案。",
            temperature=0.4,
        )
        saved_result = execute_demo_tool(
            "write_demo_file",
            {"filename": _fallback_filename(task), "content": generated},
        )
        saved_path = str(Path(saved_result["path"]).resolve().relative_to(settings.root_dir))
        answer = (
            "本轮模型没有显式触发工具调用，我已经按演示模式为你兜底完成了文件写入。\n\n"
            f"{generated[:240]}"
        )
        used_tool = False

    file_path = settings.root_dir / saved_path
    preview = file_path.read_text(encoding="utf-8", errors="ignore")[:500]
    activities = [
        {"label": "分析需求", "status": "done", "detail": "已确认用户任务与目标"},
        {
            "label": "调用写文件工具",
            "status": "done" if used_tool else "skipped",
            "detail": f"{'write_demo_file -> ' + saved_path if used_tool else 'simple_chat 生成并保存'}",
        },
        {"label": "生成交付说明", "status": "done", "detail": "整理答复并提供预览"},
    ]
    skills = ["写文件", "交付说明"]
    return {
        "answer": answer,
        "saved_path": saved_path,
        "preview": preview,
        "used_tool": used_tool,
        "files": _read_recent_files(),
        "activities": activities,
        "skills": skills,
    }


if __name__ == "__main__":
    uvicorn.run(app, host=settings.app_host, port=settings.file_agent_port)
