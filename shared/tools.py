from __future__ import annotations

from pathlib import Path

from shared.config import get_settings


WRITE_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "write_demo_file",
        "description": "Create or overwrite a file inside the local demo_outputs folder.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "A safe relative file name like launch-plan.txt or report/demo.html",
                },
                "content": {
                    "type": "string",
                    "description": "The full text content to save into the file.",
                },
            },
            "required": ["filename", "content"],
        },
    },
}


WRITE_HTML_TOOL = {
    "type": "function",
    "function": {
        "name": "write_demo_html",
        "description": "Create or overwrite an HTML file inside the local demo_outputs folder.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "A safe file name ending with .html",
                },
                "html": {
                    "type": "string",
                    "description": "The HTML markup to write to disk.",
                },
            },
            "required": ["filename", "html"],
        },
    },
}


def _safe_path(filename: str) -> Path:
    base = get_settings().demo_outputs_dir.resolve()
    candidate = (base / filename).resolve()
    if base not in candidate.parents and candidate != base:
        raise ValueError("Only demo_outputs is writable in this demo.")
    return candidate


def execute_demo_tool(name: str, args: dict) -> dict:
    if name == "write_demo_file":
        path = _safe_path(args["filename"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"], encoding="utf-8")
        return {"ok": True, "path": str(path), "bytes": path.stat().st_size}
    if name == "write_demo_html":
        filename = args["filename"]
        if not filename.lower().endswith(".html"):
            filename = f"{filename}.html"
        path = _safe_path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["html"], encoding="utf-8")
        return {"ok": True, "path": str(path), "bytes": path.stat().st_size}
    return {"ok": False, "error": f"Unknown tool: {name}"}

