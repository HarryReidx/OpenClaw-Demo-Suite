from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from shared.config import get_settings
from shared.db import DB_PATH


DEFAULT_SKILL_ID = "database-connector"
DEFAULT_SKILL_NAME = "数据库连接技能"


@dataclass(frozen=True)
class InstallableSkill:
    skill_id: str
    name: str
    description: str
    template_dir: str | None = None
    db_engine: str | None = None
    keywords: tuple[str, ...] = ()
    source: str = "local-template"

    def to_catalog_entry(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "template_dir": self.template_dir,
            "db_engine": self.db_engine,
            "keywords": list(self.keywords),
            "source": self.source,
        }


LOCAL_SKILL_CATALOG: tuple[InstallableSkill, ...] = (
    InstallableSkill(
        skill_id="database-connector",
        name="SQLite 数据库连接技能",
        description="连接当前演示仓库的 SQLite 数据库，支持列出表和执行只读 SQL。",
        template_dir="database-connector",
        db_engine="sqlite",
        keywords=("sqlite", "数据库", "sql", "database"),
    ),
    InstallableSkill(
        skill_id="database-connector-mysql",
        name="MySQL 数据库连接技能",
        description="连接 MySQL 数据库，支持列出表和执行只读 SQL，需要提供连接信息。",
        template_dir="database-connector-mysql",
        db_engine="mysql",
        keywords=("mysql", "数据库", "database"),
    ),
    InstallableSkill(
        skill_id="database-connector-postgres",
        name="PostgreSQL 数据库连接技能",
        description="连接 PostgreSQL 数据库，支持列出表和执行只读 SQL，需要提供连接信息。",
        template_dir="database-connector-postgres",
        db_engine="postgresql",
        keywords=("postgres", "postgresql", "pg", "数据库", "database"),
    ),
)


def _external_catalog() -> list[InstallableSkill]:
    path = get_settings().data_dir / "openclaw_skill_catalog.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    entries: list[InstallableSkill] = []
    for item in payload:
        try:
            skill_id = str(item["skill_id"]).strip()
            name = str(item.get("name") or skill_id)
            description = str(item.get("description") or "")
            template_dir = str(item.get("template_dir") or skill_id)
            db_engine = str(item.get("db_engine") or "")
            keywords = tuple(str(word) for word in item.get("keywords", []) if word)
            if not keywords and db_engine:
                keywords = (db_engine, "database", "数据库")
            entries.append(
                InstallableSkill(
                    skill_id=skill_id,
                    name=name,
                    description=description,
                    template_dir=template_dir,
                    db_engine=db_engine,
                    keywords=keywords,
                    source="local-catalog",
                )
            )
        except Exception:
            continue
    return entries


def _all_installable_skills() -> list[InstallableSkill]:
    merged: dict[str, InstallableSkill] = {item.skill_id: item for item in LOCAL_SKILL_CATALOG}
    for item in _external_catalog():
        merged[item.skill_id] = item
    return list(merged.values())


@dataclass(frozen=True)
class InstalledSkill:
    skill_id: str
    name: str
    description: str
    install_dir: Path
    db_engine: str
    db_path: str
    installed_at: str
    status: str = "installed"
    source: str = "local-template"

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "install_dir": str(self.install_dir),
            "db_engine": self.db_engine,
            "db_path": self.db_path,
            "installed_at": self.installed_at,
            "status": self.status,
            "source": self.source,
        }


def list_installable_skills() -> list[dict[str, Any]]:
    return [item.to_catalog_entry() for item in _all_installable_skills()]


def get_installable_skill(skill_id: str) -> dict[str, Any] | None:
    for item in _all_installable_skills():
        if item.skill_id == skill_id:
            return item.to_catalog_entry()
    return None


def match_installable_skill(text: str) -> dict[str, Any] | None:
    compact = re.sub(r"\s+", "", text.lower())
    scored: list[tuple[int, InstallableSkill]] = []
    for item in _all_installable_skills():
        matches = sum(1 for keyword in item.keywords if re.sub(r"\s+", "", keyword.lower()) in compact)
        if matches:
            scored.append((matches, item))
    if not scored:
        return None
    scored.sort(key=lambda pair: (pair[0], len(pair[1].keywords)), reverse=True)
    return scored[0][1].to_catalog_entry()


def select_installable_skill(text: str) -> tuple[InstallableSkill, str]:
    compact = re.sub(r"\s+", "", text.lower())
    mentions_mysql = "mysql" in compact
    mentions_postgres = "postgres" in compact or "postgresql" in compact
    mentions_sqlite = "sqlite" in compact
    matched = match_installable_skill(text)
    if matched:
        skill = InstallableSkill(
            skill_id=str(matched["skill_id"]),
            name=str(matched["name"]),
            description=str(matched["description"]),
            template_dir=str(matched.get("template_dir") or "") or None,
            db_engine=str(matched.get("db_engine") or "") or None,
            keywords=tuple(str(item) for item in matched.get("keywords", [])),
            source=str(matched.get("source") or "local-template"),
        )
        return skill, f"已匹配到本地候选技能：{matched['name']}，{matched['description']}"
    if mentions_mysql:
        raise ValueError("未发现可用的 MySQL skill 模板，请先在本地 catalog 中配置。")
    if mentions_postgres:
        raise ValueError("未发现可用的 PostgreSQL skill 模板，请先在本地 catalog 中配置。")
    if mentions_sqlite:
        raise ValueError("未发现可用的 SQLite skill 模板，请先在本地 catalog 中配置。")
    fallback = next((item for item in _all_installable_skills() if item.skill_id == DEFAULT_SKILL_ID), None)
    if not fallback:
        raise FileNotFoundError("Default installable skill not found.")
    return fallback, "当前未找到更精确的 skill 来源，已回退到默认的 SQLite 数据库连接技能。"


def _template_root(template_dir: str) -> Path:
    return get_settings().root_dir / "projects" / "05-mobile-openclaw" / "skill_templates" / template_dir


def _install_root() -> Path:
    return get_settings().codex_skills_dir


def _skill_dir(skill_id: str) -> Path:
    return _install_root() / skill_id


def _skill_installer_script() -> Path:
    return get_settings().codex_skills_dir / ".system" / "skill-installer" / "scripts" / "install-skill-from-github.py"


def install_database_skill(skill_id: str = DEFAULT_SKILL_ID, install_root: Path | None = None) -> dict[str, Any]:
    selected = get_installable_skill(skill_id)
    if not selected:
        raise FileNotFoundError(f"Unknown installable skill: {skill_id}")

    template_dir_name = str(selected.get("template_dir") or "")
    if not template_dir_name:
        raise FileNotFoundError(f"Skill {skill_id} is not backed by a local template.")

    target_root = install_root or _install_root()
    target_root.mkdir(parents=True, exist_ok=True)
    target_dir = target_root / skill_id
    template_dir = _template_root(template_dir_name)
    if not template_dir.exists():
        raise FileNotFoundError(f"Skill template not found: {template_dir}")

    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(template_dir, target_dir)

    default_path = str(Path(DB_PATH)) if selected.get("db_engine") == "sqlite" else ""
    installed = InstalledSkill(
        skill_id=skill_id,
        name=str(selected["name"]),
        description=str(selected["description"]),
        install_dir=target_dir,
        db_engine=str(selected.get("db_engine") or ""),
        db_path=default_path,
        installed_at=datetime.now().isoformat(),
    )

    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(json.dumps(installed.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return installed.to_dict()


def install_skill_from_github(url: str, name: str | None = None, install_root: Path | None = None) -> dict[str, Any]:
    script_path = _skill_installer_script()
    if not script_path.exists():
        raise FileNotFoundError(f"GitHub installer script not found: {script_path}")

    target_root = install_root or _install_root()
    command = [sys.executable, str(script_path), "--url", url, "--dest", str(target_root)]
    if name:
        command.extend(["--name", name])

    result = subprocess.run(command, capture_output=True, text=True, check=True)
    installed_name = name or _derive_skill_name_from_url(url)
    install_dir = target_root / installed_name
    manifest = {
        "skill_id": installed_name,
        "name": installed_name,
        "description": f"Installed from GitHub: {url}",
        "install_dir": str(install_dir),
        "db_engine": "",
        "db_path": "",
        "installed_at": datetime.now().isoformat(),
        "status": "installed",
        "source": "github",
        "installer_output": result.stdout.strip(),
    }
    manifest_path = install_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _derive_skill_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if "tree" in parts:
        index = parts.index("tree")
        if index + 2 < len(parts):
            return parts[-1]
    return parts[-1] if parts else "installed-skill"


def smoke_test_database_skill(
    skill_id: str | dict[str, Any] = DEFAULT_SKILL_ID,
    connection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = skill_id if isinstance(skill_id, dict) else {"skill_id": skill_id}
    actual_skill_id = str(manifest.get("skill_id") or DEFAULT_SKILL_ID)
    install_dir = _skill_dir(actual_skill_id)
    script_path = install_dir / "scripts" / "smoke_test.py"

    selected = get_installable_skill(actual_skill_id) or {}
    engine = str(
        selected.get("db_engine")
        or manifest.get("db_engine")
        or (connection.get("database") if connection else "")
        or "sqlite"
    )

    if script_path.exists() and engine == "sqlite":
        sqlite_path = ""
        if connection:
            sqlite_path = str(connection.get("path") or "")
        if not sqlite_path:
            sqlite_path = str(manifest.get("db_path") or DB_PATH)
        command = [sys.executable, str(script_path), "--database", "sqlite", "--path", str(Path(sqlite_path))]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            payload = json.loads(result.stdout.strip())
            payload["table_count"] = len(payload.get("tables", []))
            return payload
        except Exception as exc:
            return {"ok": False, "database": "sqlite", "error": str(exc)}

    details = connection or extract_connection_details("", engine)
    try:
        if engine == "sqlite":
            target = Path(details.get("path") or manifest.get("db_path") or DB_PATH)
            with sqlite3.connect(target) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                probe = cursor.fetchone()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                tables = [row[0] for row in cursor.fetchall()]
            return {
                "ok": True,
                "database": "sqlite",
                "path": str(target),
                "probe": probe[0] if probe else None,
                "tables": tables,
                "table_count": len(tables),
            }
        if engine == "mysql":
            conn = _connect_mysql(details)
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    probe = cursor.fetchone()
                    cursor.execute("SHOW TABLES")
                    rows = cursor.fetchall()
                tables = [next(iter(row.values())) if isinstance(row, dict) else row[0] for row in rows]
            finally:
                conn.close()
            return {"ok": True, "database": "mysql", "probe": probe[0] if probe else None, "tables": tables, "table_count": len(tables)}
        if engine == "postgresql":
            conn = _connect_postgres(details)
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    probe = cursor.fetchone()
                    cursor.execute(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                        ORDER BY table_name
                        """
                    )
                    tables = [row[0] for row in cursor.fetchall()]
            finally:
                conn.close()
            return {"ok": True, "database": "postgresql", "probe": probe[0] if probe else None, "tables": tables, "table_count": len(tables)}
        return {"ok": False, "database": engine, "error": f"Unsupported database engine: {engine}"}
    except Exception as exc:
        return {"ok": False, "database": engine, "error": str(exc)}


def extract_connection_details(text: str, db_engine: str) -> dict[str, Any]:
    if db_engine == "sqlite":
        path_match = re.search(r"([A-Za-z]:\\[^\s]+\.db|/[^\s]+\.db|[^\s]+\.db)", text)
        return {"database": "sqlite", "path": path_match.group(1) if path_match else str(Path(DB_PATH))}

    url_match = re.search(r"((?:mysql|postgres(?:ql)?)://[^\s]+)", text, flags=re.IGNORECASE)
    if url_match:
        parsed = urlparse(url_match.group(1))
        return {
            "database": "postgresql" if parsed.scheme.startswith("postgres") else "mysql",
            "host": parsed.hostname or "",
            "port": parsed.port or (5432 if parsed.scheme.startswith("postgres") else 3306),
            "user": parsed.username or "",
            "password": parsed.password or "",
            "database_name": (parsed.path or "").lstrip("/"),
        }

    return {
        "database": db_engine,
        "host": _extract_named_value(text, ("host", "主机")) or os.getenv(f"{db_engine.upper()}_HOST", ""),
        "port": _extract_named_value(text, ("port", "端口")) or os.getenv(f"{db_engine.upper()}_PORT", ""),
        "user": _extract_named_value(text, ("user", "username", "用户名")) or os.getenv(f"{db_engine.upper()}_USER", ""),
        "password": _extract_named_value(text, ("password", "密码")) or os.getenv(f"{db_engine.upper()}_PASSWORD", ""),
        "database_name": _extract_named_value(text, ("database", "db", "库名", "dbname")) or os.getenv(f"{db_engine.upper()}_DATABASE", ""),
    }


def connection_summary(skill: dict[str, Any], connection: dict[str, Any] | None = None) -> str:
    engine = str(skill.get("db_engine") or "")
    if connection is None:
        connection = extract_connection_details("", engine)
        if engine == "sqlite":
            connection["path"] = skill.get("db_path") or connection.get("path")
    if engine == "sqlite":
        return f"SQLite: {connection.get('path') or DB_PATH}"
    host = connection.get("host") or "未提供 host"
    port = connection.get("port") or ("3306" if engine == "mysql" else "5432")
    database_name = connection.get("database_name") or connection.get("database") or "未提供 database"
    return f"{engine}://{host}:{port}/{database_name}"


def _extract_named_value(text: str, aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        match = re.search(rf"{re.escape(alias)}\s*[:=：]\s*([^\s,，；;]+)", text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def list_tables(skill: dict[str, Any], connection: dict[str, Any] | None = None) -> list[str]:
    engine = str(skill.get("db_engine") or "")
    details = connection or extract_connection_details("", engine)
    if engine == "sqlite":
        target = Path(details.get("path") or skill.get("db_path") or DB_PATH)
        with sqlite3.connect(target) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return [row[0] for row in rows]

    if engine == "mysql":
        conn = _connect_mysql(details)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                rows = cursor.fetchall()
            return [next(iter(row.values())) if isinstance(row, dict) else row[0] for row in rows]
        finally:
            conn.close()

    if engine == "postgresql":
        conn = _connect_postgres(details)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                    """
                )
                rows = cursor.fetchall()
            return [row[0] for row in rows]
        finally:
            conn.close()

    raise ValueError(f"Unsupported database engine: {engine}")


def run_readonly_query(
    query: str,
    skill: dict[str, Any],
    connection: dict[str, Any] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    normalized = query.strip().rstrip(";")
    lowered = normalized.lower()
    if not lowered.startswith("select "):
        raise ValueError("当前数据库技能只允许执行只读 SELECT 查询。")

    limited_query = f"{normalized} LIMIT {limit}" if " limit " not in lowered else normalized
    engine = str(skill.get("db_engine") or "")
    details = connection or extract_connection_details("", engine)

    if engine == "sqlite":
        target = Path(details.get("path") or skill.get("db_path") or DB_PATH)
        with sqlite3.connect(target) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(limited_query).fetchall()
        items = [dict(row) for row in rows]
        return {"query": limited_query, "row_count": len(items), "rows": items}

    if engine == "mysql":
        conn = _connect_mysql(details)
        try:
            with conn.cursor() as cursor:
                cursor.execute(limited_query)
                rows = cursor.fetchall()
            items = [dict(row) for row in rows]
        finally:
            conn.close()
        return {"query": limited_query, "row_count": len(items), "rows": items}

    if engine == "postgresql":
        conn = _connect_postgres(details)
        try:
            with conn.cursor() as cursor:
                cursor.execute(limited_query)
                columns = [item[0] for item in cursor.description or []]
                rows = cursor.fetchall()
            items = [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()
        return {"query": limited_query, "row_count": len(items), "rows": items}

    raise ValueError(f"Unsupported database engine: {engine}")


def _connect_mysql(details: dict[str, Any]):
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as exc:
        raise RuntimeError("MySQL skill 需要先安装 pymysql 依赖。") from exc

    host = str(details.get("host") or "")
    user = str(details.get("user") or "")
    password = str(details.get("password") or "")
    database_name = str(details.get("database_name") or details.get("database") or "")
    port = int(details.get("port") or 3306)
    if not all([host, user, database_name]):
        raise ValueError("MySQL 技能需要提供 host、user、database 等连接信息。")
    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database_name,
        cursorclass=DictCursor,
        autocommit=True,
    )


def _connect_postgres(details: dict[str, Any]):
    try:
        import psycopg
    except ImportError:
        try:
            import psycopg2 as psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL skill 需要先安装 psycopg 或 psycopg2 依赖。") from exc

    host = str(details.get("host") or "")
    user = str(details.get("user") or "")
    password = str(details.get("password") or "")
    database_name = str(details.get("database_name") or details.get("database") or "")
    port = int(details.get("port") or 5432)
    if not all([host, user, database_name]):
        raise ValueError("PostgreSQL 技能需要提供 host、user、database 等连接信息。")
    return psycopg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=database_name,
    )
