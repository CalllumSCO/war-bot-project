"""
Start the companion API + Next.js web app locally.

In Cursor/VS Code: open this file and press F5, or Run ▶ on the `__main__` block.
Or from a terminal:  py scripts/start_companion.py
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
API_HOST = "127.0.0.1"
API_PORT = 8000
WEB_PORT = 3000
OPEN_BROWSER = os.getenv("COMPANION_OPEN_BROWSER", "1") not in ("0", "false", "False")


def _py() -> str:
    return sys.executable


def _npm() -> list[str]:
    # On Windows, prefer npm.cmd so CreateProcess doesn't need a shell.
    if os.name == "nt":
        return ["npm.cmd"]
    return ["npm"]


def main() -> int:
    os.chdir(ROOT)
    env = os.environ.copy()
    env.setdefault("NEXT_PUBLIC_API_BASE", f"http://localhost:{API_PORT}")

    api_cmd = [
        _py(),
        "-m",
        "uvicorn",
        "api.main:app",
        "--reload",
        "--host",
        API_HOST,
        "--port",
        str(API_PORT),
    ]
    web_cmd = [*_npm(), "run", "dev", "--", "-p", str(WEB_PORT)]

    print("▶ Companion API:", " ".join(api_cmd))
    print("▶ Companion web:", " ".join(web_cmd), f"(cwd={WEB_DIR})")
    print("  API  → http://localhost:8000")
    print("  Web  → http://localhost:3000")
    print("  Stop → Ctrl+C\n")

    creationflags = 0
    if os.name == "nt":
        # New process group so Ctrl+C can tear both down cleanly.
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    api = subprocess.Popen(api_cmd, cwd=ROOT, env=env, creationflags=creationflags)
    web = subprocess.Popen(web_cmd, cwd=WEB_DIR, env=env, creationflags=creationflags)
    procs = [api, web]

    if OPEN_BROWSER:
        time.sleep(2.5)
        webbrowser.open(f"http://localhost:{WEB_PORT}")

    def _shutdown(*_args: object) -> None:
        print("\n⏹ Stopping companion…")
        for proc in procs:
            if proc.poll() is not None:
                continue
            try:
                if os.name == "nt":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                else:
                    proc.send_signal(signal.SIGTERM)
            except Exception:
                proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    try:
        while True:
            for proc in procs:
                code = proc.poll()
                if code is not None:
                    print(f"Process exited with code {code}; shutting down the rest.")
                    _shutdown()
                    return code or 0
            time.sleep(0.4)
    except KeyboardInterrupt:
        _shutdown()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
