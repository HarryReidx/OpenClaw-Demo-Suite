from __future__ import annotations

import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent

APPS = [
    ("portal", ROOT / "portal" / "main.py"),
    ("01-basic-qa", ROOT / "projects" / "01-basic-qa" / "main.py"),
    ("02-memory-chat", ROOT / "projects" / "02-memory-chat" / "main.py"),
    ("03-file-agent", ROOT / "projects" / "03-file-agent" / "main.py"),
    ("04-search-to-html", ROOT / "projects" / "04-search-to-html" / "main.py"),
    ("05-mobile-openclaw", ROOT / "projects" / "05-mobile-openclaw" / "main.py"),
    ("06-ai-news-push", ROOT / "projects" / "06-ai-news-push" / "main.py"),
    ("07-ai-rag", ROOT / "projects" / "07-ai-rag" / "main.py"),
]


def main() -> None:
    processes: list[subprocess.Popen] = []
    try:
        for name, script in APPS:
            if not script.exists():
                print(f"[skip] {name}: {script} does not exist yet")
                continue
            print(f"[start] {name}")
            process = subprocess.Popen([sys.executable, str(script)], cwd=str(ROOT))
            processes.append(process)
            time.sleep(0.8)
        print("[ready] portal http://127.0.0.1:8000/")
        while True:
            time.sleep(1)
            for process in list(processes):
                if process.poll() is not None:
                    raise RuntimeError(f"Child process exited early: PID={process.pid}")
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
        for process in processes:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
