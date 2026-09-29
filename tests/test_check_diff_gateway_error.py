"""Regression: check_diff darf Gateway-Ausfall nicht als cpg_built=false verschlucken.

Vor dem Fix: get_cpg_status lieferte {"success": False, "error": ...}, check_diff
ignorierte das und meldete success=True/status=safe — der Aufrufer (MCP-Tool
check_architecture_drift) sah ein PASSED, obwohl gar nichts gecheckt wurde.
"""
from __future__ import annotations

from lmc import diff


def test_check_diff_propagates_gateway_unreachable(monkeypatch, tmp_path):
    class _FakeClient:
        def __init__(self, url=None):
            pass

        def get_cpg_status(self, cbh):
            return {"success": False, "error": "CPG-Server nicht erreichbar. Erst 'lmc up' ausfuehren."}

    monkeypatch.setattr(diff, "CodebadgerClient", _FakeClient)
    monkeypatch.setattr(diff, "changed_files", lambda root: ["app/Foo.php"])

    result = diff.check_diff(str(tmp_path))

    assert result["success"] is False
    assert "nicht erreichbar" in result["error"]


def test_check_diff_still_safe_with_reachable_gateway(monkeypatch, tmp_path):
    class _FakeClient:
        def __init__(self, url=None):
            pass

        def get_cpg_status(self, cbh):
            return {"success": True, "data": {"exists": False}}

        def find_methods(self, cbh, pattern):
            return {"success": True, "data": {"methods": []}}

    monkeypatch.setattr(diff, "CodebadgerClient", _FakeClient)
    monkeypatch.setattr(diff, "changed_files", lambda root: [])

    result = diff.check_diff(str(tmp_path))

    assert result["success"] is True
    assert result["status"] == "safe"
    assert result["cpg_built"] is False
