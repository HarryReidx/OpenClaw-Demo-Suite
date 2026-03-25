from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from uuid import uuid4

from docx import Document

from shared.config import get_settings


RAG_DIR = get_settings().data_dir / "rag"
RAG_DIR.mkdir(parents=True, exist_ok=True)
RAG_INDEX_PATH = RAG_DIR / "documents.json"


def _load_index() -> list[dict]:
    if not RAG_INDEX_PATH.exists():
        return []
    return json.loads(RAG_INDEX_PATH.read_text(encoding="utf-8"))


def _save_index(items: list[dict]) -> None:
    RAG_INDEX_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_text_from_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".docx":
        doc = Document(str(path))
        return "\n".join(paragraph.text for paragraph in doc.paragraphs)
    raise ValueError(f"暂不支持的文件类型: {suffix}")


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 80) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def add_document(file_name: str, raw_text: str) -> dict:
    items = _load_index()
    doc_id = uuid4().hex
    chunks = chunk_text(raw_text)
    document = {
        "doc_id": doc_id,
        "file_name": file_name,
        "chunk_count": len(chunks),
        "chunks": [{"chunk_id": f"{doc_id}-{i}", "content": chunk} for i, chunk in enumerate(chunks)],
    }
    items.append(document)
    _save_index(items)
    return document


def list_documents() -> list[dict]:
    items = _load_index()
    return [
        {
            "doc_id": item["doc_id"],
            "file_name": item["file_name"],
            "chunk_count": item["chunk_count"],
        }
        for item in reversed(items)
    ]


def get_document(doc_id: str) -> dict | None:
    for item in _load_index():
        if item["doc_id"] != doc_id:
            continue
        return {
            "doc_id": item["doc_id"],
            "file_name": item["file_name"],
            "chunk_count": item["chunk_count"],
            "content": _merge_document_chunks(item.get("chunks", [])),
            "chunks": [
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "index": index + 1,
                    "content": chunk.get("content", ""),
                }
                for index, chunk in enumerate(item.get("chunks", []))
            ],
        }
    return None


def delete_document(doc_id: str) -> bool:
    items = _load_index()
    filtered = [item for item in items if item["doc_id"] != doc_id]
    if len(filtered) == len(items):
        return False
    _save_index(filtered)
    return True


def search_chunks(query: str, top_k: int = 4) -> list[dict]:
    query_terms = _terms(query)
    scored: list[tuple[int, dict]] = []
    documents = _load_index()
    if not query_terms:
        return [
            {
                "doc_id": document["doc_id"],
                "file_name": document["file_name"],
                "chunk_id": chunk["chunk_id"],
                "content": chunk["content"],
                "score": 0,
            }
            for document in documents
            for chunk in document["chunks"][:1]
        ][:top_k]

    for document in documents:
        for chunk in document["chunks"]:
            content_terms = _terms(chunk["content"])
            score = _overlap_score(query_terms, content_terms)
            if score <= 0:
                continue
            scored.append(
                (
                    score,
                    {
                        "doc_id": document["doc_id"],
                        "file_name": document["file_name"],
                        "chunk_id": chunk["chunk_id"],
                        "content": chunk["content"],
                        "score": score,
                    },
                )
            )
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored:
        return [item[1] for item in scored[:top_k]]
    return [
        {
            "doc_id": document["doc_id"],
            "file_name": document["file_name"],
            "chunk_id": chunk["chunk_id"],
            "content": chunk["content"],
            "score": 0,
        }
        for document in documents
        for chunk in document["chunks"][:1]
    ][:top_k]


def _terms(text: str) -> Counter:
    normalized = text.lower()
    tokens = re.findall(r"[a-zA-Z0-9_]+", normalized)
    chinese_spans = re.findall(r"[\u4e00-\u9fff]+", normalized)
    for span in chinese_spans:
        tokens.extend(list(span))
        if len(span) > 1:
            tokens.extend(span[i : i + 2] for i in range(len(span) - 1))
        if len(span) > 2:
            tokens.extend(span[i : i + 3] for i in range(len(span) - 2))
    return Counter(tokens)


def _overlap_score(query_terms: Counter, content_terms: Counter) -> int:
    score = 0
    for token, count in query_terms.items():
        score += min(count, content_terms.get(token, 0))
    return score


def _merge_document_chunks(chunks: list[dict], overlap: int = 80) -> str:
    if not chunks:
        return ""
    merged = chunks[0].get("content", "")
    for chunk in chunks[1:]:
        content = chunk.get("content", "")
        if overlap > 0 and len(merged) >= overlap and content.startswith(merged[-overlap:]):
            merged += content[overlap:]
            continue
        merged += content
    return merged.strip()
