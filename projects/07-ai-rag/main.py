from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.config import get_settings
from shared.qwen_client import simple_chat
from shared.rag import RAG_DIR, add_document, extract_text_from_file, get_document, list_documents, search_chunks


settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = RAG_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="07. AI 知识库 RAG")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"documents": list_documents()})


@app.get("/api/documents")
async def documents() -> dict[str, object]:
    return {"documents": list_documents()}


@app.get("/api/documents/{doc_id}")
async def document_detail(doc_id: str) -> dict[str, object]:
    document = get_document(doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"document": document}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict[str, object]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".txt", ".md", ".docx"}:
        raise HTTPException(status_code=400, detail="仅支持 txt、md、docx。")
    save_name = f"{uuid4().hex}{suffix}"
    saved_path = UPLOADS_DIR / save_name
    saved_path.write_bytes(await file.read())
    try:
        text = extract_text_from_file(saved_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"文档解析失败: {exc}") from exc
    document = add_document(file.filename or save_name, text)
    return {
        "document": {
            "doc_id": document["doc_id"],
            "file_name": document["file_name"],
            "chunk_count": document["chunk_count"],
        },
        "documents": list_documents(),
    }


@app.post("/api/ask")
async def ask(question: str = Form(...)) -> dict[str, object]:
    query = question.strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入问题。")
    chunks = search_chunks(query, top_k=4)
    if not chunks:
        return {
            "answer": "知识库里暂时没有检索到相关内容。你可以先上传一份文档，再试试提问。",
            "citations": [],
        }
    context = "\n\n".join(
        f"[{idx + 1}] 文件：{chunk['file_name']}\n内容：{chunk['content']}"
        for idx, chunk in enumerate(chunks)
    )
    prompt = "\n".join(
        [
            "请严格基于以下知识库片段回答问题。",
            "如果片段里没有答案，就明确说明“根据当前上传文档无法确定”。",
            "",
            f"问题：{query}",
            "",
            "知识库片段：",
            context,
        ]
    )
    try:
        answer = await run_in_threadpool(
            simple_chat,
            prompt,
            system_prompt="你是公司内部知识库助手，回答要简洁、可信、基于文档。",
            temperature=0.2,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"大模型调用失败: {exc}") from exc
    return {"answer": answer, "citations": chunks}


if __name__ == "__main__":
    uvicorn.run(app, host=settings.app_host, port=settings.ai_rag_port)
