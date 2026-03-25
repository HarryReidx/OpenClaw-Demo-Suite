from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Iterable

import feedparser
import httpx

from shared.config import get_settings
from shared.db import list_news_items, save_news_item
from shared.qwen_client import simple_chat
from shared.schemas import NewsItem


AI_FEEDS = [
    ("OpenAI", "https://openai.com/news/rss.xml"),
    ("Anthropic", "https://www.anthropic.com/news/rss.xml"),
    ("Google AI", "https://blog.google/technology/ai/rss/"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml"),
]

FALLBACK_FEEDS = [
    ("Google News / AI", "https://news.google.com/rss/search?q=AI&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
    ("Google News / OpenAI", "https://news.google.com/rss/search?q=OpenAI&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
    ("Google News / Qwen", "https://news.google.com/rss/search?q=Qwen&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
]


def _load_feed_entries(feed_url: str) -> Iterable:
    try:
        response = httpx.get(feed_url, timeout=4.0, follow_redirects=True)
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        return getattr(feed, "entries", [])
    except Exception:
        return []


def fetch_ai_news(limit_per_feed: int = 2, target_count: int = 8) -> list[NewsItem]:
    items: list[NewsItem] = []
    seen_urls: set[str] = set()
    for source, feed_url in [*AI_FEEDS, *FALLBACK_FEEDS]:
        entries = _load_feed_entries(feed_url)
        for entry in list(entries)[:limit_per_feed]:
            link = getattr(entry, "link", "")
            title = getattr(entry, "title", "")
            if not link or not title or link in seen_urls:
                continue
            seen_urls.add(link)
            raw_summary = getattr(entry, "summary", "") or title
            image_url = _extract_image_url(entry, raw_summary)
            clean_title = _localize_title(title)
            clean_summary = _localize_summary(_clean_summary(raw_summary), title=clean_title)
            item = NewsItem(
                title=clean_title,
                url=link,
                source=source,
                summary=clean_summary,
                published_at=getattr(entry, "published", "unknown"),
                tags=["AI", source],
                image_url=image_url,
            )
            save_news_item(
                item.title,
                item.url,
                item.source,
                item.summary,
                item.published_at,
                item.tags,
                image_url=item.image_url,
            )
            items.append(item)
            if len(items) >= target_count:
                return items
    return items


def build_ai_digest(limit: int = 6) -> str:
    items = list_news_items(limit=limit)
    if not items:
        return "当前还没有缓存到 AI 资讯。可以先点击“立即获取并推送”。"

    lines = ["今日 AI 早报", ""]
    for item in items[:limit]:
        lines.append(f"- {item['title']}")
        lines.append(f"  来源：{item['source']}")
        lines.append(f"  摘要：{item['summary']}")
        lines.append(f"  原文：{item['url']}")
        lines.append("")
    return "\n".join(lines).strip()


def build_ai_digest_markdown(limit: int = 5) -> str:
    items = list_news_items(limit=limit)
    if not items:
        return (
            "# AI 资讯早报\n"
            "> 当前还没有缓存到资讯，请先执行一次“立即获取并推送”。\n\n"
            "---\n"
            "> 清云·武汉研发中心 🦞"
        )

    lines = [
        "# AI 资讯早报",
        "",
        "> 精选最新 AI 动态，已整理为中文速读版。",
        f"> 共 {len(items[:limit])} 条，可直接点击标题或“查看原文”。",
        "",
        "---",
        "",
    ]
    for index, item in enumerate(items[:limit], start=1):
        lines.append(f"## {index}. [{item['title']}]({item['url']})")
        lines.append("")
        lines.append(f"- **来源**：{item['source']}")
        lines.append(f"- **发布时间**：{item['published_at']}")
        lines.append(f"- **中文摘要**：{item['summary']}")
        lines.append(f"- **查看原文**：[点击阅读]({item['url']})")
        if item.get("image_url"):
            lines.append(f"- **配图**：![资讯配图]({item['image_url']})")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("> 清云·武汉研发中心 🦞")
    return "\n".join(lines)[:3900]


def refresh_ai_digest(fetch_timeout: float = 8.0) -> str:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fetch_ai_news)
    try:
        future.result(timeout=fetch_timeout)
    except FuturesTimeoutError:
        pass
    except Exception:
        pass
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return build_ai_digest()


def push_ai_digest_to_wechat(message: str | None = None) -> dict[str, str]:
    webhook_url = get_settings().wechat_webhook_url
    if not webhook_url:
        return {"ok": "false", "status": "未配置企业微信 webhook"}

    markdown_content = message if message and ("[" in message and "](" in message) else build_ai_digest_markdown()
    payload = {
        "msgtype": "markdown_v2",
        "markdown_v2": {
            "content": markdown_content,
        },
    }
    response = httpx.post(webhook_url, json=payload, timeout=6.0)
    response.raise_for_status()
    body = response.json()
    if body.get("errcode") != 0:
        raise RuntimeError(body.get("errmsg", "企业微信 webhook 返回失败"))
    return {"ok": "true", "status": "已推送到企业微信"}


def _extract_image_url(entry: object, raw_summary: str) -> str:
    for field_name in ("media_content", "media_thumbnail"):
        field_value = getattr(entry, field_name, None)
        if isinstance(field_value, list):
            for candidate in field_value:
                if isinstance(candidate, dict) and candidate.get("url"):
                    return str(candidate["url"])
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_summary, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _clean_summary(summary: str) -> str:
    text = re.sub(r"<img[^>]*>", " ", summary, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    return " ".join(text.split())[:320]


def _contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _looks_english(text: str) -> bool:
    letters = re.findall(r"[A-Za-z]", text)
    return len(letters) >= 24 and not _contains_chinese(text)


def _localize_title(title: str) -> str:
    if not title or _contains_chinese(title) or not _looks_english(title):
        return title
    return _translate_to_chinese(title, kind="标题")


def _localize_summary(summary: str, *, title: str) -> str:
    if not summary or _contains_chinese(summary) or not _looks_english(summary):
        return summary
    prompt = (
        "请将下面这段 AI 资讯摘要翻译并本地化成简洁自然的中文，用于企业微信 AI 早报。"
        "只输出中文摘要，不要添加前缀、引号、解释或项目符号。\n\n"
        f"标题：{title}\n"
        f"摘要：{summary}"
    )
    return _translate_to_chinese(summary, kind="摘要", prompt=prompt)


def _translate_to_chinese(text: str, *, kind: str, prompt: str | None = None) -> str:
    if not text:
        return text
    try:
        translated = simple_chat(
            prompt
            or (
                f"请将下面这段 AI 新闻{kind}翻译成自然、准确、简洁的中文。"
                "只输出翻译结果，不要补充说明。\n\n"
                f"{text}"
            ),
            system_prompt="你是一名中文科技编辑，擅长把英文 AI 资讯准确翻译成简洁中文。",
            temperature=0.2,
        ).strip()
        if translated and _contains_chinese(translated):
            return translated[:320]
    except Exception:
        pass
    return text
