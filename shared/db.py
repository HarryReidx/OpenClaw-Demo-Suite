from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from shared.config import get_settings


DB_PATH = get_settings().data_dir / "openclaw_demo.db"


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name TEXT NOT NULL,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                meta_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS news_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                summary TEXT NOT NULL,
                published_at TEXT NOT NULL,
                image_url TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                target TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        chat_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(chat_messages)").fetchall()
        }
        if "meta_json" not in chat_columns:
            conn.execute(
                "ALTER TABLE chat_messages ADD COLUMN meta_json TEXT NOT NULL DEFAULT '{}'"
            )

        news_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(news_items)").fetchall()
        }
        if "image_url" not in news_columns:
            conn.execute(
                "ALTER TABLE news_items ADD COLUMN image_url TEXT NOT NULL DEFAULT ''"
            )


def save_message(
    app_name: str,
    session_id: str,
    role: str,
    content: str,
    metadata: dict | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_messages (app_name, session_id, role, content, meta_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (app_name, session_id, role, content, json.dumps(metadata or {}, ensure_ascii=False)),
        )


def load_messages(app_name: str, session_id: str, limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT role, content, meta_json, created_at
            FROM chat_messages
            WHERE app_name = ? AND session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (app_name, session_id, limit),
        ).fetchall()
    items: list[dict] = []
    for row in reversed(rows):
        item = dict(row)
        item["metadata"] = json.loads(item.pop("meta_json") or "{}")
        items.append(item)
    return items


def delete_messages(app_name: str, session_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM chat_messages
            WHERE app_name = ? AND session_id = ?
            """,
            (app_name, session_id),
        )


def save_news_item(
    title: str,
    url: str,
    source: str,
    summary: str,
    published_at: str,
    tags: list[str],
    image_url: str = "",
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO news_items
            (title, url, source, summary, published_at, image_url, tags_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                url,
                source,
                summary,
                published_at,
                image_url,
                json.dumps(tags, ensure_ascii=False),
            ),
        )


def list_news_items(limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT title, url, source, summary, published_at, image_url, tags_json, created_at
            FROM news_items
            ORDER BY published_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    results: list[dict] = []
    for row in rows:
        item = dict(row)
        item["tags"] = json.loads(item.pop("tags_json"))
        results.append(item)
    return results


def add_subscriber(channel: str, target: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO subscribers (channel, target)
            VALUES (?, ?)
            """,
            (channel, target),
        )


def list_subscribers() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT channel, target, created_at
            FROM subscribers
            ORDER BY id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


init_db()
