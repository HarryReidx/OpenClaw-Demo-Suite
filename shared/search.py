from __future__ import annotations

from urllib.parse import quote_plus

import feedparser
import httpx

from shared.config import get_settings
from shared.db import list_news_items
from shared.schemas import SearchResult


def _load_tavily_results(query: str, max_results: int) -> list[SearchResult]:
    settings = get_settings()
    if not settings.tavily_api_key:
        return []

    try:
        response = httpx.post(
            f"{settings.tavily_base_url}/search",
            json={
                "api_key": settings.tavily_api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "advanced",
                "topic": "general",
                "include_answer": False,
                "include_images": False,
                "include_raw_content": False,
            },
            timeout=12.0,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    results: list[SearchResult] = []
    for item in payload.get("results", [])[:max_results]:
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title or not url:
            continue
        snippet = str(item.get("content") or item.get("snippet") or title).strip()
        source = str(item.get("source") or "Tavily").strip() or "Tavily"
        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=" ".join(snippet.split())[:280],
                source=source,
            )
        )
    return results


def _load_google_news(query: str, max_results: int) -> list[SearchResult]:
    feed_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    try:
        response = httpx.get(feed_url, timeout=4.0, follow_redirects=True)
        response.raise_for_status()
        feed = feedparser.parse(response.text)
    except Exception:
        return []

    results: list[SearchResult] = []
    for entry in list(getattr(feed, "entries", []))[:max_results]:
        title = getattr(entry, "title", "")
        link = getattr(entry, "link", "")
        if not title or not link:
            continue
        summary = getattr(entry, "summary", "") or title
        results.append(
            SearchResult(
                title=title,
                url=link,
                snippet=summary,
                source="Google News RSS",
            )
        )
    return results


def search_web(query: str, max_results: int = 6) -> list[SearchResult]:
    tavily_results = _load_tavily_results(query, max_results)
    if tavily_results:
        return tavily_results

    results = _load_google_news(query, max_results)
    if results:
        return results

    try:
        response = httpx.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": query, "tags": "story", "hitsPerPage": max_results},
            timeout=8.0,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    hn_results: list[SearchResult] = []
    for hit in payload.get("hits", []):
        title = hit.get("title") or hit.get("story_title")
        url = hit.get("url") or hit.get("story_url")
        if not title or not url:
            continue
        snippet = hit.get("story_text") or hit.get("comment_text") or title
        hn_results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=" ".join(str(snippet).split())[:240],
                source="Hacker News Search",
            )
        )
    if hn_results:
        return hn_results

    cached_items = list_news_items(limit=max_results)
    return [
        SearchResult(
            title=item["title"],
            url=item["url"],
            snippet=item["summary"],
            source=f"{item['source']} / 缓存资讯",
        )
        for item in cached_items
    ]
