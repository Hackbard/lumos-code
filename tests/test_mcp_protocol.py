"""Regression-Test: der Gateway muss MCP-Lifecycle-Methoden sprechen, nicht nur `tools/call`.

Bug 2026-09-21: ``mcp()`` wertete ausschliesslich ``tools/call`` aus. Jede andere
Methode (allen voran ``initialize``, mit dem sich jeder MCP-Client zuerst
meldet) landete im "Unbekanntes Tool"-Zweig der ``tools/call``-Handler-Logik.
Weil ``body.get("method") == "tools/call"`` fuer ``initialize`` zu ``False``
auswertet, stand im Fehlertext sogar woertlich "Unbekanntes Tool: False" — kein
MCP-Client konnte sich je verbinden.

Fix: ``initialize``, ``notifications/initialized`` und ``tools/list`` werden
jetzt echt bedient; eine unbekannte Methode bekommt einen JSON-RPC-Fehler
-32601 ("Method not found") statt eines erfundenen Tool-Fehlers.
``tools/call`` bleibt unveraendert (bestehendes Verhalten, von
``CodebadgerClient`` in ``lmc/client.py`` genutzt).
"""
import os
import sys

# Repo-Root zum Pfad hinzufuegen (laeuft ohne Install).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from starlette.testclient import TestClient  # noqa: E402

from lmc.server.app import PREFERRED_PROTOCOL_VERSION, SERVER_NAME, TOOLS, app  # noqa: E402

_client = TestClient(app)


def _rpc(method: str, params: dict | None = None, id_: int | None = 1) -> dict:
    body = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        body["params"] = params
    if id_ is not None:
        body["id"] = id_
    r = _client.post("/mcp", json=body)
    return r


def test_initialize_mirrors_supported_protocol_version():
    """Fordert der Client eine Version an, die wir kennen, spiegeln wir sie."""
    r = _rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    result = body["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == SERVER_NAME
    assert result["serverInfo"]["version"], "Version darf nicht leer sein"
    assert "error" not in body


def test_initialize_falls_back_for_unknown_protocol_version():
    """Unbekannte Version -> wir antworten mit unserer eigenen, kein Fehler."""
    r = _rpc("initialize", {"protocolVersion": "1999-01-01", "capabilities": {}})
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["protocolVersion"] == PREFERRED_PROTOCOL_VERSION


def test_notifications_initialized_gets_no_result_body():
    """Eine Notification (keine 'id') bekommt nie eine JSON-RPC-Antwort mit Ergebnis."""
    r = _rpc("notifications/initialized", {}, id_=None)
    assert r.status_code == 202
    assert r.content == b"", f"Notification darf keinen Body zurueckgeben, bekam: {r.content!r}"


def test_tools_list_returns_all_seven_with_input_schema():
    r = _rpc("tools/list")
    assert r.status_code == 200
    body = r.json()
    tools = body["result"]["tools"]
    assert [t["name"] for t in tools] == list(TOOLS), "Reihenfolge/Vollstaendigkeit muss TOOLS spiegeln"
    assert tools[0]["name"] == "generate_cpg"
    for t in tools:
        assert t["description"], f"{t['name']} hat keine description"
        schema = t["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        for req in schema.get("required", []):
            assert req in schema["properties"], f"{t['name']}: required '{req}' fehlt in properties"


def test_unknown_method_is_a_real_jsonrpc_error_not_a_fake_tool_error():
    """Der eigentliche Bug: fruemher landete jede unbekannte Methode im
    tools/call-Zweig und bekam einen erfundenen 'Unbekanntes Tool: False'-Text."""
    r = _rpc("does/not/exist", {})
    assert r.status_code == 200
    body = r.json()
    assert "result" not in body
    assert body["error"]["code"] == -32601
    assert "False" not in body["error"]["message"]


def test_tools_call_behaviour_is_unchanged():
    """tools/call bleibt wie vorher: MCP-Content-Block mit dem Tool-JSON als Text."""
    r = _rpc("tools/call", {"name": "get_cpg_status", "arguments": {"codebase_hash": "does-not-exist"}})
    assert r.status_code == 200
    body = r.json()
    content = body["result"]["content"]
    assert content[0]["type"] == "text"
    import json as _json
    payload = _json.loads(content[0]["text"])
    assert payload == {"success": True, "data": {"exists": False}}


def test_tools_call_unknown_tool_error_text_is_unchanged():
    r = _rpc("tools/call", {"name": "nope", "arguments": {}})
    body = r.json()
    import json as _json
    payload = _json.loads(body["result"]["content"][0]["text"])
    assert payload["success"] is False
    assert "Unbekanntes Tool: nope" in payload["error"]


if __name__ == "__main__":
    for fn in (
        test_initialize_mirrors_supported_protocol_version,
        test_initialize_falls_back_for_unknown_protocol_version,
        test_notifications_initialized_gets_no_result_body,
        test_tools_list_returns_all_seven_with_input_schema,
        test_unknown_method_is_a_real_jsonrpc_error_not_a_fake_tool_error,
        test_tools_call_behaviour_is_unchanged,
        test_tools_call_unknown_tool_error_text_is_unchanged,
    ):
        fn()
        print(f"ok: {fn.__name__}")
    print("all mcp protocol tests passed")
