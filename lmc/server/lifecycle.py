"""Server-Lifecycle: up/down fuer Joern-Backend (Docker) + Lumos-Gateway.

`lmc up`:
  1. ensured das eigene Image `lmc-joern:latest` (baut es einmalig aus docker/).
  2. ensured das Volume `lmc-cpgs`.
  3. startet den persistenten Joern-REST-Server im Container `lmc-joern` (Port 8085).
  4. startet den Lumos-Gateway (tree-sitter nav) auf Port 4243.
`lmc down` stoppt beides (Volume + CPGs bleiben erhalten).
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

from .app import DEFAULT_HOST, DEFAULT_PORT
from ..joern import IMAGE, CONTAINER, VOLUME, CPG_DIR_IN_CONTAINER, JOERN_PORT, JoernClient

CACHE_DIR = Path(os.environ.get("LUMOS_CACHE", Path.home() / ".cache" / "lumos"))
PID_FILE = CACHE_DIR / "server.pid"
LOG_FILE = CACHE_DIR / "server.log"
DOCKER_DIR = Path(__file__).resolve().parents[2] / "docker"


def gateway_url() -> str:
    host = os.environ.get("LUMOS_HOST", DEFAULT_HOST)
    port = int(os.environ.get("LUMOS_PORT", DEFAULT_PORT))
    return f"http://{host}:{port}/mcp"


def gateway_running() -> bool:
    try:
        r = httpx.get(gateway_url().replace("/mcp", "/health"), timeout=1.0)
        return r.status_code == 200 and r.json().get("ok") is True
    except Exception:
        return False


def _run(cmd: list, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def ensure_image() -> dict:
    r = _run(["docker", "image", "inspect", IMAGE], timeout=10.0)
    if r.returncode == 0:
        return {"success": True, "image": IMAGE, "already_present": True}
    if not DOCKER_DIR.joinpath("Dockerfile").exists():
        return {"success": False, "error": f"Kein Dockerfile in {DOCKER_DIR}"}
    r = _run(["docker", "build", "-t", IMAGE, str(DOCKER_DIR)], timeout=900.0)
    if r.returncode != 0:
        return {"success": False, "error": f"docker build fehlgeschlagen: {r.stderr[-600:]}"}
    return {"success": True, "image": IMAGE, "built": True}


def ensure_volume() -> dict:
    _run(["docker", "volume", "create", VOLUME], timeout=15.0)
    return {"success": True, "volume": VOLUME}


def start_joern() -> dict:
    img = ensure_image()
    if not img.get("success"):
        return img
    ensure_volume()
    _run(["docker", "rm", "-f", CONTAINER], timeout=15.0)
    host_port = os.environ.get("LUMOS_JOERN_PORT", str(JOERN_PORT))
    cmd = ["docker", "run", "-d", "--name", CONTAINER,
           "-p", f"{host_port}:{JOERN_PORT}",
           "-v", f"{VOLUME}:{CPG_DIR_IN_CONTAINER}",
           "--restart", "unless-stopped", IMAGE]
    r = _run(cmd, timeout=30.0)
    if r.returncode != 0:
        return {"success": False, "error": f"joern container start fehlgeschlagen: {r.stderr[-400:]}"}
    # Auf REST-Server warten (JVM-Startup ~30-60s).
    jc = JoernClient()
    for _ in range(60):
        if jc.is_up():
            # Warmup-Query konsumiert das REPL-Banner, damit Nutzer-Queries sauber sind.
            try:
                jc.run("1", timeout=60.0)
            except Exception:
                pass
            return {"success": True, "container": CONTAINER, "url": jc.base_url, "port": host_port}
        time.sleep(1.0)
    return {"success": False, "error": f"Joern-REST nicht erreichbar. Logs: docker logs {CONTAINER}"}


def stop_joern() -> dict:
    r = _run(["docker", "rm", "-f", CONTAINER], timeout=15.0)
    if r.returncode != 0:
        return {"success": False, "error": r.stderr.strip() or "Container nicht vorhanden"}
    return {"success": True, "container": CONTAINER}


def start_gateway() -> dict:
    if gateway_running():
        return {"success": True, "already_running": True, "url": gateway_url()}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log_fp = open(LOG_FILE, "ab", buffering=0)
    proc = subprocess.Popen(
        [sys.executable, "-m", "lmc.server"],
        stdout=log_fp, stderr=subprocess.STDOUT, start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))
    for _ in range(20):
        if gateway_running():
            return {"success": True, "pid": proc.pid, "url": gateway_url(), "log": str(LOG_FILE)}
        if proc.poll() is not None:
            return {"success": False, "error": f"Gateway starb sofort. Log: {LOG_FILE}"}
        time.sleep(0.25)
    return {"success": False, "error": f"Gateway Health nicht erreicht. Log: {LOG_FILE}"}


def stop_gateway() -> dict:
    if not PID_FILE.exists():
        return {"success": False, "error": "Keine Gateway-PID-Datei."}
    pid = None
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
    return {"success": True, "stopped_pid": pid}


# Kompatibilitaet mit alter API
def is_running(url: str | None = None) -> bool:
    return gateway_running()


def start_server(url: str | None = None) -> dict:
    joern = start_joern()
    gw = start_gateway()
    return {"success": joern.get("success") and gw.get("success"),
            "joern": joern, "gateway": gw}


def stop_server() -> dict:
    gw = stop_gateway()
    joern = stop_joern()
    return {"success": True, "gateway": gw, "joern": joern}