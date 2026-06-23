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
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import store
from .graph import Index

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4243  # eigen: getrennt vom externen Codebadger-Server (4242)


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
    codebase_hash = args.get("codebase_hash")
    if not codebase_hash:
        import hashlib
        from pathlib import Path
        codebase_hash = hashlib.sha1(str(Path(source_path).resolve()).encode()).hexdigest()[:16]
    try:
        idx = store.generate(codebase_hash, source_path, language)
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


def re_error():
    import re
    return re.error


async def mcp(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}})
    tool_name = body.get("method") == "tools/call" and body.get("params", {}).get("name")
    arguments = body.get("params", {}).get("arguments", {}) or {}
    req_id = body.get("id", 1)
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