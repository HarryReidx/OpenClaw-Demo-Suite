from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import uvicorn


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_TARGET = os.getenv("APP_TARGET", "portal").strip()
HOST = os.getenv("APP_HOST", "0.0.0.0").strip() or "0.0.0.0"
PORT = int(os.getenv("APP_PORT", "8081"))

APP_FILES = {
    "portal": ROOT_DIR / "portal" / "main.py",
    "01": ROOT_DIR / "projects" / "01-basic-qa" / "main.py",
    "02": ROOT_DIR / "projects" / "02-memory-chat" / "main.py",
    "03": ROOT_DIR / "projects" / "03-file-agent" / "main.py",
    "04": ROOT_DIR / "projects" / "04-search-to-html" / "main.py",
    "05": ROOT_DIR / "projects" / "05-mobile-openclaw" / "main.py",
    "06": ROOT_DIR / "projects" / "06-ai-news-push" / "main.py",
    "07": ROOT_DIR / "projects" / "07-ai-rag" / "main.py",
}


def load_app(target: str):
    app_file = APP_FILES.get(target)
    if app_file is None:
        supported = ", ".join(APP_FILES)
        raise RuntimeError(f"Unsupported APP_TARGET={target!r}. Supported: {supported}")
    if not app_file.exists():
        raise RuntimeError(f"App entry not found: {app_file}")

    spec = importlib.util.spec_from_file_location(f"openclaw_{target}", app_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load app module from: {app_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    app = getattr(module, "app", None)
    if app is None:
        raise RuntimeError(f"No ASGI app named 'app' found in: {app_file}")
    return app


if __name__ == "__main__":
    uvicorn.run(load_app(APP_TARGET), host=HOST, port=PORT)
