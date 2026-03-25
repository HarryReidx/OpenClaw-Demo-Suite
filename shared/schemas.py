from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ChatTurn:
    role: str
    content: str
    created_at: datetime | None = None


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = ""


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    summary: str
    published_at: str
    tags: list[str] = field(default_factory=list)
    image_url: str = ""


@dataclass
class FileWriteRequest:
    filename: str
    content: str
    purpose: str = ""


@dataclass
class ToolExecutionResult:
    ok: bool
    message: str
    payload: dict[str, Any] = field(default_factory=dict)
