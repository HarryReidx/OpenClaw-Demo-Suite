from __future__ import annotations

import atexit
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright


CHROME_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]


BROWSER_OPEN_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_open_page",
        "description": "Open a web page in the current browser session and return a page snapshot.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL to open, for example http://172.19.101.6:8000/.",
                },
            },
            "required": ["url"],
        },
    },
}


BROWSER_SNAPSHOT_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_read_page",
        "description": "Read the current page and return the visible text plus clickable elements.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}


BROWSER_CLICK_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_click",
        "description": "Click one of the clickable elements returned by browser_read_page using its element_index.",
        "parameters": {
            "type": "object",
            "properties": {
                "element_index": {
                    "type": "integer",
                    "description": "The clickable element index from browser_read_page.",
                },
            },
            "required": ["element_index"],
        },
    },
}


BROWSER_FILL_LOGIN_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_fill_login",
        "description": "Fill the visible username and password inputs on a login page.",
        "parameters": {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "The username to fill.",
                },
                "password": {
                    "type": "string",
                    "description": "The password to fill.",
                },
            },
            "required": ["username", "password"],
        },
    },
}


BROWSER_BACK_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_go_back",
        "description": "Go back to the previous page in the current browser session and return a fresh snapshot.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}


def browser_tools() -> list[dict[str, Any]]:
    return [
        BROWSER_OPEN_TOOL,
        BROWSER_SNAPSHOT_TOOL,
        BROWSER_FILL_LOGIN_TOOL,
        BROWSER_CLICK_TOOL,
        BROWSER_BACK_TOOL,
    ]


@dataclass
class BrowserSession:
    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page
    lock: threading.Lock
    owner_thread_id: int


_sessions: dict[str, BrowserSession] = {}
_sessions_guard = threading.Lock()
_close_timers: dict[str, threading.Timer] = {}
AUTO_CLOSE_DELAY_SECONDS = 12.0


def _browser_executable() -> str:
    for candidate in CHROME_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("未找到可用的 Chrome 或 Edge 浏览器，请先安装浏览器。")


def _wait_for_page(page: Page) -> None:
    page.wait_for_load_state("domcontentloaded", timeout=15000)
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass


def _sanitize_text(value: Any, limit: int = 200) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _snapshot(page: Page) -> dict[str, Any]:
    _wait_for_page(page)
    payload = page.evaluate(
        """() => {
            const normalize = (value, limit = 240) => {
                const text = String(value || "").replace(/\\s+/g, " ").trim();
                return text.slice(0, limit);
            };
            const isVisible = (element) => {
                const style = window.getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.visibility !== "hidden"
                    && style.display !== "none"
                    && rect.width > 0
                    && rect.height > 0;
            };
            const selectors = [
                "a[href]",
                "button",
                "input[type=button]",
                "input[type=submit]",
                "[role=button]",
                "[onclick]"
            ];
            const clickable = [];
            const formFields = [];
            const seen = new Set();
            document.querySelectorAll(selectors.join(",")).forEach((element) => {
                if (!isVisible(element)) {
                    return;
                }
                const text = normalize(
                    element.innerText || element.textContent || element.getAttribute("aria-label") || element.getAttribute("title")
                );
                const href = normalize(element.getAttribute("href"));
                const key = `${element.tagName}|${text}|${href}`;
                if (seen.has(key)) {
                    return;
                }
                seen.add(key);
                clickable.push({
                    text,
                    tag: element.tagName.toLowerCase(),
                    href,
                    aria_label: normalize(element.getAttribute("aria-label")),
                    title: normalize(element.getAttribute("title")),
                });
            });
            document.querySelectorAll("input, textarea, select").forEach((element) => {
                if (!isVisible(element)) {
                    return;
                }
                formFields.push({
                    tag: element.tagName.toLowerCase(),
                    type: normalize(element.getAttribute("type") || element.type || ""),
                    name: normalize(element.getAttribute("name")),
                    id: normalize(element.getAttribute("id")),
                    placeholder: normalize(element.getAttribute("placeholder")),
                    value: normalize(element.value),
                    autocomplete: normalize(element.getAttribute("autocomplete")),
                });
            });
            const bodyText = normalize(document.body ? document.body.innerText : "", 4000);
            return {
                title: document.title || "",
                body_text: bodyText,
                clickable,
                form_fields: formFields,
            };
        }"""
    )
    clickable = []
    for index, item in enumerate(payload.get("clickable", [])[:20], start=1):
        clickable.append(
            {
                "element_index": index,
                "text": _sanitize_text(item.get("text"), 120),
                "tag": _sanitize_text(item.get("tag"), 40),
                "href": _sanitize_text(item.get("href"), 200),
                "aria_label": _sanitize_text(item.get("aria_label"), 120),
                "title": _sanitize_text(item.get("title"), 120),
            }
        )
    return {
        "ok": True,
        "url": page.url,
        "title": _sanitize_text(payload.get("title"), 200),
        "body_text": payload.get("body_text", ""),
        "clickable_elements": clickable,
        "form_fields": payload.get("form_fields", [])[:12],
    }


def _visible(locator: Any) -> Any | None:
    try:
        if locator.count() and locator.first.is_visible():
            return locator.first
    except Exception:
        return None
    return None


def _first_visible(page: Page, selectors: list[str]) -> Any | None:
    for selector in selectors:
        locator = _visible(page.locator(selector))
        if locator is not None:
            return locator
    return None


def _fill_input(locator: Any, value: str) -> None:
    locator.click(timeout=5000)
    locator.fill("")
    locator.fill(value, timeout=5000)


def get_browser_session(session_id: str) -> BrowserSession:
    current_thread_id = threading.get_ident()
    recreate_existing = None
    with _sessions_guard:
        timer = _close_timers.pop(session_id, None)
        if timer is not None:
            timer.cancel()
        existing = _sessions.get(session_id)
        if existing:
            if existing.owner_thread_id == current_thread_id:
                return existing
            recreate_existing = existing

    if recreate_existing is not None:
        close_browser_session(session_id)

    with _sessions_guard:
        existing = _sessions.get(session_id)
        if existing and existing.owner_thread_id == current_thread_id:
            return existing
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            executable_path=_browser_executable(),
            headless=False,
            args=["--disable-gpu", "--no-first-run", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        session = BrowserSession(
            playwright=playwright,
            browser=browser,
            context=context,
            page=page,
            lock=threading.Lock(),
            owner_thread_id=current_thread_id,
        )
        _sessions[session_id] = session
        return session


def close_browser_session(session_id: str) -> None:
    with _sessions_guard:
        timer = _close_timers.pop(session_id, None)
        if timer is not None:
            timer.cancel()
        session = _sessions.pop(session_id, None)
    if not session:
        return
    try:
        session.context.close()
    finally:
        try:
            session.browser.close()
        finally:
            session.playwright.stop()


def close_all_browser_sessions() -> None:
    with _sessions_guard:
        session_ids = list(_sessions.keys())
    for session_id in session_ids:
        close_browser_session(session_id)


atexit.register(close_all_browser_sessions)


def schedule_browser_session_close(session_id: str, delay_seconds: float = AUTO_CLOSE_DELAY_SECONDS) -> None:
    with _sessions_guard:
        if session_id not in _sessions:
            return
        timer = _close_timers.pop(session_id, None)
        if timer is not None:
            timer.cancel()
        next_timer = threading.Timer(delay_seconds, close_browser_session, args=[session_id])
        next_timer.daemon = True
        _close_timers[session_id] = next_timer
        next_timer.start()


def execute_browser_tool(session_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    session = get_browser_session(session_id)
    with session.lock:
        if name == "browser_open_page":
            url = str(args.get("url") or "").strip()
            if not url:
                return {"ok": False, "error": "缺少 url"}
            session.page.goto(url, wait_until="domcontentloaded", timeout=20000)
            result = _snapshot(session.page)
            schedule_browser_session_close(session_id)
            return result

        if name == "browser_read_page":
            result = _snapshot(session.page)
            schedule_browser_session_close(session_id)
            return result

        if name == "browser_fill_login":
            username = str(args.get("username") or "")
            password = str(args.get("password") or "")
            if not username or not password:
                return {"ok": False, "error": "缺少 username 或 password"}

            username_locator = _first_visible(
                session.page,
                [
                    "input[placeholder*='用户名']",
                    "input[placeholder*='账号']",
                    "input[autocomplete='username']",
                    "input[name*='user' i]",
                    "input[id*='user' i]",
                    "input[name*='account' i]",
                    "input[id*='account' i]",
                    "input[type='text']",
                    "input:not([type])",
                ],
            )
            password_locator = _first_visible(
                session.page,
                [
                    "input[placeholder*='密码']",
                    "input[autocomplete='current-password']",
                    "input[name*='pass' i]",
                    "input[id*='pass' i]",
                    "input[type='password']",
                ],
            )
            if username_locator is None or password_locator is None:
                snapshot = _snapshot(session.page)
                return {
                    "ok": False,
                    "error": "未找到可见的用户名或密码输入框",
                    "snapshot": snapshot,
                }

            _fill_input(username_locator, username)
            _fill_input(password_locator, password)
            snapshot = _snapshot(session.page)
            result = {
                "ok": True,
                "filled": True,
                "snapshot": snapshot,
            }
            schedule_browser_session_close(session_id)
            return result

        if name == "browser_click":
            element_index = int(args.get("element_index") or 0)
            snapshot = _snapshot(session.page)
            clickable = snapshot.get("clickable_elements", [])
            if element_index < 1 or element_index > len(clickable):
                return {
                    "ok": False,
                    "error": f"element_index 超出范围，当前只有 {len(clickable)} 个可点击元素",
                }
            target = clickable[element_index - 1]
            text = target.get("text")
            href = target.get("href")
            clicked = False
            if href:
                locator = session.page.locator(f'a[href="{href}"]').first
                if locator.count():
                    locator.click(timeout=10000)
                    clicked = True
            if not clicked and text:
                locator = session.page.get_by_text(text, exact=True).first
                if locator.count():
                    locator.click(timeout=10000)
                    clicked = True
            if not clicked:
                raise RuntimeError(f"未能点击元素 #{element_index}，请改用其他元素重试。")
            session.page.wait_for_timeout(2500)
            result = _snapshot(session.page)
            schedule_browser_session_close(session_id)
            return result

        if name == "browser_go_back":
            session.page.go_back(wait_until="domcontentloaded", timeout=10000)
            session.page.wait_for_timeout(1200)
            result = _snapshot(session.page)
            schedule_browser_session_close(session_id)
            return result

        return {"ok": False, "error": f"未知浏览器工具：{name}"}
