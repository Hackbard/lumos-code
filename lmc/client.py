"""Schlanker HTTP-Client fuer den Lumos CPG-Server (JSON-RPC tools/call)."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx

from .server.app import DEFAULT_HOST, DEFAULT_PORT


def default_url() -> str:
    import os
    host = os.environ.get("LUMOS_HOST", DEFAULT_HOST)
    port = int(os.environ.get("LUMOS_PORT", DEFAULT_PORT))
    return f"http://{host}:{port}/mcp"


class CodebadgerClient:
    def __init__(self, base_url: str | None = None, timeout: float = 120.0):
        self.base_url = base_url or default_url()
        self.client = httpx.Client(timeout=timeout)

    def _call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        try:
            r = self.client.post(self.base_url, json=payload)
            r.raise_for_status()
            content = r.json().get("result", {}).get("content", [])
            if content and content[0].get("type") == "text":
                return json.loads(content[0].get("text", "{}"))
            return {"success": False, "error": "Unerwartetes MCP-Antwortformat"}
        except httpx.ConnectError:
            return {"success": False, "error": "CPG-Server nicht erreichbar. Erst 'lmc up' ausfuehren."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Kern-Methoden ---

    def generate_cpg(self, source_path: str, language: str, codebase_hash: Optional[str] = None) -> Dict[str, Any]:
        args = {"source_path": source_path, "language": language}
        if codebase_hash:
            args["codebase_hash"] = codebase_hash
        return self._call("generate_cpg", args)

    def get_cpg_status(self, codebase_hash: str) -> Dict[str, Any]:
        return self._call("get_cpg_status", {"codebase_hash": codebase_hash})

    def find_methods(self, codebase_hash: str, pattern: str) -> Dict[str, Any]:
        return self._call("find_methods", {"codebase_hash": codebase_hash, "pattern": pattern})

    def get_call_graph(self, codebase_hash: str, method: str, direction: str, depth: int) -> Dict[str, Any]:
        return self._call("get_call_graph", {"codebase_hash": codebase_hash, "method_name": method,
                                             "direction": direction, "depth": depth})

    def get_source(self, codebase_hash: str, method: str) -> Dict[str, Any]:
        return self._call("get_source", {"codebase_hash": codebase_hash, "method_name": method})

    def get_context(self, codebase_hash: str, symbol: str) -> Dict[str, Any]:
        return self._call("get_context", {"codebase_hash": codebase_hash, "symbol": symbol})

    def run_query(self, codebase_hash: str, query: str) -> Dict[str, Any]:
        return self._call("run_cpgql_query", {"codebase_hash": codebase_hash, "query": query})