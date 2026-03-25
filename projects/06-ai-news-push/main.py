from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.db import list_news_items
from shared.news import build_ai_digest, build_ai_digest_markdown, push_ai_digest_to_wechat, refresh_ai_digest
from shared.scheduler import ensure_interval_job, get_scheduler


class ToggleScheduleRequest(BaseModel):
    enabled: bool


BASE_DIR = Path(__file__).resolve().parent
SCHEDULE_STATE_PATH = ROOT_DIR / "data" / "news_schedule_state.json"
JOB_ID = "scheduled-ai-news-refresh"

app = FastAPI(title="06. AI 资讯定时推送")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _load_schedule_state() -> dict[str, Any]:
    if not SCHEDULE_STATE_PATH.exists():
        return {"enabled": False, "last_action": "尚未操作"}
    return json.loads(SCHEDULE_STATE_PATH.read_text(encoding="utf-8"))


def _save_schedule_state(enabled: bool, last_action: str | None = None) -> None:
    state = _load_schedule_state()
    state["enabled"] = enabled
    if last_action is not None:
        state["last_action"] = last_action
    SCHEDULE_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _refresh_and_push() -> dict[str, Any]:
    digest = refresh_ai_digest(fetch_timeout=8.0)
    digest_markdown = build_ai_digest_markdown()
    push = push_ai_digest_to_wechat(digest_markdown)
    _save_schedule_state(_load_schedule_state().get("enabled", False), last_action=push["status"])
    return {
        "items": list_news_items(limit=12),
        "digest": digest,
        "digest_markdown": digest_markdown,
        "push_status": push["status"],
    }


@app.on_event("startup")
def startup() -> None:
    ensure_interval_job(JOB_ID, _refresh_and_push, hours=3)
    scheduler = get_scheduler()
    state = _load_schedule_state()
    if state.get("enabled"):
        scheduler.resume_job(JOB_ID)
    else:
        scheduler.pause_job(JOB_ID)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/api/state")
async def state() -> dict[str, Any]:
    schedule_state = _load_schedule_state()
    return {
        "items": list_news_items(limit=12),
        "digest": build_ai_digest(),
        "digest_markdown": build_ai_digest_markdown(),
        "push_status": schedule_state.get("last_action", "尚未操作"),
        "schedule_enabled": bool(schedule_state.get("enabled", False)),
    }


@app.post("/api/refresh")
async def refresh() -> dict[str, Any]:
    try:
        return await run_in_threadpool(_refresh_and_push)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"获取或推送失败：{exc}") from exc


@app.post("/api/schedule")
async def schedule(payload: ToggleScheduleRequest) -> dict[str, Any]:
    scheduler = get_scheduler()
    try:
        if payload.enabled:
            scheduler.resume_job(JOB_ID)
            _save_schedule_state(True, last_action="已开启定时刷新")
            return {"enabled": True, "status": "已开启定时刷新"}
        scheduler.pause_job(JOB_ID)
        _save_schedule_state(False, last_action="已关闭定时刷新")
        return {"enabled": False, "status": "已关闭定时刷新"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"切换定时任务失败：{exc}") from exc


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8106)
