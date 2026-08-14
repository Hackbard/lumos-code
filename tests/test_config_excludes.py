"""Projekteigene Ausschluesse aus dem `exclude:`-Key der lumos.yml.

Motivation 2026-08-14: ein Laravel-Repo schleppte einen Legacy-Baum mit
1,5-MB-Font-Arrays mit, an dem php2cpg mit ``java.lang.OutOfMemoryError`` starb.
So ein Ordnername ist projektspezifisch und hat in DEFAULT_EXCLUDES nichts zu
suchen — dafuer gibt es jetzt ``exclude:`` in der lumos.yml.

Generische Dependency-/Cache-Ordner bleiben dagegen in den Default-Listen; der
Test haelt beide Ebenen auseinander.
"""
import os
import sys
import tempfile
from pathlib import Path

# Repo-Root zum Pfad hinzufuegen (laeuft ohne Install).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lmc.config import excludes_from_config, save_config  # noqa: E402
from lmc.joern import DEFAULT_EXCLUDES, parse_command  # noqa: E402

OUT = "/cpgs/deadbeef.bin"


def _worktree(tmp: str, exclude=None) -> str:
    """Minimaler Worktree mit lumos.yml — genau das, was `lmc init` schreibt."""
    extra = {"codebase_hash": "deadbeef"}
    if exclude is not None:
        extra["exclude"] = exclude
    save_config(tmp, "php", extra=extra)
    return tmp


def test_no_config_means_no_extra_excludes():
    """Ohne lumos.yml darf nichts explodieren — leere Menge, kein Fehler."""
    with tempfile.TemporaryDirectory() as d:
        assert excludes_from_config(d) == set()


def test_missing_key_means_no_extra_excludes():
    """lumos.yml ohne `exclude:` ist der Normalfall (so schreibt `lmc init` sie)."""
    with tempfile.TemporaryDirectory() as d:
        assert excludes_from_config(_worktree(d)) == set()


def test_exclude_key_is_read():
    """Der eigentliche Zweck: Namen aus der Config kommen an, Slashes normalisiert."""
    with tempfile.TemporaryDirectory() as d:
        got = excludes_from_config(_worktree(d, ["legacy", "third_party/"]))
        assert got == {"legacy", "third_party"}, got


def test_config_excludes_reach_the_frontend_command():
    """Ohne diesen Schritt liest die Config zwar, der CPG-Bau ignoriert sie aber."""
    cmd = parse_command("/w", OUT, "php", extra_excludes={"legacy"})
    assert "/code/legacy" in cmd, cmd
    assert "/code/vendor" in cmd, "Defaults duerfen nicht verdraengt werden"


def test_config_excludes_are_not_duplicated():
    """`vendor` doppelt (Default + Config) wuerde php2cpg zwei gleiche Flags geben."""
    cmd = parse_command("/w", OUT, "php", extra_excludes={"vendor"})
    assert cmd.count("/code/vendor") == 1
    assert cmd.count("--exclude") == len(DEFAULT_EXCLUDES)


def test_index_skips_configured_dir():
    """Der Beweis am Ergebnis: die Datei taucht nicht im Index auf."""
    from lmc.server.graph import build_index

    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "app").mkdir()
        (Path(d) / "app" / "Keep.php").write_text("<?php\nfunction keep_me() {}\n")
        (Path(d) / "legacy").mkdir()
        (Path(d) / "legacy" / "Drop.php").write_text("<?php\nfunction drop_me() {}\n")

        _worktree(d)  # noch ohne exclude
        names = {m.name for m in build_index("deadbeef", "php", d).methods}
        assert names == {"keep_me", "drop_me"}, f"Baseline stimmt nicht: {names}"

        _worktree(d, ["legacy"])
        names = {m.name for m in build_index("deadbeef", "php", d).methods}
        assert names == {"keep_me"}, f"legacy/ haette rausfallen muessen: {names}"


if __name__ == "__main__":
    for fn in (
        test_no_config_means_no_extra_excludes,
        test_missing_key_means_no_extra_excludes,
        test_exclude_key_is_read,
        test_config_excludes_reach_the_frontend_command,
        test_config_excludes_are_not_duplicated,
        test_index_skips_configured_dir,
    ):
        fn()
        print(f"ok: {fn.__name__}")
    print("all lumos.yml exclude tests passed")
