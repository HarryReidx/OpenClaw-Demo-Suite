from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.config import get_settings
from shared.db import DB_PATH


DEFAULT_SKILL_ID = "database-connector"
DEFAULT_SKILL_NAME = "数据库连接技能"


@dataclass(frozen=True)
class InstalledSkill:
    skill_id: str
    name: str
    description: str
    install_dir: Path
    db_engine: str
    db_path: Path
    installed_at: str
    status: str = "installed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "install_dir": str(self.install_dir),
            "db_engine": self.db_engine,
            "db_path": str(self.db_path),
            "installed_at": self.installed_at,
            "status": self.status,
        }


def _template_root() -> Path:
    return get_settings().root_dir / "projects" / "05-mobile-openclaw" / "skill_templates" / DEFAULT_SKILL_ID


def _install_root() -> Path:
    return get_settings().codex_skills_dir


def _skill_dir() -> Path:
    return _install_root() / DEFAULT_SKILL_ID


def install_database_skill(install_root: Path | None = None) -> dict[str, Any]:
    target_root = install_root or _install_root()
    target_root.mkdir(parents=True, exist_ok=True)
    target_dir = target_root / DEFAULT_SKILL_ID
    template_dir = _template_root()
    if not template_dir.exists():
        raise FileNotFoundError(f"Skill template not found: {template_dir}")

    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(template_dir, target_dir)

    installed = InstalledSkill(
        skill_id=DEFAULT_SKILL_ID,
        name=DEFAULT_SKILL_NAME,
        description="连接当前演示仓库的 SQLite 数据库，支持列出表和执行只读 SQL。",
        install_dir=target_dir,
        db_engine="sqlite",
        db_path=Path(DB_PATH),
        installed_at=__import__("datetime").datetime.now().isoformat(),
    )

    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(json.dumps(installed.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return installed.to_dict()


def smoke_test_database_skill(db_path: Path | None = None) -> dict[str, Any]:
    target = Path(db_path or DB_PATH)
    install_dir = _skill_dir()
    script_path = install_dir / "scripts" / "smoke_test.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Smoke test script not found: {script_path}")

    result = subprocess.run(
        [sys.executable, str(script_path), "--database", "sqlite", "--path", str(target)],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout.strip())
    payload["table_count"] = len(payload.get("tables", []))
    return payload


def list_tables(db_path: Path | None = None) -> list[str]:
    target = Path(db_path or DB_PATH)
    with sqlite3.connect(target) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    return [row[0] for row in rows]


def run_readonly_query(query: str, db_path: Path | None = None, limit: int = 20) -> dict[str, Any]:
    normalized = query.strip().rstrip(";")
    lowered = normalized.lower()
    if not lowered.startswith("select "):
        raise ValueError("当前数据库技能只允许执行只读 SELECT 查询。")

    limited_query = f"{normalized} LIMIT {limit}" if " limit " not in lowered else normalized
    target = Path(db_path or DB_PATH)
    with sqlite3.connect(target) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(limited_query).fetchall()
    items = [dict(row) for row in rows]
    return {"query": limited_query, "row_count": len(items), "rows": items}
