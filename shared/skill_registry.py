from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from shared.config import get_settings


def _installer_script() -> Path:
    return (
        get_settings().codex_home
        / "skills"
        / ".system"
        / "skill-installer"
        / "scripts"
        / "install-skill-from-github.py"
    )


def parse_github_install_spec(text: str) -> dict[str, str] | None:
    lowered = text.lower()
    if "github.com" not in lowered and "repo" not in lowered:
        return None

    url_match = re.search(r"(https?://github\.com/[^\s)]+)", text, flags=re.IGNORECASE)
    if url_match:
        url = url_match.group(1)
        tree_match = re.search(
            r"https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.+)",
            url,
            flags=re.IGNORECASE,
        )
        if tree_match:
            owner, repo, ref, path = tree_match.groups()
            skill_id = Path(path).name
            return {
                "url": url,
                "repo": f"{owner}/{repo}",
                "path": path,
                "ref": ref,
                "skill_id": skill_id,
            }
        return {"url": url}

    repo_match = re.search(r"repo\s*[:=]?\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", text, flags=re.IGNORECASE)
    path_match = re.search(r"path\s*[:=]?\s*([A-Za-z0-9_./-]+)", text, flags=re.IGNORECASE)
    ref_match = re.search(r"ref\s*[:=]?\s*([A-Za-z0-9_.-]+)", text, flags=re.IGNORECASE)
    if repo_match and path_match:
        repo = repo_match.group(1)
        path = path_match.group(1)
        skill_id = Path(path).name
        spec = {"repo": repo, "path": path, "skill_id": skill_id}
        if ref_match:
            spec["ref"] = ref_match.group(1)
        return spec

    return {"error": "missing_repo_or_path"}


def _read_skill_metadata(skill_dir: Path) -> dict[str, str]:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return {"name": skill_dir.name, "description": "Installed from GitHub."}

    content = skill_md.read_text(encoding="utf-8", errors="ignore")
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            name_match = re.search(r"^name:\s*\"?(.+?)\"?\s*$", frontmatter, flags=re.MULTILINE)
            desc_match = re.search(r"^description:\s*\"?(.+?)\"?\s*$", frontmatter, flags=re.MULTILINE)
            return {
                "name": name_match.group(1).strip() if name_match else skill_dir.name,
                "description": desc_match.group(1).strip() if desc_match else "Installed from GitHub.",
            }
    return {"name": skill_dir.name, "description": "Installed from GitHub."}


def install_skill_from_github(spec: dict[str, str], dest_root: Path | None = None) -> dict[str, Any]:
    script = _installer_script()
    if not script.exists():
        raise FileNotFoundError(f"Skill installer script not found: {script}")

    dest = dest_root or get_settings().codex_skills_dir
    args = [sys.executable, str(script)]
    if spec.get("url"):
        args.extend(["--url", spec["url"]])
    elif spec.get("repo") and spec.get("path"):
        args.extend(["--repo", spec["repo"], "--path", spec["path"]])
        if spec.get("ref"):
            args.extend(["--ref", spec["ref"]])
    else:
        raise ValueError("未识别到 GitHub repo/path，请提供 repo 和 path。")
    args.extend(["--dest", str(dest)])

    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "GitHub 安装失败").strip())

    skill_id = spec.get("skill_id") or Path(spec.get("path") or "").name
    if not skill_id:
        raise ValueError("无法从 GitHub 路径识别 skill 名称。")

    install_dir = dest / skill_id
    metadata = _read_skill_metadata(install_dir)
    payload = {
        "skill_id": skill_id,
        "name": metadata["name"],
        "description": metadata["description"],
        "install_dir": str(install_dir),
        "installed_at": datetime.now().isoformat(),
        "status": "installed",
        "source": "github",
        "github": {
            "repo": spec.get("repo"),
            "path": spec.get("path"),
            "ref": spec.get("ref"),
            "url": spec.get("url"),
        },
    }

    manifest_path = install_dir / "manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def run_optional_smoke_test(install_dir: Path) -> dict[str, Any]:
    script_path = install_dir / "scripts" / "smoke_test.py"
    if not script_path.exists():
        return {"ok": False, "error": "No smoke test found."}
    result = subprocess.run([sys.executable, str(script_path)], capture_output=True, text=True)
    if result.returncode != 0:
        return {"ok": False, "error": (result.stderr or result.stdout or "Smoke test failed").strip()}
    output = result.stdout.strip()
    if not output:
        return {"ok": True}
    try:
        return {"ok": True, "output": json.loads(output)}
    except Exception:
        return {"ok": True, "output": output}
