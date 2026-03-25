from __future__ import annotations

import json
import re
import sys
import asyncio
import threading
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from uuid import uuid4

import uvicorn
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.browser import browser_tools, close_browser_session, execute_browser_tool
from shared.config import get_settings
from shared.db_skill import (
    DEFAULT_SKILL_ID,
    DEFAULT_SKILL_NAME,
    connection_summary,
    extract_connection_details,
    install_database_skill,
    list_tables as db_skill_list_tables,
    run_readonly_query as db_skill_run_readonly_query,
    select_installable_skill,
    smoke_test_database_skill,
)
from shared.skill_registry import (
    install_skill_from_github,
    parse_github_install_spec,
    run_optional_smoke_test,
)
from shared.db import delete_messages, load_messages, save_message
from shared.news import push_ai_digest_to_wechat, refresh_ai_digest
from shared.qwen_client import chat_completion, simple_chat, stream_chat_completion, vision_chat
from shared.rag import (
    RAG_DIR,
    add_document,
    delete_document,
    extract_text_from_file,
    get_document,
    list_documents,
    search_chunks,
)
from shared.scheduler import ensure_scheduler_started, get_scheduler
from shared.search import search_web


settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
APP_NAME = "mobile-openclaw"
UPLOADS_DIR = settings.data_dir / "uploads" / APP_NAME
KB_UPLOADS_DIR = RAG_DIR / "openclaw"
TASKS_PATH = settings.data_dir / "openclaw_tasks.json"
EMAILS_PATH = settings.data_dir / "openclaw_emails.json"
INSTALLED_SKILLS_PATH = settings.data_dir / "openclaw_installed_skills.json"
INSTALLABLE_SKILLS_ROOT = settings.codex_skills_dir
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
KB_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
INSTALLABLE_SKILLS_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="05. 模拟 OpenClaw 综合工作台")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


def _load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_json_list(path: Path, items: list[dict]) -> None:
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _message_payload(item: dict) -> dict[str, object]:
    metadata = item.get("metadata", {})
    payload: dict[str, object] = {
        "role": item["role"],
        "content": item["content"],
        "created_at": item.get("created_at"),
        "task_title": metadata.get("task_title"),
        "steps": metadata.get("steps", []),
        "skills": metadata.get("skills", []),
    }
    if metadata.get("image_url"):
        payload["image_url"] = metadata["image_url"]
    if metadata.get("image_name"):
        payload["image_name"] = metadata["image_name"]
    return payload


def _step(label: str, status: str, detail: str) -> dict[str, str]:
    return {"label": label, "status": status, "detail": detail}


def _load_tasks() -> list[dict]:
    return _load_json_list(TASKS_PATH)


def _save_tasks(items: list[dict]) -> None:
    _save_json_list(TASKS_PATH, items)


def _load_emails() -> list[dict]:
    return _load_json_list(EMAILS_PATH)


def _save_emails(items: list[dict]) -> None:
    _save_json_list(EMAILS_PATH, items)


def _load_installed_skills() -> list[dict]:
    items = _load_json_list(INSTALLED_SKILLS_PATH)
    has_current_database_skill = any(item.get("skill_id") == DEFAULT_SKILL_ID for item in items)
    cleaned: list[dict] = []
    seen_ids: set[str] = set()
    for item in items:
        skill_id = str(item.get("skill_id") or "").strip()
        if not skill_id or skill_id in seen_ids:
            continue
        if has_current_database_skill and skill_id == "sqlite_db_connector":
            continue
        seen_ids.add(skill_id)
        cleaned.append(item)
    return cleaned


def _save_installed_skills(items: list[dict]) -> None:
    _save_json_list(INSTALLED_SKILLS_PATH, items)


def _upsert_installed_skill(skill: dict[str, object]) -> None:
    items = _load_installed_skills()
    legacy_ids = {"sqlite_db_connector"} if skill.get("skill_id") == DEFAULT_SKILL_ID else set()
    next_items: list[dict] = []
    replaced = False
    for current in items:
        current_id = current.get("skill_id")
        if current_id == skill.get("skill_id"):
            current.update(skill)
            next_items.append(current)
            replaced = True
            continue
        if current_id in legacy_ids:
            continue
        next_items.append(current)
    if not replaced:
        next_items.append(skill)
    _save_installed_skills(next_items)


def _update_task(task_id: str, **updates: object) -> None:
    tasks = _load_tasks()
    for task in tasks:
        if task["task_id"] == task_id:
            task.update(updates)
            break
    _save_tasks(tasks)


def _task_payload(task: dict) -> dict[str, object]:
    return {
        "task_id": task["task_id"],
        "task_type": task.get("task_type", ""),
        "prompt_text": task.get("prompt_text", ""),
        "action_prompt": task.get("action_prompt", ""),
        "schedule_mode": task.get("schedule_mode", ""),
        "status": task.get("status", "pending"),
        "created_at": task.get("created_at"),
        "run_at": task.get("run_at"),
        "started_at": task.get("started_at"),
        "finished_at": task.get("finished_at"),
    }


def _email_payload(item: dict) -> dict[str, object]:
    return {
        "email_id": item["email_id"],
        "session_id": item["session_id"],
        "subject": item["subject"],
        "recipients": item["recipients"],
        "body_markdown": item["body_markdown"],
        "status": item.get("status", "sent"),
        "category": item.get("category", "general"),
        "created_at": item.get("created_at"),
        "sent_at": item.get("sent_at"),
    }


def _skill_catalog() -> list[dict[str, str]]:
    builtins = [
        {
            "id": "vision",
            "name": "看图分析",
            "description": "上传图片后识别画面重点，并给出下一步建议。",
        },
        {
            "id": "rag",
            "name": "知识库问答",
            "description": "结合本地上传的 txt、md、docx 文档进行回答。",
        },
        {
            "id": "web_search",
            "name": "联网搜索",
            "description": "识别搜索意图后联网整理结果，输出适合演示的答复。",
        },
        {
            "id": "browser_agent",
            "name": "浏览器操作",
            "description": "支持访问网页、读取页面正文，并按页面元素完成点击跳转。",
        },
        {
            "id": "schedule_push",
            "name": "定时任务",
            "description": "支持创建通用定时任务，并追踪执行状态，例如新闻、网页操作、天气提醒等。",
        },
        {
            "id": "chat_memory",
            "name": "会话记忆",
            "description": "对话时自动读取最近多轮消息，形成连续上下文。",
        },
        {
            "id": "mail_send",
            "name": "邮件发送",
            "description": "支持生成并演示发送全员通知、会议纪要等企业内部邮件。",
        },
    ]
    installed = [
        {
            "id": str(item.get("skill_id") or ""),
            "name": str(item.get("name") or ""),
            "description": str(item.get("description") or ""),
        }
        for item in _load_installed_skills()
        if item.get("status") == "installed"
    ]
    return builtins + installed


def _memory_payload(session_id: str) -> dict[str, object]:
    items = load_messages(APP_NAME, session_id, limit=24)
    user_messages = [item for item in items if item.get("role") == "user"]
    assistant_messages = [item for item in items if item.get("role") == "assistant"]
    latest_created_at = items[-1]["created_at"] if items else None

    memory_items: list[dict[str, object]] = []
    for index, item in enumerate(items):
        if item.get("role") != "user":
            continue
        reply = next((candidate for candidate in items[index + 1 :] if candidate.get("role") == "assistant"), None)
        content = item.get("content", "")
        memory_items.append(
            {
                "memory_id": f"mem-{index}",
                "title": content[:32] or "未命名记忆",
                "user_content": content,
                "assistant_preview": (reply.get("content", "")[:200] if reply else ""),
                "created_at": item.get("created_at"),
            }
        )

    return {
        "session_id": session_id,
        "message_count": len(items),
        "user_message_count": len(user_messages),
        "assistant_message_count": len(assistant_messages),
        "latest_created_at": latest_created_at,
        "recent_memories": list(reversed(memory_items[-6:])),
    }


def _append_email_record(session_id: str, subject: str, recipients: str, body_markdown: str, category: str) -> dict:
    record = {
        "email_id": uuid4().hex,
        "session_id": session_id,
        "subject": subject,
        "recipients": recipients,
        "body_markdown": body_markdown,
        "category": category,
        "status": "sent",
        "created_at": datetime.now().isoformat(),
        "sent_at": datetime.now().isoformat(),
    }
    emails = _load_emails()
    emails.append(record)
    _save_emails(emails)
    return record


def _remove_session_tasks(session_id: str) -> None:
    scheduler = get_scheduler()
    tasks = []
    for task in _load_tasks():
        if task["session_id"] == session_id and task.get("status") == "pending":
            if scheduler.get_job(task["task_id"]):
                scheduler.remove_job(task["task_id"])
            continue
        tasks.append(task)
    _save_tasks(tasks)


def _schedule_task(task: dict) -> None:
    scheduler = ensure_scheduler_started()
    if task.get("schedule_mode") == "daily":
        job = scheduler.add_job(
            _execute_scheduled_task,
            trigger=CronTrigger(hour=int(task.get("hour", 9)), minute=int(task.get("minute", 0))),
            id=task["task_id"],
            replace_existing=True,
            args=[task["task_id"]],
        )
        if job and job.next_run_time:
            _update_task(task["task_id"], run_at=job.next_run_time.isoformat())
        return

    run_at = datetime.fromisoformat(task["run_at"])
    scheduler.add_job(
        _execute_scheduled_task,
        trigger=DateTrigger(run_date=run_at),
        id=task["task_id"],
        replace_existing=True,
        args=[task["task_id"]],
    )


def _restore_pending_tasks() -> None:
    now = datetime.now()
    for task in _load_tasks():
        if task.get("task_type") == "skill_install" and task.get("status") in {"pending", "running"}:
            _start_skill_install_task(task["task_id"])
            continue
        if task.get("status") != "pending":
            continue
        if task.get("task_type") == "scheduled_action" and task.get("schedule_mode") == "daily":
            _schedule_task(task)
            continue
        run_at = datetime.fromisoformat(task["run_at"])
        if run_at <= now:
            _execute_scheduled_task(task["task_id"])
            continue
        _schedule_task(task)


def _create_news_task(session_id: str, delay_seconds: int, prompt_text: str) -> dict:
    run_at = datetime.now() + timedelta(seconds=delay_seconds)
    task = {
        "task_id": uuid4().hex,
        "session_id": session_id,
        "task_type": "ai_news_push",
        "prompt_text": prompt_text,
        "delay_seconds": delay_seconds,
        "run_at": run_at.isoformat(),
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }
    tasks = _load_tasks()
    tasks.append(task)
    _save_tasks(tasks)
    _schedule_task(task)
    return task


def _create_scheduled_action_task(
    session_id: str,
    prompt_text: str,
    action_prompt: str,
    *,
    delay_seconds: int | None = None,
    schedule_mode: str = "once",
    hour: int | None = None,
    minute: int | None = None,
) -> dict:
    run_at = datetime.now() + timedelta(seconds=delay_seconds or 0)
    if schedule_mode == "daily":
        now = datetime.now()
        target = now.replace(hour=hour or 9, minute=minute or 0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        run_at = target

    task = {
        "task_id": uuid4().hex,
        "session_id": session_id,
        "task_type": "scheduled_action",
        "prompt_text": prompt_text,
        "action_prompt": action_prompt,
        "schedule_mode": schedule_mode,
        "delay_seconds": delay_seconds,
        "hour": hour,
        "minute": minute,
        "run_at": run_at.isoformat(),
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }
    tasks = _load_tasks()
    tasks.append(task)
    _save_tasks(tasks)
    _schedule_task(task)
    return task


def _create_skill_install_task(
    session_id: str,
    prompt_text: str,
    skill_id: str,
    skill_name: str,
    install_source: str = "catalog",
    install_spec: dict[str, object] | None = None,
) -> dict:
    task = {
        "task_id": uuid4().hex,
        "session_id": session_id,
        "task_type": "skill_install",
        "skill_id": skill_id,
        "skill_name": skill_name,
        "install_source": install_source,
        "install_spec": install_spec or {},
        "prompt_text": prompt_text,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }
    tasks = _load_tasks()
    tasks.append(task)
    _save_tasks(tasks)
    return task


def _start_skill_install_task(task_id: str) -> None:
    worker = threading.Thread(target=_execute_skill_install_task, args=(task_id,), daemon=True)
    worker.start()


def _execute_scheduled_task(task_id: str) -> None:
    tasks = _load_tasks()
    task = next((item for item in tasks if item["task_id"] == task_id), None)
    if not task or task.get("status") != "pending":
        return

    action_prompt = str(task.get("action_prompt") or task.get("prompt_text") or "").strip()
    steps = [
        _step("读取任务", "done", "已加载用户的定时需求"),
        _step("触发定时执行", "done", "已唤起调度任务并开始执行"),
        _step("执行动作", "running", action_prompt or "已读取待执行内容"),
    ]
    _update_task(task_id, status="running", started_at=datetime.now().isoformat())
    try:
        non_stream_result = _generate_non_stream_response(
            session_id=task["session_id"],
            prompt_text=action_prompt,
            image_bytes=None,
            image_content_type="image/jpeg",
            metadata={},
            allow_scheduling=False,
        )
        if non_stream_result is not None:
            action_answer, action_meta = non_stream_result
        else:
            conversation, history_items, rag_context = _build_chat_conversation(task["session_id"], action_prompt)
            action_meta = _build_chat_assistant_meta(action_prompt, history_items, rag_context)
            response = chat_completion(conversation, temperature=0.45)
            action_answer = response.choices[0].message.content or ""
        steps[2] = _step("执行动作", "done", action_prompt or "已完成执行")
        content = f"定时任务执行结果：\n{action_answer}"
        status = "pending" if task.get("schedule_mode") == "daily" else "done"
    except Exception as exc:
        steps[2] = _step("执行动作", "failed", str(exc))
        content = f"定时任务执行失败：{exc}"
        status = "pending" if task.get("schedule_mode") == "daily" else "failed"

    save_message(
        APP_NAME,
        task["session_id"],
        "assistant",
        content,
        metadata={"task_title": "定时任务已执行", "steps": steps, "skills": ["定时任务"]},
    )
    scheduler = get_scheduler()
    job = scheduler.get_job(task_id)
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
    _update_task(
        task_id,
        status=status,
        finished_at=datetime.now().isoformat(),
        run_at=next_run or task.get("run_at"),
        last_run_at=datetime.now().isoformat(),
    )


def _execute_skill_install_task(task_id: str) -> None:
    tasks = _load_tasks()
    task = next((item for item in tasks if item["task_id"] == task_id), None)
    if not task or task.get("status") not in {"pending", "running"}:
        return

    _update_task(task_id, status="running", started_at=datetime.now().isoformat())
    steps = [
        _step("识别安装请求", "done", f"已匹配候选技能：{task.get('skill_name', DEFAULT_SKILL_NAME)}"),
        _step("安装技能文件", "running", "正在安装到 Codex skills 目录"),
        _step("执行连通性测试", "pending", "等待安装完成后执行 smoke test"),
        _step("回写技能目录", "pending", "等待写入 Skills 面板"),
    ]
    try:
        install_source = str(task.get("install_source") or "catalog")
        install_spec = task.get("install_spec") or {}

        if install_source == "github":
            manifest = install_skill_from_github(install_spec, dest_root=INSTALLABLE_SKILLS_ROOT)
            steps[1] = _step("安装技能文件", "done", f"已写入 {manifest['install_dir']}")
            smoke = run_optional_smoke_test(Path(manifest["install_dir"]))
            if smoke.get("ok"):
                steps[2] = _step("执行连通性测试", "done", "已执行 smoke test")
            else:
                steps[2] = _step("执行连通性测试", "failed", smoke.get("error") or "未执行 smoke test")
            installed_skill = {**manifest, "smoke_test": smoke}
            _upsert_installed_skill(installed_skill)
            steps[3] = _step("回写技能目录", "done", "已刷新 Skills 面板中的已安装技能")
            answer = "\n".join(
                [
                    f"已安装技能：{installed_skill['name']}",
                    f"- 技能标识：{installed_skill['skill_id']}",
                    f"- 来源：GitHub",
                    f"- 安装目录：{installed_skill['install_dir']}",
                    f"- Smoke Test：{'成功' if smoke.get('ok') else '未通过'}",
                ]
            )
            status = "done" if smoke.get("ok") else "failed"
        else:
            manifest = install_database_skill(task.get("skill_id") or DEFAULT_SKILL_ID, INSTALLABLE_SKILLS_ROOT)
            steps[1] = _step("安装技能文件", "done", f"已写入 {manifest['install_dir']}")
            smoke = smoke_test_database_skill(manifest)
            if smoke.get("ok"):
                steps[2] = _step("执行连通性测试", "done", f"SELECT 1 成功，发现 {smoke.get('table_count', 0)} 张表")
            else:
                steps[2] = _step("执行连通性测试", "failed", smoke.get("error") or "smoke test 失败")
            installed_skill = {
                **manifest,
                "source": "local-catalog",
                "smoke_test": smoke,
            }
            _upsert_installed_skill(installed_skill)
            steps[3] = _step("回写技能目录", "done", "已刷新 Skills 面板中的已安装技能")
            answer = "\n".join(
                [
                    f"已安装技能：{installed_skill['name']}",
                    f"- 技能标识：{installed_skill['skill_id']}",
                    f"- 数据库类型：{installed_skill['db_engine']}",
                    f"- 连接配置：{connection_summary(installed_skill)}",
                    f"- Smoke Test：{'成功' if smoke.get('ok') else '未通过'}",
                    f"- 示例表：{', '.join(smoke.get('tables', [])[:5]) or '暂无业务表'}",
                    "",
                    "现在你可以继续这样使用它：",
                    "- 帮我用数据库技能列出所有表",
                    "- 帮我查询数据库：SELECT * FROM chat_messages ORDER BY id DESC LIMIT 5",
                ]
            )
            status = "done" if smoke.get("ok") else "failed"
    except Exception as exc:
        steps[1] = _step("安装技能文件", "failed", str(exc))
        steps[2] = _step("执行连通性测试", "failed", "安装失败，未执行 smoke test")
        steps[3] = _step("回写技能目录", "failed", "安装失败，未写入 Skills 面板")
        answer = "\n".join(
            [
                f"技能安装失败：{task.get('skill_name', DEFAULT_SKILL_NAME)}",
                f"- 原因：{exc}",
            ]
        )
        status = "failed"

    save_message(
        APP_NAME,
        task["session_id"],
        "assistant",
        answer,
        metadata={"task_title": "技能安装任务", "steps": steps, "skills": ["技能安装", "数据库技能"]},
    )
    _update_task(task_id, status=status, finished_at=datetime.now().isoformat())


def _detect_delay_seconds(text: str) -> int | None:
    match = re.search(r"([0-9一二两三四五六七八九十百]+)\s*(秒|分钟|分|小时|天)(?:钟)?后", text)
    if not match:
        return None
    raw_value = match.group(1)
    value = int(raw_value) if raw_value.isdigit() else _parse_chinese_number(raw_value)
    if value <= 0:
        return None
    unit = match.group(2)
    multiplier = {
        "秒": 1,
        "分钟": 60,
        "分": 60,
        "小时": 3600,
        "天": 24 * 3600,
    }.get(unit, 1)
    return max(1, min(value * multiplier, 30 * 24 * 3600))


def _parse_chinese_number(text: str) -> int:
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100}
    total = 0
    current = 0
    for char in text:
        if char in digits:
            current = digits[char]
        elif char in units:
            current = max(current, 1) * units[char]
            total += current
            current = 0
    return total + current


def _extract_daily_time(text: str) -> tuple[int, int] | None:
    if "每天" not in text:
        return None
    clock_match = re.search(r"每天(?:早上|上午|中午|下午|晚上)?\s*(\d{1,2})(?:[:：点时](\d{1,2}))?", text)
    if not clock_match:
        return (9, 0)

    hour = int(clock_match.group(1))
    minute = int(clock_match.group(2) or 0)
    if "下午" in text or "晚上" in text:
        hour = hour if hour >= 12 else hour + 12
    if "中午" in text and hour < 11:
        hour += 12
    hour = max(0, min(hour, 23))
    minute = max(0, min(minute, 59))
    return hour, minute


def _strip_schedule_prefix(text: str) -> str:
    cleaned = re.sub(r"^\s*(请)?\s*\d+\s*(秒|分钟|分|小时|天)(?:钟)?后", "", text).strip()
    cleaned = re.sub(r"^\s*(请)?\s*每天(?:早上|上午|中午|下午|晚上)?\s*\d{0,2}(?:[:：点时]\d{0,2})?", "", cleaned).strip()
    cleaned = cleaned.lstrip("，,。.:： ")
    return cleaned or text.strip()


def _extract_schedule_request(text: str) -> dict[str, object] | None:
    delay_seconds = _detect_delay_seconds(text)
    if delay_seconds is not None:
        return {
            "schedule_mode": "once",
            "delay_seconds": delay_seconds,
            "action_prompt": _strip_schedule_prefix(text),
        }

    daily_time = _extract_daily_time(text)
    if daily_time is not None:
        hour, minute = daily_time
        return {
            "schedule_mode": "daily",
            "hour": hour,
            "minute": minute,
            "action_prompt": _strip_schedule_prefix(text),
        }
    return None


def _is_kb_presence_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    return ("知识库" in compact or "本地知识" in compact) and any(
        keyword in compact for keyword in ["有没有", "有无", "是否有", "有关", "关于", "包含", "收录"]
    )


def _extract_kb_topic(text: str) -> str:
    match = re.search(r"(?:关于|有关|有没有|是否有|包含|收录)([^？?。]+)", text)
    if match:
        topic = match.group(1)
    else:
        topic = text
    topic = re.sub(r"^(于|的|与|相关|方面的)", "", topic).strip()
    topic = re.sub(r"(的知识|知识|内容|资料|信息|吗|么|呢)$", "", topic).strip("：:，,。?？ ")
    topic = topic.rstrip("的").strip()
    return topic or text.strip()


def _looks_like_lyric_document(raw_text: str) -> bool:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if len(lines) < 12:
        return False
    short_lines = [line for line in lines if len(line) <= 20]
    repeated = len(lines) - len(set(lines))
    return len(short_lines) >= max(10, len(lines) // 2) and repeated >= 2


def _scan_rag_topic_presence(topic: str) -> tuple[bool, list[str]]:
    matches: list[str] = []
    topic_compact = re.sub(r"\s+", "", topic)
    documents = list_documents()
    if "歌词" in topic_compact:
        lyric_matches: list[str] = []
        for item in documents:
            document = get_document(str(item.get("doc_id") or ""))
            if not document:
                continue
            raw_text = str(document.get("content") or "")
            if _looks_like_lyric_document(raw_text):
                lyric_matches.append(str(item.get("file_name") or document.get("doc_id") or "未命名文档"))
        unique = list(dict.fromkeys(lyric_matches))
        return bool(unique), unique[:6]

    chunks = search_chunks(topic, top_k=5)
    for chunk in chunks:
        score = int(chunk.get("score") or 0)
        if score > 0:
            file_name = str(chunk.get("file_name") or "未命名文档")
            if file_name not in matches:
                matches.append(file_name)

    unique = list(dict.fromkeys(matches))
    return bool(unique), unique[:6]


def _answer_kb_presence(prompt_text: str) -> tuple[str, dict[str, object]]:
    topic = _extract_kb_topic(prompt_text)
    found, matched_files = _scan_rag_topic_presence(topic)
    documents = list_documents()
    if found:
        answer = "\n".join(
            [
                f"有，当前知识库里检索到了和“{topic}”相关的内容。",
                f"- 命中数量：{len(matched_files)}",
                f"- 示例文档：{', '.join(matched_files)}",
            ]
        )
        steps = [
            _step("识别知识库问题", "done", "已识别到知识库存在性检查需求"),
            _step("检索本地知识", "done", f"共命中 {len(matched_files)} 个相关文档"),
        ]
    else:
        answer = "\n".join(
            [
                f"当前没有检索到和“{topic}”直接相关的知识。",
                f"- 当前知识库文档数：{len(documents)}",
                "- 如果你愿意，我可以先帮你上传相关材料，再基于知识库回答。",
            ]
        )
        steps = [
            _step("识别知识库问题", "done", "已识别到知识库存在性检查需求"),
            _step("检索本地知识", "failed", f"未命中与“{topic}”相关的文档"),
        ]
    return answer, {"task_title": "知识库检查", "steps": steps, "skills": ["知识库问答"]}


def _is_news_push_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    keywords = ["\u63a8\u9001AI\u65e9\u62a5", "AI\u8d44\u8baf", "AI\u65e9\u62a5", "\u8d44\u8baf\u603b\u7ed3", "\u8d44\u8baf\u7b80\u62a5", "AI\u603b\u7ed3", "\u6700\u65b0AI\u8d44\u8baf", "AI\u8d44\u8baf\u603b\u7ed3"]
    return any(keyword in compact for keyword in keywords)


def _is_email_request(text: str) -> bool:
    compact = text.replace(" ", "")
    keywords = ["邮件", "发邮件", "发送邮件", "群发", "全员", "会议纪要", "考试认知"]
    return any(keyword in compact for keyword in keywords)


def _is_simple_chat_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.lower())
    simple_patterns = {
        "你好",
        "您好",
        "hi",
        "hello",
        "在吗",
        "早上好",
        "中午好",
        "下午好",
        "晚上好",
        "谢谢",
        "好的",
        "ok",
    }
    return compact in simple_patterns


def _is_search_request(text: str) -> bool:
    keywords = ["联网", "搜索", "查一下", "查一查", "搜一下", "最新资料", "最新信息", "新闻", "局势", "天气", "最新动态"]
    return any(keyword in text for keyword in keywords)


def _is_skill_install_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.lower())
    wants_install = any(keyword in compact for keyword in ["安装", "装一个", "加一个", "install"])
    skillish = any(keyword in compact for keyword in ["skill", "技能", "数据库连接", "数据库", "github.com", "repo"])
    return wants_install and skillish


def _has_installed_skill(skill_id: str) -> bool:
    return any(item.get("skill_id") == skill_id and item.get("status") == "installed" for item in _load_installed_skills())


def _installed_db_skills() -> list[dict]:
    return [
        item
        for item in _load_installed_skills()
        if item.get("status") == "installed" and item.get("db_engine")
    ]


def _is_database_skill_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.lower())
    db_keywords = [
        "数据库技能",
        "连接数据库",
        "数据库查询",
        "查询数据库",
        "列出表",
        "所有表",
        "哪些表",
        "query database",
        "list tables",
        "show tables",
        "mysql",
        "postgres",
        "postgresql",
        "sqlite",
    ]
    normalized_keywords = [re.sub(r"\s+", "", keyword.lower()) for keyword in db_keywords]
    has_sql = "select" in compact and "from" in compact
    return any(keyword in compact for keyword in normalized_keywords) or has_sql


def _select_db_skill_for_request(prompt_text: str) -> dict:
    installed = _installed_db_skills()
    if not installed:
        raise ValueError("当前还没有安装数据库 skill。可以先说：帮我安装一个数据库 skill。")

    compact = re.sub(r"\s+", "", prompt_text.lower())
    if "mysql" in compact:
        for item in installed:
            if str(item.get("db_engine")).lower() == "mysql":
                return item
        raise ValueError("未安装 MySQL 数据库 skill，请先安装 MySQL skill。")
    if "postgres" in compact:
        for item in installed:
            if str(item.get("db_engine")).lower() in {"postgres", "postgresql"}:
                return item
        raise ValueError("未安装 PostgreSQL 数据库 skill，请先安装 PostgreSQL skill。")
    if "sqlite" in compact:
        for item in installed:
            if str(item.get("db_engine")).lower() == "sqlite":
                return item
        raise ValueError("未安装 SQLite 数据库 skill，请先安装 SQLite skill。")

    sorted_skills = sorted(
        installed,
        key=lambda item: str(item.get("installed_at") or ""),
        reverse=True,
    )
    return sorted_skills[0]


def _build_skill_install_ack(session_id: str, prompt_text: str) -> tuple[str, dict[str, object], str | None]:
    github_spec = parse_github_install_spec(prompt_text)
    if github_spec:
        if github_spec.get("error") == "missing_repo_or_path":
            answer = "未识别到 GitHub repo/path，请补充 repo 和 path，例如：repo openai/skills path skills/.curated/sqlite"
            return answer, {"task_title": "技能安装任务", "steps": [_step("识别安装请求", "failed", answer)]}, None
        if not github_spec.get("path"):
            answer = "未识别到 GitHub 路径，请提供完整路径，例如：https://github.com/openai/skills/tree/main/skills/.curated/sqlite"
            return answer, {"task_title": "技能安装任务", "steps": [_step("识别安装请求", "failed", answer)]}, None

        skill_id = github_spec.get("skill_id") or Path(github_spec.get("path") or "").name or "github-skill"
        skill_name = skill_id
        selection_reason = "将使用 GitHub repo/path 安装技能。"
        task = _create_skill_install_task(
            session_id,
            prompt_text,
            skill_id,
            skill_name,
            install_source="github",
            install_spec=github_spec,
        )
        answer = "\n".join(
            [
                f"已创建技能安装任务：{skill_name}",
                f"- 任务编号：{task['task_id'][:8]}",
                f"- 匹配结果：{selection_reason}",
                "- 后续会在后台异步安装、自动执行 smoke test，并在聊天里回写结果。",
            ]
        )
        assistant_meta = {
            "task_title": "技能安装任务",
            "steps": [
                _step("识别安装请求", "done", "已识别到 GitHub 安装需求"),
                _step("匹配候选技能", "done", selection_reason),
                _step("创建后台任务", "running", f"安装任务 {task['task_id'][:8]} 已启动"),
            ],
            "skills": ["技能安装"],
        }
        return answer, assistant_meta, task["task_id"]

    try:
        entry, selection_reason = select_installable_skill(prompt_text)
    except Exception as exc:
        answer = f"技能安装失败：{exc}"
        return answer, {"task_title": "技能安装任务", "steps": [_step("匹配候选技能", "failed", str(exc))]}, None

    task = _create_skill_install_task(
        session_id,
        prompt_text,
        entry.skill_id,
        entry.name,
        install_source="catalog",
        install_spec={"db_engine": entry.db_engine},
    )
    answer = "\n".join(
        [
            f"已创建技能安装任务：{entry.name}",
            f"- 任务编号：{task['task_id'][:8]}",
            f"- 匹配结果：{selection_reason}",
            "- 后续会在后台异步安装、自动执行 smoke test，并在聊天里回写结果。",
        ]
    )
    assistant_meta = {
        "task_title": "技能安装任务",
        "steps": [
            _step("识别安装请求", "done", "已识别到安装 skill 的需求"),
            _step("匹配候选技能", "done", selection_reason),
            _step("创建后台任务", "running", f"安装任务 {task['task_id'][:8]} 已启动"),
        ],
        "skills": ["技能安装"],
    }
    return answer, assistant_meta, task["task_id"]


def _extract_select_query(text: str) -> str:
    match = re.search(r"(select\s+.+)", text, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _extract_url_candidates(text: str) -> list[str]:
    return re.findall(r"https?://[^\s)>\u3002\uff0c]+", text, flags=re.IGNORECASE)


def _is_browser_request(text: str) -> bool:
    urls = _extract_url_candidates(text)
    if urls:
        return True
    compact = re.sub(r"\s+", "", text)
    browser_keywords = [
        "访问",
        "打开网页",
        "打开页面",
        "浏览器",
        "网页",
        "页面内容",
        "抓取页面",
        "点击",
        "点一下",
        "点开",
    ]
    return any(keyword in compact for keyword in browser_keywords)


def _extract_click_target(text: str) -> str:
    match = re.search(r"(?:点击|点开|点一下)([^，。,.；;！!？?\n]+)", text)
    if not match:
        if re.search(r"(登录|立即登录|提交|确认登录)", text):
            return "登录"
        return ""
    target = match.group(1)
    target = re.sub(r"^(一下|一下子|页面上的|网页上的)", "", target).strip()
    target = re.sub(r"(并|然后|再|后|并且).*$", "", target).strip()
    return target.strip(" \"'“”‘’：:")


def _extract_login_credentials(text: str) -> tuple[str, str]:
    compact = text.strip()
    pair_patterns = [
        r"(?:用户名和密码|账号密码|用户名/密码|账号/密码)[：: ]*[\"“']?([A-Za-z0-9_.-]{1,80})\s*/\s*([^\s，。；;\"“”'、]{1,120})",
        r"使用[“\"']?([A-Za-z0-9_.-]{1,80})\s*/\s*([^\s，。；;\"“”'、]{1,120})[”\"']?(?:这个)?(?:用户名密码|账号密码)?",
        r"[“\"']([A-Za-z0-9_.-]{1,80})\s*/\s*([^\s，。；;\"“”'、]{1,120})[”\"']",
    ]
    for pattern in pair_patterns:
        match = re.search(pattern, compact)
        if match:
            return match.group(1).strip(), match.group(2).strip()

    user_match = re.search(r"(?:用户名|账号|user(?:name)?|account)[：:\s]+([A-Za-z0-9_.-]{1,80})", compact, flags=re.IGNORECASE)
    if not user_match:
        user_match = re.search(r"(?:用户名|账号)\s*[为是]\s*([A-Za-z0-9_.-]{1,80})", compact)
    password_match = re.search(r"(?:密码|password|pwd|pass)[：:\s]+([^\s，。；;\"“”'、]{1,120})", compact, flags=re.IGNORECASE)
    if not password_match:
        password_match = re.search(r"(?:密码)\s*[为是]\s*([^\s，。；;\"“”'、]{1,120})", compact)
    if user_match and password_match:
        return user_match.group(1).strip(), password_match.group(1).strip()

    scrubbed = re.sub(r"https?://[^\s]+", " ", compact, flags=re.IGNORECASE)
    scrubbed = re.sub(r"(?:输入框|用户名和密码输入框|账号密码输入框|输入用户名和密码|输入账号密码)", " ", scrubbed)
    generic_pairs = re.findall(r"([A-Za-z0-9_.-]{2,})\s*/\s*([A-Za-z0-9_@#$%^&*().!+=:-]{2,})", scrubbed)
    if generic_pairs:
        username, password = generic_pairs[-1]
        return username.strip(), password.strip()
    return "", ""


def _find_clickable_match(snapshot: dict[str, object], click_target: str) -> dict[str, object] | None:
    target = click_target.strip().lower()
    if not target:
        return None
    clickable = snapshot.get("clickable_elements", [])
    if not isinstance(clickable, list):
        return None

    def score(item: dict[str, object]) -> tuple[int, int]:
        fields = [
            str(item.get("text") or ""),
            str(item.get("aria_label") or ""),
            str(item.get("title") or ""),
            str(item.get("href") or ""),
        ]
        normalized = [field.lower() for field in fields if field]
        exact = any(target == field for field in normalized)
        contains = any(target in field for field in normalized)
        if exact:
            return (2, -len(normalized[0]) if normalized else 0)
        if contains:
            return (1, -min((len(field) for field in normalized if target in field), default=0))
        return (0, 0)

    ranked = sorted(
        (item for item in clickable if isinstance(item, dict)),
        key=score,
        reverse=True,
    )
    if not ranked or score(ranked[0])[0] == 0:
        return None
    return ranked[0]


def _clip_text(value: object, limit: int = 700) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _format_browser_snapshot_answer(
    prompt_text: str,
    snapshot: dict[str, object],
    *,
    username_filled: str = "",
    password_filled: bool = False,
    fill_attempted: bool = False,
    fill_failed_reason: str = "",
    click_target: str = "",
    clicked_label: str = "",
    click_attempted: bool = False,
    click_failed_reason: str = "",
) -> str:
    title = str(snapshot.get("title") or "").strip() or "未识别到标题"
    url = str(snapshot.get("url") or "").strip() or "未识别到地址"
    body_text = _clip_text(snapshot.get("body_text") or "未抓取到可见正文。")
    clickable = snapshot.get("clickable_elements") if isinstance(snapshot.get("clickable_elements"), list) else []

    lines = [
        f"当前页面标题：{title}",
        f"当前页面地址：{url}",
        "",
        "页面可见内容：",
        body_text,
    ]

    if fill_attempted:
        lines.extend(
            [
                "",
                "表单填写结果：",
                f"- 用户名：{'已填写 ' + username_filled if username_filled and not fill_failed_reason else '未完成'}",
                f"- 密码：{'已填写' if password_filled and not fill_failed_reason else '未完成'}",
            ]
        )
        if fill_failed_reason:
            lines.append(f"- 原因：{fill_failed_reason}")

    if click_attempted:
        lines.extend(
            [
                "",
                "点击结果：",
                f"- 目标：{clicked_label or click_target or '未指明'}",
                f"- 状态：{'已执行点击' if clicked_label and not click_failed_reason else '未完成'}",
            ]
        )
        if click_failed_reason:
            lines.append(f"- 原因：{click_failed_reason}")
        else:
            lines.append(f"- 当前停留页：{url}")

    if clickable:
        lines.extend(["", f"当前页可点击项（最多显示 {min(len(clickable), 5)} 个）："])
        for item in clickable[:5]:
            lines.append(
                f"- [{item.get('element_index')}] {item.get('text') or '(无文本)'}"
                + (f" -> {item.get('href')}" if item.get("href") else "")
            )
    else:
        lines.extend(["", "当前页未识别到可点击项。"])

    lines.extend(
        [
            "",
            "说明：以上内容仅基于本次浏览器实际看到的页面信息生成；未看到的登录结果、跳转页面、账号信息或内部文档内容均未验证。",
        ]
    )
    return "\n".join(lines)


def _format_browser_failure(prompt_text: str, error: Exception) -> str:
    return "\n".join(
        [
            "本次浏览器操作未完成。",
            f"- 用户请求：{prompt_text}",
            f"- 失败原因：{error}",
            "说明：由于浏览器步骤未成功执行，本次没有拿到可验证的页面结果，因此不会推断登录是否成功、页面跳转结果或任何内部信息。",
        ]
    )


def _build_default_rag_context(query: str) -> str:
    documents = list_documents()
    if not documents:
        return ""
    chunks = search_chunks(query, top_k=3)
    if not chunks:
        return ""
    return "\n\n".join(
        f"[资料 {idx + 1}] 文件：{chunk['file_name']}\n内容：{chunk['content']}"
        for idx, chunk in enumerate(chunks)
    )


def _summarize_search(query: str, results: list) -> str:
    prompt_lines = [
        "请基于以下联网资料，生成一段适合内部演示的中文答复。",
        "要求：先给结论，再给 3 个关键信息点，最后补一句下一步建议。",
        "",
        f"用户问题：{query}",
        "",
        "联网结果：",
    ]
    for item in results[:6]:
        prompt_lines.append(f"- 标题：{item.title}")
        prompt_lines.append(f"  摘要：{item.snippet}")
        prompt_lines.append(f"  来源：{item.source}")
        prompt_lines.append(f"  链接：{item.url}")
    return simple_chat(
        "\n".join(prompt_lines),
        system_prompt="你是企业内部的 Agent 助手，输出自然、清晰、适合演示。",
        temperature=0.3,
    )


def _run_browser_agent(session_id: str, prompt_text: str) -> tuple[str, dict[str, object]]:
    try:
        urls = _extract_url_candidates(prompt_text)
        click_target = _extract_click_target(prompt_text)
        username, password = _extract_login_credentials(prompt_text)

        if urls:
            steps = [_step("打开网页", "done", urls[0])]
            snapshot = execute_browser_tool(session_id, "browser_open_page", {"url": urls[0]})
            current_snapshot = snapshot
            fill_failed_reason = ""
            fill_attempted = bool(username and password)
            click_failed_reason = ""
            clicked_label = ""

            if fill_attempted:
                fill_result = execute_browser_tool(
                    session_id,
                    "browser_fill_login",
                    {"username": username, "password": password},
                )
                if fill_result.get("ok"):
                    current_snapshot = fill_result.get("snapshot", current_snapshot)
                    steps.append(_step("填写登录表单", "done", f"已填写用户名 {username} 和密码"))
                else:
                    fill_failed_reason = str(fill_result.get("error") or "登录表单填写失败")
                    current_snapshot = fill_result.get("snapshot", current_snapshot)
                    steps.append(_step("填写登录表单", "failed", fill_failed_reason))

            effective_click_target = click_target or ("登录" if fill_attempted else "")
            if click_target:
                matched = _find_clickable_match(current_snapshot, effective_click_target)
                if matched:
                    current_snapshot = execute_browser_tool(
                        session_id,
                        "browser_click",
                        {"element_index": matched["element_index"]},
                    )
                    steps.append(
                        _step(
                            "点击页面元素",
                            "done",
                            f"已点击 {matched.get('text') or effective_click_target}",
                        )
                    )
                    clicked_label = str(matched.get("text") or effective_click_target)
                else:
                    click_failed_reason = f"未找到与“{effective_click_target}”匹配的按钮或链接"
                    steps.append(_step("点击页面元素", "failed", click_failed_reason))
            elif fill_attempted:
                matched = _find_clickable_match(current_snapshot, effective_click_target)
                if matched:
                    current_snapshot = execute_browser_tool(
                        session_id,
                        "browser_click",
                        {"element_index": matched["element_index"]},
                    )
                    steps.append(_step("点击页面元素", "done", f"已点击 {matched.get('text') or effective_click_target}"))
                    clicked_label = str(matched.get("text") or effective_click_target)
                else:
                    click_failed_reason = f"未找到与“{effective_click_target}”匹配的按钮或链接"
                    steps.append(_step("点击页面元素", "failed", click_failed_reason))

            if current_snapshot.get("ok"):
                answer = _format_browser_snapshot_answer(
                    prompt_text,
                    current_snapshot,
                    username_filled=username,
                    password_filled=bool(password),
                    fill_attempted=fill_attempted,
                    fill_failed_reason=fill_failed_reason,
                    click_target=effective_click_target,
                    clicked_label=clicked_label,
                    click_attempted=bool(effective_click_target),
                    click_failed_reason=click_failed_reason,
                )
                return answer, {
                    "task_title": "浏览器操作任务",
                    "steps": steps,
                    "skills": ["浏览器操作"],
                }

        return (
            "本次浏览器操作未执行。\n"
            f"- 用户请求：{prompt_text}\n"
            "- 原因：消息里没有检测到可访问的 http/https 地址。\n"
            "- 说明：请直接提供页面 URL，我会只基于实际打开后的页面内容返回结果。",
            {
                "task_title": "浏览器操作任务",
                "steps": [
                    _step("分析浏览器任务", "done", "已识别为浏览器相关需求"),
                    _step("等待明确地址", "failed", "未检测到可访问的 URL"),
                ],
                "skills": ["浏览器操作"],
            },
        )
    except Exception as exc:
        return (
            _format_browser_failure(prompt_text, exc),
            {
                "task_title": "浏览器操作任务",
                "steps": [
                    _step("分析浏览器任务", "done", "已识别为浏览器相关需求"),
                    _step("执行浏览器操作", "failed", str(exc)),
                ],
                "skills": ["浏览器操作"],
            },
        )


def _run_database_skill(prompt_text: str) -> tuple[str, dict[str, object]]:
    try:
        skill = _select_db_skill_for_request(prompt_text)
        connection = extract_connection_details(prompt_text, str(skill.get("db_engine") or "sqlite"))
    except Exception as exc:
        return (
            f"数据库技能不可用：{exc}",
            {
                "task_title": "数据库技能任务",
                "steps": [
                    _step("识别数据库请求", "done", "已识别到数据库请求"),
                    _step("检查技能安装", "failed", str(exc)),
                ],
                "skills": ["数据库技能"],
            },
        )

    query = _extract_select_query(prompt_text)
    if query:
        try:
            result = db_skill_run_readonly_query(query, skill, connection)
        except Exception as exc:
            return (
                f"数据库技能执行失败：{exc}",
                {
                    "task_title": "数据库技能任务",
                    "steps": [
                        _step("识别数据库请求", "done", "已识别到只读 SQL 请求"),
                        _step("连接数据库", "failed", str(exc)),
                    ],
                    "skills": ["数据库技能"],
                },
            )
        preview = json.dumps(result["rows"], ensure_ascii=False, indent=2)
        answer = "\n".join(
            [
                "数据库技能执行完成。",
                f"- 当前数据库：{connection_summary(skill, connection)}",
                f"- 查询语句：{result['query']}",
                f"- 返回行数：{result['row_count']}",
                "",
                "结果预览：",
                preview or "[]",
            ]
        )
        return answer, {
            "task_title": "数据库技能任务",
            "steps": [
                _step("识别数据库请求", "done", "已识别到只读 SQL 请求"),
                _step("连接数据库", "done", f"已连接数据库：{connection_summary(skill, connection)}"),
                _step("执行查询", "done", f"已返回 {result['row_count']} 行结果"),
            ],
            "skills": ["数据库技能"],
        }

    try:
        tables = db_skill_list_tables(skill, connection)
    except Exception as exc:
        return (
            f"数据库技能执行失败：{exc}",
            {
                "task_title": "数据库技能任务",
                "steps": [
                    _step("识别数据库请求", "done", "已识别到数据库结构查询需求"),
                    _step("连接数据库", "failed", str(exc)),
                ],
                "skills": ["数据库技能"],
            },
        )
    answer = "\n".join(
        [
            "数据库技能执行完成。",
            f"- 当前数据库：{connection_summary(skill, connection)}",
            f"- 表数量：{len(tables)}",
            f"- 表列表：{', '.join(tables) if tables else '暂无业务表'}",
        ]
    )
    return answer, {
        "task_title": "数据库技能任务",
        "steps": [
            _step("识别数据库请求", "done", "已识别到数据库结构查询需求"),
            _step("连接数据库", "done", f"已连接数据库：{connection_summary(skill, connection)}"),
            _step("读取表结构", "done", f"已识别 {len(tables)} 张表"),
        ],
        "skills": ["数据库技能"],
    }


def _draft_email_templates(prompt_text: str, history_items: list[dict]) -> list[dict[str, str]]:
    compact = prompt_text.replace(" ", "")
    templates: list[dict[str, str]] = []
    today = datetime.now().strftime("%Y-%m-%d")

    if "考试认知" in compact or ("考试" in compact and "认知" in compact):
        templates.append(
            {
                "category": "exam_notice",
                "subject": f"关于考试认知与备考安排的通知 | {today}",
                "recipients": "全员",
                "body_markdown": (
                    "各位同事：\n\n"
                    "为统一考试认知、减少信息偏差，请大家关注以下事项：\n\n"
                    "1. 本次考试目标是统一关键知识认知，帮助团队对齐基本要求。\n"
                    "2. 请按照统一时间窗口完成学习与准备，避免临近截止集中处理。\n"
                    "3. 如对考试范围、形式或安排存在疑问，请及时向组织方反馈。\n\n"
                    "请大家提前规划时间，按要求完成准备工作。谢谢配合。"
                ),
            }
        )

    if "会议纪要" in compact or "会议总结" in compact:
        history_context = "\n".join(
            f"- {item['role']}: {item['content'][:120]}"
            for item in history_items[-8:]
        )
        body = simple_chat(
            "\n".join(
                [
                    "请生成一封企业内部会议纪要邮件，使用中文 Markdown。",
                    "结构包含：会议主题、核心结论、行动项、下一步安排。",
                    "如果上下文不足，就写成适合演示的简洁版本。",
                    "",
                    f"用户需求：{prompt_text}",
                    "",
                    "最近上下文：",
                    history_context or "- 暂无额外上下文",
                ]
            ),
            system_prompt="你是企业内部邮件助手，输出清晰、正式、适合直接发送的会议纪要邮件正文。",
            temperature=0.3,
        )
        templates.append(
            {
                "category": "meeting_minutes",
                "subject": f"会议纪要 | {today}",
                "recipients": "全员",
                "body_markdown": body,
            }
        )

    if templates:
        return templates

    fallback_body = simple_chat(
        "\n".join(
            [
                "请根据以下需求起草一封企业内部邮件，使用中文 Markdown。",
                "输出只需要邮件正文，不要额外解释。",
                "",
                f"需求：{prompt_text}",
            ]
        ),
        system_prompt="你是企业内部邮件助手，擅长起草简洁清晰的通知邮件。",
        temperature=0.4,
    )
    return [
        {
            "category": "general",
            "subject": f"内部通知 | {today}",
            "recipients": "相关同事",
            "body_markdown": fallback_body,
        }
    ]


def _build_chat_conversation(session_id: str, prompt_text: str) -> tuple[list[dict[str, str]], list[dict], str]:
    rag_context = _build_default_rag_context(prompt_text)
    history_items = load_messages(APP_NAME, session_id, limit=16)
    conversation = [
        {
            "role": "system",
            "content": (
                "你是一个模拟 OpenClaw 风格的中文 Agent 工作台。"
                "默认会结合用户已添加的知识进行回答，但不要直接暴露检索片段。"
                "回答要简洁、移动端友好，并在合适时主动提示下一步。"
            ),
        }
    ]
    if rag_context:
        conversation.append(
            {
                "role": "system",
                "content": f"以下是与当前问题相关的知识背景，可用于辅助回答：\n{rag_context}",
            }
        )
    conversation.extend(
        {"role": item["role"], "content": item["content"]}
        for item in history_items
    )
    return conversation, history_items, rag_context


def _build_chat_assistant_meta(prompt_text: str, history_items: list[dict], rag_context: str) -> dict[str, object]:
    if _is_simple_chat_request(prompt_text):
        return {}
    assistant_meta: dict[str, object] = {
        "task_title": "对话生成",
        "steps": [
            _step("读取上下文", "done", f"已载入最近 {min(len(history_items), 16)} 条会话"),
            _step("知识增强", "done", "已自动结合本地知识背景"),
            _step("生成答复", "done", "已生成自然对话回复"),
        ],
    }
    if not rag_context:
        assistant_meta["steps"][1] = _step("知识增强", "done", "当前未命中额外知识，直接按上下文回答")
    return assistant_meta


def _generate_non_stream_response(
    session_id: str,
    prompt_text: str,
    image_bytes: bytes | None,
    image_content_type: str,
    metadata: dict[str, object],
    allow_scheduling: bool = True,
) -> tuple[str, dict[str, object]] | None:
    if image_bytes is not None:
        answer = vision_chat(
            prompt_text or "请分析这张图片，提取关键信息，并给出下一步建议。",
            image_bytes,
            image_mime_type=image_content_type,
            system_prompt="你是模拟 OpenClaw 风格的多模态助理，回答自然、清晰、适合演示。",
        )
        return answer, {
            "task_title": "图片理解任务",
            "steps": [
                _step("接收图片", "done", str(metadata.get("image_name", "已接收图片"))),
                _step("视觉分析", "done", "已识别画面主体和关键信息"),
                _step("生成答复", "done", "已整理为可继续追问的结论"),
            ],
        }

    if _is_email_request(prompt_text):
        history_items = load_messages(APP_NAME, session_id, limit=16)
        email_records = []
        for spec in _draft_email_templates(prompt_text, history_items):
            email_records.append(
                _append_email_record(
                    session_id=session_id,
                    subject=spec["subject"],
                    recipients=spec["recipients"],
                    body_markdown=spec["body_markdown"],
                    category=spec["category"],
                )
            )
        answer_lines = ["已完成邮件发送（演示）：", ""]
        for item in email_records:
            answer_lines.append(f"- **{item['subject']}**")
            answer_lines.append(f"  - 收件人：{item['recipients']}")
            answer_lines.append("  - 状态：已发送")
        return "\n".join(answer_lines), {
            "task_title": "邮件发送任务",
            "steps": [
                _step("识别邮件需求", "done", "已识别到发送邮件场景"),
                _step("生成邮件内容", "done", f"已生成 {len(email_records)} 封邮件"),
                _step("执行发送", "done", "已完成演示发送并写入邮件面板"),
            ],
        }

    if allow_scheduling:
        schedule_request = _extract_schedule_request(prompt_text)
        if schedule_request is not None:
            task = _create_scheduled_action_task(
                session_id=session_id,
                prompt_text=prompt_text,
                action_prompt=str(schedule_request["action_prompt"]),
                delay_seconds=schedule_request.get("delay_seconds"),
                schedule_mode=str(schedule_request.get("schedule_mode") or "once"),
                hour=schedule_request.get("hour"),
                minute=schedule_request.get("minute"),
            )
            schedule_label = "每天执行" if task.get("schedule_mode") == "daily" else "稍后执行"
            return (
                "\n".join(
                    [
                        "已创建通用定时任务。",
                        f"- 任务编号：{task['task_id'][:8]}",
                        f"- 执行动作：{task['action_prompt']}",
                        f"- 调度方式：{schedule_label}",
                        f"- 下次执行：{task['run_at'][:19].replace('T', ' ')}",
                    ]
                ),
                {
                    "task_title": "已创建定时任务",
                    "steps": [
                        _step("理解需求", "done", "已识别到通用定时任务需求"),
                        _step("持久化任务", "done", f"任务已保存，编号 {task['task_id'][:8]}"),
                        _step("等待执行", "running", f"计划执行时间：{task['run_at'][:19].replace('T', ' ')}"),
                    ],
                    "skills": ["定时任务"],
                },
            )

    if _is_news_push_request(prompt_text):
        digest = refresh_ai_digest(8.0)
        push_result = push_ai_digest_to_wechat()
        return (
            f"{digest}\n\n推送状态：{push_result['status']}",
            {
                "task_title": "AI 早报即时任务",
                "steps": [
                    _step("整理资讯", "done", "已完成最新 AI 资讯整理"),
                    _step("推送企业微信", "done", push_result["status"]),
                ],
            },
        )

    if _is_search_request(prompt_text):
        results = search_web(prompt_text, 6)
        summary = _summarize_search(prompt_text, results)
        return (
            summary,
            {
                "task_title": "联网搜索任务",
                "steps": [
                    _step("解析查询", "done", "已识别联网搜索意图"),
                    _step("搜索资料", "done", f"找到 {len(results)} 条候选结果"),
                    _step("整理结论", "done", "已生成适合演示的答复"),
                ],
            },
        )

    if _is_kb_presence_request(prompt_text):
        return _answer_kb_presence(prompt_text)

    if _is_skill_install_request(prompt_text):
        answer, assistant_meta, task_id = _build_skill_install_ack(session_id, prompt_text)
        if task_id:
            assistant_meta["pending_skill_install_task_id"] = task_id
        return answer, assistant_meta

    if _is_database_skill_request(prompt_text):
        return _run_database_skill(prompt_text)

    if _is_browser_request(prompt_text):
        return _run_browser_agent(session_id, prompt_text)

    return None


def _format_sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _chunk_text(text: str, chunk_size: int = 24) -> list[str]:
    return [text[index:index + chunk_size] for index in range(0, len(text), chunk_size)] or [""]


def _pop_pending_skill_install_task_id(metadata: dict[str, object]) -> str | None:
    task_id = metadata.pop("pending_skill_install_task_id", None)
    return str(task_id) if task_id else None


@app.on_event("startup")
def startup() -> None:
    _restore_pending_tasks()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"session_id": str(uuid4())})


@app.get("/api/history")
async def history(session_id: str) -> dict[str, list[dict[str, object]]]:
    items = load_messages(APP_NAME, session_id, limit=40)
    return {"messages": [_message_payload(item) for item in items]}


@app.get("/api/kb-docs")
async def kb_docs() -> dict[str, list[dict[str, object]]]:
    return {"documents": list_documents()}


@app.get("/api/tasks")
async def tasks(session_id: str) -> dict[str, list[dict[str, object]]]:
    items = sorted(
        (
            _task_payload(task)
            for task in _load_tasks()
            if task["session_id"] == session_id
        ),
        key=lambda item: item.get("created_at") or "",
        reverse=True,
    )[:10]
    return {"tasks": items}


@app.get("/api/skills")
async def skills() -> dict[str, list[dict[str, str]]]:
    return {"skills": _skill_catalog()}


@app.get("/api/memory")
async def memory(session_id: str) -> dict[str, object]:
    return {"memory": _memory_payload(session_id)}


@app.get("/api/emails")
async def emails(session_id: str) -> dict[str, list[dict[str, object]]]:
    items = [
        _email_payload(item)
        for item in reversed(_load_emails())
        if item.get("session_id") == session_id
    ][:10]
    return {"emails": items}


@app.post("/api/kb-upload")
async def kb_upload(file: UploadFile = File(...)) -> dict[str, object]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".txt", ".md", ".docx"}:
        raise HTTPException(status_code=400, detail="仅支持 txt、md、docx 文档")
    saved_path = KB_UPLOADS_DIR / f"{uuid4().hex}{suffix}"
    saved_path.write_bytes(await file.read())
    try:
        text = extract_text_from_file(saved_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"文档解析失败：{exc}") from exc
    document = add_document(file.filename or saved_path.name, text)
    return {
        "document": {
            "doc_id": document["doc_id"],
            "file_name": document["file_name"],
            "chunk_count": document["chunk_count"],
        },
        "documents": list_documents(),
    }


@app.post("/api/kb-delete")
async def kb_delete(doc_id: str = Form(...)) -> dict[str, object]:
    if not delete_document(doc_id.strip()):
        raise HTTPException(status_code=404, detail="未找到要删除的知识文档")
    return {"ok": True, "documents": list_documents()}


@app.post("/api/clear")
async def clear_context(session_id: str = Form(...)) -> dict[str, object]:
    delete_messages(APP_NAME, session_id)
    _remove_session_tasks(session_id)
    close_browser_session(session_id)
    return {"ok": True}


@app.post("/api/message")
async def message(
    session_id: str = Form(...),
    text: str = Form(""),
    image: UploadFile | None = File(None),
) -> dict[str, object]:
    session_id = session_id.strip()
    prompt_text = text.strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="缺少 session_id")
    if not prompt_text and image is None:
        raise HTTPException(status_code=400, detail="请输入消息或上传图片")

    metadata: dict[str, object] = {}
    image_bytes: bytes | None = None
    if image is not None and image.filename:
        suffix = Path(image.filename).suffix.lower() or ".jpg"
        file_name = f"{session_id}-{uuid4().hex}{suffix}"
        image_bytes = await image.read()
        image_path = UPLOADS_DIR / file_name
        image_path.write_bytes(image_bytes)
        metadata = {
            "image_url": f"/uploads/{file_name}",
            "image_name": image.filename,
        }

    user_record = prompt_text or "请帮我分析这张图片。"
    save_message(APP_NAME, session_id, "user", user_record, metadata=metadata)

    try:
        if image_bytes is not None:
            answer = await run_in_threadpool(
                vision_chat,
                prompt_text or "请分析这张图片，提取关键信息，并给出下一步建议。",
                image_bytes,
                image_mime_type=image.content_type or "image/jpeg",
                system_prompt="你是模拟 OpenClaw 风格的多模态助理，回答自然、清晰、适合演示。",
            )
            assistant_meta = {
                "task_title": "图片理解任务",
                "steps": [
                    _step("接收图片", "done", metadata.get("image_name", "已接收图片")),
                    _step("视觉分析", "done", "已识别画面主体和关键信息"),
                    _step("生成答复", "done", "已整理为可继续追问的结论"),
                ],
            }
        elif _is_email_request(prompt_text):
            history_items = load_messages(APP_NAME, session_id, limit=16)
            email_records = []
            for spec in _draft_email_templates(prompt_text, history_items):
                email_records.append(
                    _append_email_record(
                        session_id=session_id,
                        subject=spec["subject"],
                        recipients=spec["recipients"],
                        body_markdown=spec["body_markdown"],
                        category=spec["category"],
                    )
                )
            answer_lines = ["已完成邮件发送（演示）：", ""]
            for item in email_records:
                answer_lines.append(f"- **{item['subject']}**")
                answer_lines.append(f"  - 收件人：{item['recipients']}")
                answer_lines.append(f"  - 状态：已发送")
            answer = "\n".join(answer_lines)
            assistant_meta = {
                "task_title": "邮件发送任务",
                "steps": [
                    _step("识别邮件需求", "done", "已识别发送邮件场景"),
                    _step("生成邮件内容", "done", f"已生成 {len(email_records)} 封邮件"),
                    _step("执行发送", "done", "已完成演示发送并写入邮件面板"),
                ],
            }
        elif _extract_schedule_request(prompt_text) is not None:
            schedule_request = _extract_schedule_request(prompt_text) or {}
            task = _create_scheduled_action_task(
                session_id=session_id,
                prompt_text=prompt_text,
                action_prompt=str(schedule_request.get("action_prompt") or prompt_text),
                delay_seconds=schedule_request.get("delay_seconds"),
                schedule_mode=str(schedule_request.get("schedule_mode") or "once"),
                hour=schedule_request.get("hour"),
                minute=schedule_request.get("minute"),
            )
            schedule_label = "每天执行" if task.get("schedule_mode") == "daily" else "稍后执行"
            answer = "\n".join(
                [
                    "已创建通用定时任务。",
                    f"- 任务编号：{task['task_id'][:8]}",
                    f"- 执行动作：{task['action_prompt']}",
                    f"- 调度方式：{schedule_label}",
                    f"- 下次执行：{task['run_at'][:19].replace('T', ' ')}",
                ]
            )
            assistant_meta = {
                "task_title": "已创建定时任务",
                "steps": [
                    _step("理解需求", "done", "已识别到通用定时任务需求"),
                    _step("持久化任务", "done", f"任务已保存，编号 {task['task_id'][:8]}"),
                    _step("等待执行", "running", f"计划执行时间：{task['run_at'][:19].replace('T', ' ')}"),
                ],
                "skills": ["定时任务"],
            }
        elif _is_news_push_request(prompt_text):
            digest = await run_in_threadpool(refresh_ai_digest, 8.0)
            push_result = await run_in_threadpool(push_ai_digest_to_wechat)
            answer = f"{digest}\n\n推送状态：{push_result['status']}"
            assistant_meta = {
                "task_title": "AI 早报即时任务",
                "steps": [
                    _step("整理资讯", "done", "已完成最新 AI 资讯整理"),
                    _step("推送企业微信", "done", push_result["status"]),
                ],
            }
        elif _is_search_request(prompt_text):
            results = await run_in_threadpool(search_web, prompt_text, 6)
            summary = await run_in_threadpool(_summarize_search, prompt_text, results)
            answer = summary
            assistant_meta = {
                "task_title": "联网搜索任务",
                "steps": [
                    _step("解析查询", "done", "已识别联网搜索意图"),
                    _step("搜索资料", "done", f"找到 {len(results)} 条候选结果"),
                    _step("整理结论", "done", "已生成适合演示的答复"),
                ],
            }
        elif _is_kb_presence_request(prompt_text):
            answer, assistant_meta = await run_in_threadpool(_answer_kb_presence, prompt_text)
        elif _is_skill_install_request(prompt_text):
            answer, assistant_meta, _ = _build_skill_install_ack(session_id, prompt_text)
        elif _is_database_skill_request(prompt_text):
            answer, assistant_meta = await run_in_threadpool(_run_database_skill, prompt_text)
        elif _is_browser_request(prompt_text):
            answer, assistant_meta = await run_in_threadpool(_run_browser_agent, session_id, prompt_text)
        else:
            rag_context = await run_in_threadpool(_build_default_rag_context, prompt_text)
            history_items = load_messages(APP_NAME, session_id, limit=16)
            conversation = [
                {
                    "role": "system",
                    "content": (
                        "你是一个模拟 OpenClaw 风格的中文 Agent 工作台。"
                        "默认会结合用户已增加的知识进行回答，但不要直接暴露检索片段。"
                        "回答要简洁、移动端友好，并在合适时主动提示下一步。"
                    ),
                }
            ]
            if rag_context:
                conversation.append(
                    {
                        "role": "system",
                        "content": f"以下是与当前问题相关的知识背景，可用于辅助回答：\n{rag_context}",
                    }
                )
            conversation.extend(
                {"role": item["role"], "content": item["content"]}
                for item in history_items
            )
            response = await run_in_threadpool(partial(chat_completion, conversation, temperature=0.45))
            answer = response.choices[0].message.content or ""
            if _is_simple_chat_request(prompt_text):
                assistant_meta = {}
            else:
                assistant_meta = {
                    "task_title": "对话生成",
                    "steps": [
                        _step("读取上下文", "done", f"已载入最近 {min(len(history_items), 16)} 条会话"),
                        _step("知识增强", "done", "已自动结合本地知识背景"),
                        _step("生成答复", "done", "已生成自然对话回复"),
                    ],
                }
                if not rag_context:
                    assistant_meta["steps"][1] = _step("知识增强", "done", "当前未命中额外知识，直接按上下文回答")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"大模型调用失败：{exc}") from exc

    pending_skill_install_task_id = _pop_pending_skill_install_task_id(assistant_meta)
    save_message(APP_NAME, session_id, "assistant", answer, metadata=assistant_meta)
    if pending_skill_install_task_id:
        _start_skill_install_task(pending_skill_install_task_id)
    full_history = load_messages(APP_NAME, session_id, limit=40)
    return {"assistant": answer, "messages": [_message_payload(item) for item in full_history]}


@app.post("/api/message-stream")
async def message_stream(
    session_id: str = Form(...),
    text: str = Form(""),
    image: UploadFile | None = File(None),
) -> StreamingResponse:
    session_id = session_id.strip()
    prompt_text = text.strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="缺少 session_id")
    if not prompt_text and image is None:
        raise HTTPException(status_code=400, detail="请输入消息或上传图片")

    metadata: dict[str, object] = {}
    image_bytes: bytes | None = None
    image_content_type = "image/jpeg"
    if image is not None and image.filename:
        suffix = Path(image.filename).suffix.lower() or ".jpg"
        file_name = f"{session_id}-{uuid4().hex}{suffix}"
        image_bytes = await image.read()
        image_content_type = image.content_type or "image/jpeg"
        image_path = UPLOADS_DIR / file_name
        image_path.write_bytes(image_bytes)
        metadata = {
            "image_url": f"/uploads/{file_name}",
            "image_name": image.filename,
        }

    user_record = prompt_text or "请帮我分析这张图片。"
    save_message(APP_NAME, session_id, "user", user_record, metadata=metadata)

    async def event_stream():
        answer = ""
        assistant_meta: dict[str, object] = {}
        try:
            yield _format_sse("start", {"ok": True})
            await asyncio.sleep(0)

            non_stream_result = await run_in_threadpool(
                _generate_non_stream_response,
                session_id=session_id,
                prompt_text=prompt_text,
                image_bytes=image_bytes,
                image_content_type=image_content_type,
                metadata=metadata,
            )
            if non_stream_result is not None:
                answer, assistant_meta = non_stream_result
                for chunk in _chunk_text(answer):
                    yield _format_sse("delta", {"delta": chunk})
                    await asyncio.sleep(0.02)
                pending_skill_install_task_id = _pop_pending_skill_install_task_id(assistant_meta)
                save_message(APP_NAME, session_id, "assistant", answer, metadata=assistant_meta)
                if pending_skill_install_task_id:
                    _start_skill_install_task(pending_skill_install_task_id)
                full_history = load_messages(APP_NAME, session_id, limit=40)
                yield _format_sse(
                    "done",
                    {
                        "assistant": answer,
                        "messages": [_message_payload(item) for item in full_history],
                    },
                )
                return

            conversation, history_items, rag_context = _build_chat_conversation(session_id, prompt_text)
            assistant_meta = _build_chat_assistant_meta(prompt_text, history_items, rag_context)

            stream = stream_chat_completion(conversation, temperature=0.45)
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if not delta:
                    continue
                answer += delta
                yield _format_sse("delta", {"delta": delta})
                await asyncio.sleep(0)

            save_message(APP_NAME, session_id, "assistant", answer, metadata=assistant_meta)
            full_history = load_messages(APP_NAME, session_id, limit=40)
            yield _format_sse(
                "done",
                {
                    "assistant": answer,
                    "messages": [_message_payload(item) for item in full_history],
                },
            )
        except Exception as exc:
            yield _format_sse("error", {"detail": f"大模型调用失败：{exc}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    uvicorn.run(app, host=settings.app_host, port=settings.mobile_openclaw_port)
