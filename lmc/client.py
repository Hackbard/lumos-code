import json
import httpx
from typing import Any, Dict, Optional

class CodebadgerClient:
    """
    Ein komplett neu geschriebener, schlanker Client für die Kommunikation 
    mit dem lokalen Codebadger MCP-Server. Keine Altlasten.
    """
    def __init__(self, base_url: str = "http://localhost:4242/mcp"):
        self.base_url = base_url
        self.client = httpx.Client(timeout=120.0) # Lange Timeouts für Joern-Builds

    def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Nativer HTTP-Aufruf an den MCP Server. 
        Ersetzt die alte Gibson cpg.py Logik.
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        try:
            response = self.client.post(self.base_url, json=payload)
            response.raise_for_status()
            result = response.json().get("result", {})
            
            # MCP gibt Content als Liste von Text/JSON Blöcken zurück
            content = result.get("content", [])
            if content and content[0].get("type") == "text":
                text_data = content[0].get("text", "{}")
                return json.loads(text_data)
            return {"success": False, "error": "Unerwartetes MCP Antwortformat"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Die Kern-Methoden für Lumos Code ---

    def generate_cpg(self, source_path: str, language: str) -> Dict[str, Any]:
        """Baut den CPG für einen spezifischen Pfad."""
        return self._call_mcp_tool("generate_cpg", {
            "source_type": "local",
            "source_path": source_path,
            "language": language,
            "force": True
        })

    def get_status(self, codebase_hash: str) -> Dict[str, Any]:
        """Fragt den Status eines CPGs ab."""
        return self._call_mcp_tool("get_cpg_status", {
            "codebase_hash": codebase_hash
        })

    def run_query(self, codebase_hash: str, query: str) -> Dict[str, Any]:
        """Führt eine rohe CPGQL Abfrage aus."""
        return self._call_mcp_tool("run_cpgql_query", {
            "codebase_hash": codebase_hash,
            "query": query
        })
        
    def get_call_graph(self, codebase_hash: str, method_name: str, direction: str, depth: int) -> Dict[str, Any]:
        """Holt den Call-Graph (für Impact und Caller/Callee)."""
        return self._call_mcp_tool("get_call_graph", {
            "codebase_hash": codebase_hash,
            "method_name": method_name,
            "direction": direction,
            "depth": depth
        })