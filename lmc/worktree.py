"""Persistenter Worktree-State (Registry ~/.cache/lumos/worktrees.json).

Haelt fest, fuer welche Codebase-Hashes schon ein CPG gebaut wurde (tree-sitter
+ Joern), damit `lmc status` auch nach einem Gateway-Restart weiss, ob der
Worktree frisch ist. Das CLI ist zustandslos; dieser State ist die einzige
Persistenz.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, Optional

CACHE_DIR = Path(os.environ.get("LUMOS_CACHE", Path.home() / ".cache" / "lumos"))
STATE_FILE = CACHE_DIR / "worktrees.json"


def _load() -> Dict[str, dict]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(state: Dict[str, dict]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def register(codebase_hash: str, path: str, language: str,
             joern_built: bool = False, joern_bin: Optional[str] = None) -> dict:
    """Trägt/aktualisiert einen Worktree im State."""
    state = _load()
    entry = {
        "path": str(Path(path).resolve()),
        "language": language,
        "joern_built": joern_built,
        "joern_bin": joern_bin,
        "built_at": time.time(),
    }
    state[codebase_hash] = entry
    _save(state)
    return entry


def get(codebase_hash: str) -> Optional[dict]:
    return _load().get(codebase_hash)


def list_all() -> Dict[str, dict]:
    return _load()


def remove(codebase_hash: str) -> bool:
    state = _load()
    if codebase_hash in state:
        del state[codebase_hash]
        _save(state)
        return True
    return False


if __name__ == "__main__":
    # ponytail: self-check der Registry.
    import tempfile
    orig = STATE_FILE
    with tempfile.TemporaryDirectory() as d:
        globals()["STATE_FILE"] = Path(d) / "wt.json"
        register("h1", "/tmp/x", "php", joern_built=True, joern_bin="/cpgs/h1.bin")
        assert get("h1")["language"] == "php"
        assert get("h1")["joern_built"] is True
        assert len(list_all()) == 1
        assert remove("h1") is True
        assert get("h1") is None
    globals()["STATE_FILE"] = orig
    print("worktree.py self-check OK")