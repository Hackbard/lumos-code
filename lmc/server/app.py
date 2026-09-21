"""Codebadger-kompatibler JSON-RPC HTTP-Server (selbst bereitgestellt).

Laeuft auf http://localhost:4242/mcp und spricht das JSON-RPC `tools/call`
Protokoll, das der Lumos-Client erwartet. Antworten werden als
MCP-Content-Bloecke (`[{"type":"text","text": <json>}]`) zurueckgegeben.

Start: `python -m lmc.server` oder via CLI `lmc up`.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from . import store
from .graph import Index

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4243  # eigen: getrennt vom externen Codebadger-Server (4242)

# --- MCP-Protokoll (Lifecycle: initialize / notifications/initialized / tools/list) ---
#
# Feldnamen und Formen (protocolVersion, capabilities, serverInfo, tools[].inputSchema,
# JSON-RPC-Fehlercode -32601) stammen aus der MCP-Spezifikation
# https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle und
# .../server/tools (per Context7 abgerufen), Versionsverhandlung zusaetzlich
# gegenspiegelt mit .../specification/2025-11-25/basic/lifecycle. Der Server
# selbst implementiert die 2025-06-18-Form; bekannte protocolVersion-Werte des
# Clients werden gespiegelt, sonst antworten wir mit unserer eigenen Version.
SERVER_NAME = "lumos-code"  # == [project].name in pyproject.toml
PREFERRED_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = (
    "2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25",
)


def _server_version() -> str:
    """Version aus den Paket-Metadaten (== [project].version in pyproject.toml).

    `uv sync`/`uv build` installieren das Paket lokal (editable bzw. Wheel);
    `importlib.metadata` liest die Version dann direkt von dort, statt sie im
    Code zu duplizieren. Fallback (Dev-Checkout ohne Install): pyproject.toml
    selbst parsen.
    """
    try:
        from importlib.metadata import version as _pkg_version
        return _pkg_version("lumos-code")
    except Exception:
        pass
    try:
        import re
        from pathlib import Path
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject.read_text())
        if m:
            return m.group(1)
    except Exception:
        pass
    return "0.0.0"


def _ok(data: dict) -> str:
    return json.dumps({"success": True, "data": data}, ensure_ascii=False)


def _err(msg: str, **extra) -> str:
    payload = {"success": False, "error": str(msg)}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def _need_index(codebase_hash: str):
    idx = store.get(codebase_hash)
    if idx is None:
        return None, _err(f"Kein CPG fuer Hash {codebase_hash}. Erst 'lmc build' ausfuehren.")
    return idx, None


# --- Tool-Implementierungen ---

def tool_generate_cpg(args: dict) -> str:
    source_path = args.get("source_path") or args.get("path")
    language = args.get("language")
    if not source_path or not language:
        return _err("source_path und language erforderlich")
    include_gitignored = args.get("include_gitignored_files", False)
    codebase_hash = args.get("codebase_hash")
    if not codebase_hash:
        import hashlib
        from pathlib import Path
        codebase_hash = hashlib.sha1(str(Path(source_path).resolve()).encode()).hexdigest()[:16]
    try:
        idx = store.generate(codebase_hash, source_path, language,
                             include_gitignored_files=include_gitignored)
    except Exception as e:
        return _err(str(e))
    return _ok({
        "codebase_hash": codebase_hash, "language": language,
        "methods": len(idx.methods), "edges": len(idx.edges), "files": len(idx.files),
    })


def tool_get_cpg_status(args: dict) -> str:
    st = store.status(args.get("codebase_hash", ""))
    return _ok(st)


def _method_dicts(methods) -> list:
    return [{"signature": m.signature, "name": m.name, "class": m.cls,
             "file": m.file, "line": m.line} for m in methods]


def tool_find_methods(args: dict) -> str:
    idx, err = _need_index(args.get("codebase_hash", ""))
    if err:
        return err
    pattern = args.get("pattern") or args.get("name") or ""
    try:
        hits = idx.find(pattern) if pattern else idx.methods
    except re_error() as e:
        return _err(f"Ungueltiges Regex-Pattern: {e}")
    return _ok({"methods": _method_dicts(hits), "count": len(hits)})


def tool_get_call_graph(args: dict) -> str:
    idx, err = _need_index(args.get("codebase_hash", ""))
    if err:
        return err
    method = args.get("method_name") or args.get("method") or ""
    direction = args.get("direction", "incoming")
    depth = int(args.get("depth", 1))
    if direction == "incoming":
        affected = idx.impact(method, depth)
        return _ok({"direction": "incoming", "method": method, "depth": depth,
                    "affected": affected})
    # outgoing: BFS ueber callees
    affected: Dict[int, list] = {}
    current = idx.resolve(method)
    visited = {id(m) for m in current}
    for d in range(1, depth + 1):
        nxt = []
        for m in current:
            for callee in idx.callees(m.signature):
                if id(callee) not in visited:
                    visited.add(id(callee))
                    nxt.append(callee)
        if not nxt:
            break
        affected[d] = sorted({c.signature for c in nxt})
        current = nxt
    return _ok({"direction": "outgoing", "method": method, "depth": depth,
                "affected": affected})


def tool_get_source(args: dict) -> str:
    idx, err = _need_index(args.get("codebase_hash", ""))
    if err:
        return err
    method = args.get("method_name") or args.get("method") or args.get("symbol") or ""
    src = idx.source(method)
    if src is None:
        return _err(f"Methode nicht gefunden: {method}")
    return _ok(src)


def tool_get_context(args: dict) -> str:
    idx, err = _need_index(args.get("codebase_hash", ""))
    if err:
        return err
    symbol = args.get("symbol") or args.get("method_name") or ""
    src = idx.source(symbol)
    callers = _method_dicts(idx.callers(symbol))
    callees = _method_dicts(idx.callees(symbol))
    return _ok({"symbol": symbol, "source": src, "callers": callers, "callees": callees})


def tool_run_cpgql_query(args: dict) -> str:
    # Reicht CPGQL an das Joern-Backend weiter (echte Ausfuehrung, kein Mock).
    from ..joern import run_cpgql
    result = run_cpgql(args.get("codebase_hash", ""), args.get("query", ""))
    if result.get("success"):
        return _ok({"stdout": result.get("stdout", ""), "engine": "joern"})
    return _err(result.get("error", "Joern-Fehler"))


TOOLS: Dict[str, Callable[[dict], str]] = {
    "generate_cpg": tool_generate_cpg,
    "get_cpg_status": tool_get_cpg_status,
    "find_methods": tool_find_methods,
    "get_call_graph": tool_get_call_graph,
    "get_source": tool_get_source,
    "get_context": tool_get_context,
    "run_cpgql_query": tool_run_cpgql_query,
}

# inputSchema pro Tool, abgeleitet aus den Handler-Implementierungen oben (welche
# Keys liest jeder Handler aus `arguments`, welche fehlen duerfen ohne Fehler zu
# werfen). `required` listet nur Keys, ohne die der Handler tatsaechlich einen
# Fehler zurueckgibt oder die Antwort sinnlos wird; Alias-Keys (z.B. `method`
# statt `method_name`), die die Handler zusaetzlich akzeptieren, stehen nur in
# der Beschreibung, nicht in `required` — falsch als Pflicht markiert waere
# schlimmer als eine unvollstaendige Beschreibung.
TOOL_SCHEMAS: Dict[str, dict] = {
    "generate_cpg": {
        "type": "object",
        "properties": {
            "source_path": {"type": "string", "description": "Pfad zum Quellverzeichnis (Legacy-Alias: path)"},
            "language": {"type": "string", "description": "Sprache, z.B. php, javascript, typescript, python, java, go, ruby, csharp, swift, kotlin, c, cpp"},
            "codebase_hash": {"type": "string", "description": "CPG-Hash; ohne Angabe wird sha1(abs(source_path))[:16] verwendet"},
            "include_gitignored_files": {"type": "boolean", "default": False, "description": "Auch von .gitignore ausgeschlossene Dateien indexieren"},
        },
        "required": ["source_path", "language"],
    },
    "get_cpg_status": {
        "type": "object",
        "properties": {
            "codebase_hash": {"type": "string", "description": "CPG-Hash aus lumos.yml (codebase_hash)"},
        },
        "required": ["codebase_hash"],
    },
    "find_methods": {
        "type": "object",
        "properties": {
            "codebase_hash": {"type": "string", "description": "CPG-Hash aus lumos.yml"},
            "pattern": {"type": "string", "description": "Regex ueber Methoden-/Klassennamen; leer = alle Methoden des CPG (Legacy-Alias: name)"},
        },
        "required": ["codebase_hash"],
    },
    "get_call_graph": {
        "type": "object",
        "properties": {
            "codebase_hash": {"type": "string", "description": "CPG-Hash aus lumos.yml"},
            "method_name": {"type": "string", "description": "Klasse.Methode oder Methodenname (Legacy-Alias: method)"},
            "direction": {"type": "string", "enum": ["incoming", "outgoing"], "default": "incoming", "description": "incoming = Aufrufer (Impact/Blast-Radius), outgoing = Aufgerufenes"},
            "depth": {"type": "integer", "minimum": 1, "default": 1, "description": "Rekursionstiefe"},
        },
        "required": ["codebase_hash", "method_name"],
    },
    "get_source": {
        "type": "object",
        "properties": {
            "codebase_hash": {"type": "string", "description": "CPG-Hash aus lumos.yml"},
            "method_name": {"type": "string", "description": "Klasse.Methode oder Methodenname (Legacy-Aliase: method, symbol)"},
        },
        "required": ["codebase_hash", "method_name"],
    },
    "get_context": {
        "type": "object",
        "properties": {
            "codebase_hash": {"type": "string", "description": "CPG-Hash aus lumos.yml"},
            "symbol": {"type": "string", "description": "Klasse.Methode oder Methodenname; liefert Source + Caller + Callee gebuendelt (Legacy-Alias: method_name)"},
        },
        "required": ["codebase_hash", "symbol"],
    },
    "run_cpgql_query": {
        "type": "object",
        "properties": {
            "codebase_hash": {"type": "string", "description": "CPG-Hash aus lumos.yml; der zugehoerige CPG muss im Joern-Backend gebaut sein"},
            "query": {"type": "string", "description": "Rohe CPGQL-Query, ausgefuehrt gegen den Joern-REST-Server (echtes Data-Flow/Taint moeglich)"},
        },
        "required": ["codebase_hash", "query"],
    },
}

TOOL_DESCRIPTIONS: Dict[str, str] = {
    "generate_cpg": "Baut den tree-sitter-CPG-Index fuer ein Quellverzeichnis (Aequivalent zu `lmc build`).",
    "get_cpg_status": "Liefert Status/Groesse (Methoden, Kanten, Dateien) eines bereits gebauten CPG.",
    "find_methods": "Findet Klassen/Methoden per Regex im CPG.",
    "get_call_graph": "Blast-Radius/Aufrufgraph einer Methode (Aufrufer oder Aufgerufenes), rekursiv bis `depth`.",
    "get_source": "Quelltext einer Methode inklusive Datei:Zeile.",
    "get_context": "Buendelt Source + direkte Aufrufer + direkte Aufgerufene fuer eine Methode.",
    "run_cpgql_query": "Fuehrt eine rohe Joern-CPGQL-Query gegen den gebauten CPG aus (Data-Flow/Taint, Escape-Hatch).",
}


def re_error():
    import re
    return re.error


def _handle_initialize(params: dict, req_id) -> JSONResponse:
    requested = params.get("protocolVersion")
    protocol_version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PREFERRED_PROTOCOL_VERSION
    return JSONResponse({
        "jsonrpc": "2.0", "id": req_id,
        "result": {
            "protocolVersion": protocol_version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": _server_version()},
        },
    })


def _handle_tools_list(req_id) -> JSONResponse:
    tools = [
        {
            "name": name,
            "description": TOOL_DESCRIPTIONS.get(name, ""),
            "inputSchema": TOOL_SCHEMAS[name],
        }
        for name in TOOLS
    ]
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}})


def _handle_tools_call(params: dict, req_id) -> JSONResponse:
    tool_name = params.get("name")
    arguments = params.get("arguments") or {}
    handler = TOOLS.get(tool_name)
    if handler is None:
        text = _err(f"Unbekanntes Tool: {tool_name}. Verfuegbar: {list(TOOLS)}")
    else:
        try:
            text = handler(arguments)
        except Exception as e:
            text = _err(f"Server-Fehler in {tool_name}: {e}")
    return JSONResponse({
        "jsonrpc": "2.0", "id": req_id,
        "result": {"content": [{"type": "text", "text": text}]},
    })


async def mcp(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
                            status_code=400)

    method = body.get("method")
    params = body.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    # JSON-RPC 2.0: eine Notification hat KEIN "id"-Feld und bekommt NIE eine
    # Antwort mit Ergebnis (nicht einmal einen Fehler) — nur eine Transport-
    # Quittung. `notifications/initialized` ist die einzige, die der Client
    # heute schickt; unbekannte Notifications werden ebenso still quittiert.
    if "id" not in body:
        return Response(status_code=202)

    req_id = body.get("id")
    if method == "initialize":
        return _handle_initialize(params, req_id)
    if method == "tools/list":
        return _handle_tools_list(req_id)
    if method == "tools/call":
        return _handle_tools_call(params, req_id)
    return JSONResponse({
        "jsonrpc": "2.0", "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    })


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "tools": list(TOOLS), "indexes": store.list_hashes()})


def create_app() -> Starlette:
    routes = [
        Route("/mcp", mcp, methods=["POST"]),
        Route("/", health, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
    ]
    return Starlette(routes=routes)


app = create_app()