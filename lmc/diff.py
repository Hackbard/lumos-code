"""check-diff / precommit als wiederverwendbare Funktion.

Liest das uncommittete `git diff` eines Worktrees, mappt die geaenderten Dateien
auf den CPG (tree-sitter) und liefert die betroffenen Methoden + Status.
Genutzt vom CLI-Befehl `lmc check-diff` / `lmc precommit`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from .client import CodebadgerClient


def changed_files(root: Path) -> list:
    """Liefert uncommittete, geaenderte Dateien (relativ zu root)."""
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "--relative"],
            cwd=root, capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"git diff fehlgeschlagen: {e.stderr or e}")
    except Exception as e:
        raise RuntimeError(f"git diff fehlgeschlagen: {e}")
    return [l for l in out.stdout.splitlines() if l]


def check_diff(path: str, codebase_hash: Optional[str] = None,
               url: Optional[str] = None) -> dict:
    """Mappt uncommittetes git diff auf den CPG und liefert Warnungen.

    Returns: {changed_files, cpg_built, warnings, status}
      status: 'safe' (keine Aenderungen) | 'clean' (Aenderungen, keine CPG-Treffer)
              | 'review' (betroffene CPG-Methoden in geaenderten Dateien)
    """
    root = Path(path).resolve()
    try:
        changed = changed_files(root)
    except RuntimeError as e:
        return {"success": False, "error": str(e)}

    cbh = codebase_hash or _hash_from_path(root)
    client = CodebadgerClient(url)
    st = client.get_cpg_status(cbh)
    cpg_built = bool((st.get("data") or {}).get("exists"))

    warnings: list = []
    # ponytail: Mapping pro Diff-Hunk (welche Methode in welcher Zeile geaendert)
    # braeuchte Joern-Level Differenzierung; wir listen die CPG-Methoden in den
    # geaenderten Dateien (primaere Blast-Radius-Kandidaten).
    if cpg_built and changed:
        find_all = client.find_methods(cbh, ".*")
        for m in (find_all.get("data") or {}).get("methods", []):
            if any(m["file"].endswith(c) for c in changed):
                warnings.append({"file": m["file"], "method": m["signature"], "line": m["line"]})

    if not changed:
        status = "safe"
    elif warnings:
        status = "review"
    else:
        status = "clean"

    return {"success": True, "changed_files": changed, "cpg_built": cpg_built,
            "warnings": warnings, "status": status}


def _hash_from_path(root: Path) -> str:
    import hashlib
    return hashlib.sha1(str(root.resolve()).encode()).hexdigest()[:16]


if __name__ == "__main__":
    # ponytail: smoke — braucht git + gebauten CPG; nur Signature pruefen.
    import inspect
    assert "check_diff" in globals() and callable(check_diff)
    print("diff.py self-check OK")