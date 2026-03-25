from __future__ import annotations

import json
import asyncio
import sys
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.config import get_settings
from shared.db import load_messages, save_message
from shared.qwen_client import chat_completion, stream_chat_completion


class SessionResponse(BaseModel):
    session_id: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


def _format_sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _chunk_text(text: str, chunk_size: int = 32) -> list[str]:
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def _build_conversation(session_id: str) -> list[dict[str, str]]:
    history_items = load_messages(APP_NAME, session_id, limit=14)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend({"role": item["role"], "content": item["content"]} for item in history_items)
    return messages


def _serialize_history(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"role": item["role"], "content": item["content"]} for item in items]


settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
APP_NAME = "memory-chat"
SYSTEM_PROMPT = (
    "你是公司内部演示用的中文助手。你需要根据多轮上下文连续回答，"
    "对之前提到的人名、偏好、目标要保持记忆感。回答清晰、自然。"
)

app = FastAPI(title="02. 带记忆的多轮对话")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})


@app.post("/api/session", response_model=SessionResponse)
async def create_session() -> SessionResponse:
    return SessionResponse(session_id=str(uuid.uuid4()))


@app.get("/api/history/{session_id}")
async def history(session_id: str) -> dict[str, list[dict[str, str]]]:
    items = load_messages(APP_NAME, session_id, limit=20)
    return {"messages": [{"role": item["role"], "content": item["content"]} for item in items]}


@app.post("/api/chat-stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    session_id = payload.session_id.strip()
    message = payload.message.strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="缺少 session_id")
    if not message:
        raise HTTPException(status_code=400, detail="请输入消息")

    save_message(APP_NAME, session_id, "user", message)

    async def event_stream():
        try:
            conversation = _build_conversation(session_id)
            answer = ""
            stream = await run_in_threadpool(
                lambda: stream_chat_completion(conversation, temperature=0.5)
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if not delta:
                    continue
                answer += delta
                yield _format_sse("delta", {"delta": delta})
                await asyncio.sleep(0)
            save_message(APP_NAME, session_id, "assistant", answer)
            full_history = load_messages(APP_NAME, session_id, limit=20)
            yield _format_sse("done", {"messages": _serialize_history(full_history)})
        except Exception as exc:
            yield _format_sse("error", {"detail": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat")
async def chat(payload: ChatRequest) -> dict[str, object]:
    session_id = payload.session_id.strip()
    message = payload.message.strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="缺少 session_id。")
    if not message:
        raise HTTPException(status_code=400, detail="请输入消息。")

    save_message(APP_NAME, session_id, "user", message)
    history_items = load_messages(APP_NAME, session_id, limit=14)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(
        {"role": item["role"], "content": item["content"]}
        for item in history_items
    )

    try:
        response = chat_completion(messages, temperature=0.5)
        answer = response.choices[0].message.content or ""
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"大模型调用失败: {exc}") from exc

    save_message(APP_NAME, session_id, "assistant", answer)
    full_history = load_messages(APP_NAME, session_id, limit=20)
    return {
        "answer": answer,
        "messages": [{"role": item["role"], "content": item["content"]} for item in full_history],
    }


if __name__ == "__main__":
    uvicorn.run(app, host=settings.app_host, port=settings.memory_chat_port)
