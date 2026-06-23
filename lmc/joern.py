"""Joern-Backend-Anbindung (Docker + REST).

Sorgt fuer echtes CPGQL: `lmc up` startet den Joern-REST-Server im Docker-
Container `lmc-joern` (Port 8085); CPGs liegen im Volume `lmc-cpgs` als
`<hash>.bin`. `lmc build` erzeugt sie per `joern-parse`, `lmc query` reicht
CPGQL an den REST-Server weiter.

REST-Protokoll (Joern v4):
  POST /query   {"query": "..."} -> {"success": true, "uuid": "..."}
  GET  /result/<uuid>            -> {"success": true, "stdout": "..."} | {"success": false, "err": "..."}
"""
from __future__ import annotations

import re
import subprocess
import time
from typing import Optional

import httpx

JOERN_HOST = "127.0.0.1"
JOERN_PORT = 8085
IMAGE = "lmc-joern:latest"
CONTAINER = "lmc-joern"
VOLUME = "lmc-cpgs"
CPG_DIR_IN_CONTAINER = "/cpgs"

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _extract_result(stdout: str) -> str:
    """Extrahiert den Wert der letzten `val resN: ... = <wert>` Bindung.

    Der Wert kann mehrzeilig sein (Joern zeigt Strings als triple-quotes),
    daher nehmen wir ab dem letzten `val res` den Rest ab ` = ` bis Ende.
    """
    idx = stdout.rfind("val res")
    if idx == -1:
        return ""
    eq = stdout.find(" = ", idx)
    if eq == -1:
        return ""
    val = stdout[eq + 3:].strip()
    if val.startswith('"""') and val.endswith('"""') and len(val) >= 6:
        val = val[3:-3]
    elif val.startswith('"') and val.endswith('"') and len(val) >= 2:
        val = val[1:-1]
    return val.strip()


def default_url() -> str:
    import os
    host = os.environ.get("LUMOS_JOERN_HOST", JOERN_HOST)
    port = int(os.environ.get("LUMOS_JOERN_PORT", JOERN_PORT))
    return f"http://{host}:{port}"


class JoernClient:
    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        self.base_url = base_url or default_url()
        self.client = httpx.Client(timeout=timeout)

    def is_up(self) -> bool:
        try:
            r = self.client.get(self.base_url, timeout=1.5)
            return r.status_code in (200, 404, 405)  # Server antwortet => up
        except Exception:
            return False

    def _submit(self, query: str) -> Optional[str]:
        try:
            r = self.client.post(f"{self.base_url}/query", json={"query": query}, timeout=30.0)
            data = r.json()
            return data.get("uuid") if data.get("success") else None
        except Exception:
            return None

    def _poll(self, uuid: str, timeout: float = 120.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = self.client.get(f"{self.base_url}/result/{uuid}", timeout=10.0)
                data = r.json()
                if data.get("success"):
                    return {"success": True, "stdout": _ANSI.sub("", data.get("stdout", ""))}
                if data.get("err") and "No result" not in str(data.get("err")):
                    return {"success": False, "error": data.get("err")}
            except Exception:
                pass
            time.sleep(0.5)
        return {"success": False, "error": "Timeout beim Warten auf Joern-Ergebnis"}

    def run(self, query: str, timeout: float = 120.0) -> dict:
        """Fuehrt CPGQL aus und liefert {success, stdout, result} bzw. {success, error}.

        `result` ist der extrahierte Wert der letzten `val resN: ... = <wert>` Zeile
        (sofern vorhanden); `stdout` ist der rohe, ANSI-bereinigte REPL-Output."""
        uuid = self._submit(query)
        if not uuid:
            return {"success": False, "error": "Joern-Server nicht erreichbar. Erst 'lmc up' ausfuehren."}
        res = self._poll(uuid, timeout=timeout)
        if not res.get("success"):
            return res
        stdout = res["stdout"].strip()
        return {"success": True, "stdout": stdout, "result": _extract_result(stdout), "engine": "joern"}


def cpg_path_in_container(codebase_hash: str) -> str:
    return f"{CPG_DIR_IN_CONTAINER}/{codebase_hash}.bin"


def joern_parse(worktree: str, codebase_hash: str) -> dict:
    """Baut <hash>.bin im Volume aus dem Worktree via `joern-parse` im Container."""
    out = cpg_path_in_container(codebase_hash)
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{worktree}:/code:ro",
        "-v", f"{VOLUME}:{CPG_DIR_IN_CONTAINER}",
        IMAGE, "joern-parse", "/code", "-o", out,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        return {"success": False, "error": "Docker nicht installiert/verfuegbar."}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "joern-parse Timeout (600s)."}
    if r.returncode != 0:
        return {"success": False, "error": f"joern-parse exit {r.returncode}: {r.stderr.strip()[-400:]}"}
    return {"success": True, "cpg_path": out, "log": r.stdout.strip()[-200:]}


def run_cpgql(codebase_hash: str, cpgql: str, url: str | None = None, timeout: float = 120.0) -> dict:
    """Laedt den CPG und fuehrt rohes CPGQL aus; liefert cleaned stdout."""
    cpg = cpg_path_in_container(codebase_hash)
    full = f'importCpg("{cpg}")\n{cpgql}'
    return JoernClient(url).run(full, timeout=timeout)


if __name__ == "__main__":
    # ponytail: self-check braucht laufenden `lmc up` + gebauten CPG; nur Smoke-Test.
    jc = JoernClient()
    print("joern up:", jc.is_up())