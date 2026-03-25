from __future__ import annotations

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
from shared.qwen_client import simple_chat


class AskRequest(BaseModel):
    prompt: str


settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="01. 最简单 LLM 一问一答")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})


@app.post("/api/ask")
async def ask(payload: AskRequest) -> dict[str, str]:
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="请输入问题。")
    try:
        answer = simple_chat(
            prompt,
            system_prompt="你是公司内部演示用的中文助手。回答清楚、直接、自然。",
            temperature=0.5,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"大模型调用失败: {exc}") from exc
    return {"answer": answer}


if __name__ == "__main__":
    uvicorn.run(app, host=settings.app_host, port=settings.basic_qa_port)
