"""lumos.yml-Handling + polyglote Sprach-Erkennung fuer Lumos Code.

Kein Mock: Sprache wird aus Datei-Endungen erkannt, die Config wirklich
geschrieben/gelesen, der Codebase-Hash deterministisch aus dem Pfad abgeleitet.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Dict

import yaml

# Joern/Codebadger unterstuetzte Sprachen -> Datei-Endungen.
# ponytail: rein extensionsbasiert; Framework-Sniffing (Laravel/Vue/...) ist
# YAGNI bis ein echtes Build-Target es braucht.
LANGUAGE_EXTENSIONS: Dict[str, set] = {
    "php": {".php", ".phtml", ".php5", ".php4"},
    "javascript": {".js", ".jsx", ".mjs", ".cjs"},
    "typescript": {".ts", ".tsx", ".mts", ".cts"},
    "python": {".py", ".pyi"},
    "java": {".java"},
    "c": {".c", ".h"},
    "cpp": {".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"},
    "csharp": {".cs"},
    "go": {".go"},
    "kotlin": {".kt", ".kts"},
    "ruby": {".rb"},
    "swift": {".swift"},
    "scala": {".scala", ".sc"},
}

SUPPORTED_LANGUAGES = sorted(LANGUAGE_EXTENSIONS)

# Verzeichnisse, die der Scan ueberspringt (Dependencies/Build-Artefakte).
IGNORE_DIRS = {
    ".git", "node_modules", "vendor", ".venv", "venv", "dist", "build",
    "__pycache__", ".idea", ".vscode", "target", "bower_components",
    "storage", "var", "cache",
}

CONFIG_NAME = "lumos.yml"


def _ext_to_lang() -> Dict[str, str]:
    table: Dict[str, str] = {}
    for lang, exts in LANGUAGE_EXTENSIONS.items():
        for ext in exts:
            table[ext] = lang
    return table


_EXT_LANG = _ext_to_lang()


def detect_language(path) -> str:
    """Erkennt die dominierende Sprache anhand der Datei-Endungen im Worktree."""
    root = Path(path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Pfad nicht gefunden: {root}")
    counts: Counter[str] = Counter()
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        # Nur Elternverzeichnisse auf IGNORE pruefen (Datei selbst egal).
        if any(part in IGNORE_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        lang = _EXT_LANG.get(p.suffix.lower())
        if lang:
            counts[lang] += 1
    if not counts:
        raise ValueError(
            f"Keine unterstuetzte Quelldatei in {root} gefunden. "
            f"Unterstuetzt: {', '.join(SUPPORTED_LANGUAGES)}"
        )
    return counts.most_common(1)[0][0]


def codebase_hash(path) -> str:
    """Deterministischer Hash fuer einen Worktree (Schluessel fuer MCP-Calls)."""
    return hashlib.sha1(str(Path(path).resolve()).encode()).hexdigest()[:16]


def load_config(path) -> dict:
    """Liest lumos.yml; liefert {} wenn keine existiert."""
    cfg = Path(path).resolve() / CONFIG_NAME
    if not cfg.exists():
        return {}
    return yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}


def save_config(path, language: str, extra: dict | None = None) -> Path:
    """Schreibt lumos.yml mit Sprache + optionalem extra (z.B. codebase_hash)."""
    cfg_path = Path(path).resolve() / CONFIG_NAME
    data: dict = {"language": language}
    if extra:
        data.update(extra)
    cfg_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return cfg_path


if __name__ == "__main__":
    # ponytail: ein runnable self-check, der bricht wenn Detection/Hash kaputt sind.
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "a.php").write_text("<?php\n")
        (Path(d) / "b.php").write_text("<?php\n")
        (Path(d) / "c.ts").write_text("export {}\n")
        assert detect_language(d) == "php", "php sollte dominieren (2 vs 1)"
        p = save_config(d, "php", extra={"codebase_hash": codebase_hash(d)})
        assert p.exists()
        cfg = load_config(d)
        assert cfg["language"] == "php"
        assert cfg["codebase_hash"] == codebase_hash(d)
        assert len(codebase_hash(d)) == 16
    print("config.py self-check OK")