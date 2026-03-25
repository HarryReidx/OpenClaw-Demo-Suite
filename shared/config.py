from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    qwen_api_key: str
    qwen_base_url: str
    qwen_text_model: str
    qwen_vision_model: str
    tavily_api_key: str
    tavily_base_url: str
    app_host: str
    portal_port: int
    basic_qa_port: int
    memory_chat_port: int
    file_agent_port: int
    search_html_port: int
    mobile_openclaw_port: int
    rag_port: int
    ai_news_push_port: int
    wechat_webhook_url: str
    codex_home: Path
    codex_skills_dir: Path
    root_dir: Path
    data_dir: Path
    demo_outputs_dir: Path

    @property
    def ai_rag_port(self) -> int:
        return self.rag_port


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings(
        qwen_api_key=os.getenv("QWEN_API_KEY", "").strip(),
        qwen_base_url=os.getenv(
            "QWEN_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ).strip(),
        qwen_text_model=os.getenv("QWEN_TEXT_MODEL", "qwen-plus").strip(),
        qwen_vision_model=os.getenv("QWEN_VISION_MODEL", "qwen-vl-plus").strip(),
        tavily_api_key=os.getenv("TAVILY_API_KEY", "").strip(),
        tavily_base_url=os.getenv("TAVILY_BASE_URL", "https://api.tavily.com").strip().rstrip("/"),
        app_host=os.getenv("APP_HOST", "0.0.0.0").strip(),
        portal_port=int(os.getenv("PORTAL_PORT", "8000")),
        basic_qa_port=int(os.getenv("BASIC_QA_PORT", "8101")),
        memory_chat_port=int(os.getenv("MEMORY_CHAT_PORT", "8102")),
        file_agent_port=int(os.getenv("FILE_AGENT_PORT", "8103")),
        search_html_port=int(os.getenv("SEARCH_HTML_PORT", "8104")),
        mobile_openclaw_port=int(os.getenv("MOBILE_OPENCLAW_PORT", "8105")),
        rag_port=int(os.getenv("RAG_PORT", "8107")),
        ai_news_push_port=int(os.getenv("AI_NEWS_PUSH_PORT", "8106")),
        wechat_webhook_url=os.getenv("WECHAT_WEBHOOK_URL", "").strip(),
        codex_home=Path(os.getenv("CODEX_HOME", str(Path.home() / ".codex"))),
        codex_skills_dir=Path(os.getenv("CODEX_HOME", str(Path.home() / ".codex"))) / "skills",
        root_dir=ROOT_DIR,
        data_dir=ROOT_DIR / "data",
        demo_outputs_dir=ROOT_DIR / "demo_outputs",
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.demo_outputs_dir.mkdir(parents=True, exist_ok=True)
    settings.codex_home.mkdir(parents=True, exist_ok=True)
    settings.codex_skills_dir.mkdir(parents=True, exist_ok=True)
    return settings


def require_api_key() -> None:
    if not get_settings().qwen_api_key:
        raise RuntimeError("QWEN_API_KEY is missing. Please configure .env first.")
