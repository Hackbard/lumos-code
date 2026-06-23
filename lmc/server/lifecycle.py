"""Server-Lifecycle: up/down/status fuer den lokalen CPG-Server."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

from .app import DEFAULT_HOST, DEFAULT_PORT

CACHE_DIR = Path(os.environ.get("LUMOS_CACHE", Path.home() / ".cache" / "lumos"))
PID_FILE = CACHE_DIR / "server.pid"
LOG_FILE = CACHE_DIR / "server.log"


def default_url() -> str:
    host = os.environ.get("LUMOS_HOST", DEFAULT_HOST)
    port = int(os.environ.get("LUMOS_PORT", DEFAULT_PORT))
    return f"http://{host}:{port}/mcp"


def is_running(url: str | None = None) -> bool:
    base = (url or default_url()).replace("/mcp", "/health")
    try:
        r = httpx.get(base, timeout=1.0)
        return r.status_code == 200 and r.json().get("ok") is True
    except Exception:
        return False


def start_server(url: str | None = None, foreground: bool = False) -> dict:
    if is_running(url):
        return {"success": True, "already_running": True, "url": default_url()}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if foreground:
        # Blockiert — nutzt python -m lmc.server direkt.
        raise SystemExit(0)
    log_fp = open(LOG_FILE, "ab", buffering=0)
    proc = subprocess.Popen(
        [sys.executable, "-m", "lmc.server"],
        stdout=log_fp, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))
    # Kurz warten bis Health-Endpoint antwortet.
    for _ in range(20):
        if is_running(url):
            return {"success": True, "pid": proc.pid, "url": default_url(), "log": str(LOG_FILE)}
        if proc.poll() is not None:
            return {"success": False, "error": f"Server starb sofort. Log: {LOG_FILE}"}
        time.sleep(0.25)
    return {"success": False, "error": f"Server startete, Health nicht erreicht. Log: {LOG_FILE}"}


def stop_server() -> dict:
    if not PID_FILE.exists():
        return {"success": False, "error": "Keine PID-Datei (Server laeuft nicht / wurde woanders gestartet)."}
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        try:
            PID_FILE.unlink()
        except FileNotFoundError:
            pass
    return {"success": True, "stopped_pid": pid if 'pid' in locals() else None}