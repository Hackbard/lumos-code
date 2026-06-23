"""In-memory Store: codebase_hash -> fertiger CPG-Index."""
from __future__ import annotations

import time
from typing import Dict, Optional

from .cpg import Index, build_index

_STORE: Dict[str, dict] = {}  # hash -> {"index": Index, "language": str, "built_at": float}


def generate(codebase_hash: str, source_path: str, language: str) -> Index:
    idx = build_index(codebase_hash, language, source_path)
    _STORE[codebase_hash] = {
        "index": idx, "language": language, "built_at": time.time(),
        "source_path": source_path,
    }
    return idx


def get(codebase_hash: str) -> Optional[Index]:
    entry = _STORE.get(codebase_hash)
    return entry["index"] if entry else None


def status(codebase_hash: str) -> dict:
    entry = _STORE.get(codebase_hash)
    if not entry:
        return {"exists": False}
    idx: Index = entry["index"]
    return {
        "exists": True,
        "language": entry["language"],
        "methods": len(idx.methods),
        "edges": len(idx.edges),
        "files": len(idx.files),
        "built_at": entry["built_at"],
    }


def list_hashes() -> list:
    return list(_STORE.keys())