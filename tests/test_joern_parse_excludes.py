"""Regression-Test: CPG-Bau muss Dependency-Ordner ausschliessen.

Bug 2026-08-11: ``joern_parse`` rief ``joern-parse /code -o out`` ueber den ganzen
Worktree auf — ohne Exclude. In einem Laravel-Projekt sind das 3.578 Projekt- plus
55.226 ``vendor``-Dateien; das PHP-Frontend stirbt an vendor-Code (exit 255), der
ganze Build faellt mit ``joern-parse exit 1`` um und es entsteht gar kein CPG.

Naheliegende Abhilfe war ``--frontend-args --exclude ...``, die aber nicht traegt:
``joern-parse`` reicht diese Argumente auch an den TypeStubs-Schritt weiter, der
daran scheitert (``unable to parse XTypeStubsParserConfig``) — der CPG wird zwar
geschrieben, der Lauf endet trotzdem mit exit 1.

Fix: bei bekannter Sprache das Frontend (php2cpg, jssrc2cpg, ...) direkt aufrufen,
dort greifen die ``--exclude``-Flags. Unbekannte Sprache -> unveraendert joern-parse.
"""
import os
import sys

# Repo-Root zum Pfad hinzufuegen (laeuft ohne Install).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lmc.joern import (  # noqa: E402
    DEFAULT_EXCLUDES,
    FRONTEND_BY_LANGUAGE,
    parse_command,
)

OUT = "/cpgs/deadbeef.bin"


def test_known_language_uses_frontend_directly():
    """PHP -> php2cpg statt joern-parse, sonst greifen die Excludes nicht."""
    cmd = parse_command("/w", OUT, "php")
    assert "php2cpg" in cmd, cmd
    assert "joern-parse" not in cmd, "joern-parse verschluckt die Excludes"
    assert cmd[-2:] == ["-o", OUT], f"Output-Flag muss am Ende stehen -> {cmd[-3:]}"


def test_dependency_dirs_are_excluded():
    """vendor/node_modules muessen raus — das ist der eigentliche Bug."""
    cmd = parse_command("/w", OUT, "php")
    assert "/code/vendor" in cmd, "vendor fehlt -> Build stirbt an 55k Dateien"
    assert "/code/node_modules" in cmd
    assert cmd.count("--exclude") == len(DEFAULT_EXCLUDES)
    # Jedes Exclude ist relativ zum Container-Mount, nicht zum Host-Pfad.
    for i, tok in enumerate(cmd):
        if tok == "--exclude":
            assert cmd[i + 1].startswith("/code/"), cmd[i + 1]


def test_excludes_only_hit_toplevel_dirs():
    """`/code/vendor` darf projekteigene Pfade wie patches/vendor nicht treffen."""
    cmd = parse_command("/w", OUT, "php")
    assert "/code/patches/vendor" not in cmd
    assert all(t.count("/") == 2 for t in cmd if t.startswith("/code/")), \
        "Excludes muessen Top-Level bleiben"


def test_unknown_language_falls_back_unchanged():
    """Fallback = exakt das alte Verhalten, damit nichts anderes kaputtgeht."""
    fallback = parse_command("/w", OUT, None)
    assert fallback[-4:] == ["joern-parse", "/code", "-o", OUT], fallback
    assert "--exclude" not in fallback
    assert parse_command("/w", OUT, "klingonisch") == fallback


def test_language_lookup_is_case_insensitive():
    """lumos.yml ist handgeschrieben — 'PHP' muss wie 'php' wirken."""
    assert parse_command("/w", OUT, "PHP") == parse_command("/w", OUT, "php")


def test_mount_is_readonly_and_volume_attached():
    """Der Worktree wird nur lesend gemountet; das CPG-Volume muss dran sein."""
    cmd = parse_command("/some/worktree", OUT, "php")
    assert "/some/worktree:/code:ro" in cmd, "Source-Mount fehlt oder ist schreibbar"
    assert any(t.startswith("lmc-cpgs:") for t in cmd), "CPG-Volume fehlt"


def test_every_mapped_frontend_is_a_known_joern_binary():
    """Tippfehler im Mapping wuerden erst zur Laufzeit im Container auffallen."""
    known = {
        "c2cpg", "csharpsrc2cpg", "gosrc2cpg", "javasrc2cpg", "jssrc2cpg",
        "kotlin2cpg", "php2cpg", "pysrc2cpg", "rubysrc2cpg", "swiftsrc2cpg",
    }
    unknown = set(FRONTEND_BY_LANGUAGE.values()) - known
    assert not unknown, f"unbekannte Frontend-Binaries im Mapping: {unknown}"


if __name__ == "__main__":
    for fn in (
        test_known_language_uses_frontend_directly,
        test_dependency_dirs_are_excluded,
        test_excludes_only_hit_toplevel_dirs,
        test_unknown_language_falls_back_unchanged,
        test_language_lookup_is_case_insensitive,
        test_mount_is_readonly_and_volume_attached,
        test_every_mapped_frontend_is_a_known_joern_binary,
    ):
        fn()
        print(f"ok: {fn.__name__}")
    print("all joern parse-command tests passed")
