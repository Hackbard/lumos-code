"""Regression-Test: tree-sitter Byte-Offset vs Python-str-Codepoint-Offset.

Bug 2026-07-08: ``_text`` slicete ``src`` (str) mit tree-sitter BYTE-Offsets. Bei
Non-ASCII-Content (Umlaute in Kommentaren/Strings) VOR einem Knoten ist
Byte-Offset != Codepoint-Offset -> der Slice droppte fuehrende Zeichen
(``CourseGateEvent`` -> ``ourseGateEvent``, ``casts`` -> ``asts``).

Fix: ``src`` als bytes (``read_text`` + ``.encode``) fuer das Byte-Offset-Slicing,
``parser.parse`` bekommt weiterhin str (tree-sitter-language-pack 1.11.0 verlangt str).
"""
import os
import sys
import tempfile

# Repo-Root zum Pfad hinzufuegen (laeuft ohne Install).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lmc.server import graph  # noqa: E402
from tree_sitter_language_pack import get_parser  # noqa: E402

_PARSER = get_parser("php")


def _build(php: str) -> graph.Index:
    d = tempfile.mkdtemp()
    open(os.path.join(d, "Sample.php"), "w").write(php)
    return graph.build_index("test-hash", "php", d)


def test_method_and_class_names_clean_with_umlaut_before():
    """Ein Umlaut VOR der Klasse/Methode darf die Namen nicht garblen."""
    php = (
        "<?php\n"
        "// Döner-Bude: Kommentar mit Umlaut ü ö ä ß vor dem Knoten\n\n"
        "class CourseGateEvent {\n"
        "    public function casts(): array { return []; }\n"
        "    public function recordSubmit(): void {}\n"
        "}\n"
    )
    idx = _build(php)
    names = {m.name for m in idx.methods}
    classes = {m.cls for m in idx.methods if m.cls}

    assert "casts" in names, f"method 'casts' garbled/missing -> {names}"
    assert "recordSubmit" in names, f"method 'recordSubmit' garbled/missing -> {names}"
    assert "CourseGateEvent" in classes, f"class 'CourseGateEvent' garbled -> {classes}"
    # Kein Garble: kein 'asts(' und kein 'ourseGateEvent'.
    assert "asts(" not in names
    assert not any(c and c.startswith("ourseGate") for c in classes)


def test_ascii_only_baseline_unchanged():
    """Reiner-ASCII-Pfad bleibt unbeeinflusst (kein Regressions-Risiko)."""
    php = (
        "<?php\n"
        "// plain ascii comment\n\n"
        "class Plain {\n"
        "    public function hello(): void {}\n"
        "}\n"
    )
    idx = _build(php)
    names = {m.name for m in idx.methods}
    classes = {m.cls for m in idx.methods if m.cls}
    assert "hello" in names
    assert "Plain" in classes


def test_multiple_multibyte_chars_offset_accumulates():
    """Mehrere Multibyte-Chars vor dem Knoten verschieben den Offset um >1 —
    der Fix muss jede Anzahl korrekt behandeln (Bytes != Codepoints kumulativ)."""
    php = (
        "<?php\n"
        "// ä ö ü ß Ä Ö Ü — acht Multibyte-Chars vor der Methode\n\n"
        "class Multi {\n"
        "    public function keeper(): void {}\n"
        "}\n"
    )
    idx = _build(php)
    names = {m.name for m in idx.methods}
    classes = {m.cls for m in idx.methods if m.cls}
    assert "keeper" in names, f"offset-accumulation bug -> {names}"
    assert "Multi" in classes


if __name__ == "__main__":
    for fn in (
        test_method_and_class_names_clean_with_umlaut_before,
        test_ascii_only_baseline_unchanged,
        test_multiple_multibyte_chars_offset_accumulates,
    ):
        fn()
        print(f"ok: {fn.__name__}")
    print("all graph nonascii-offset tests passed")