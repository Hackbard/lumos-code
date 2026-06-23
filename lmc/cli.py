import json
import subprocess
import typer
from rich.console import Console
from rich.table import Table
from pathlib import Path

from .client import CodebadgerClient, default_url
from .config import (
    detect_language, codebase_hash, load_config, save_config,
    SUPPORTED_LANGUAGES, CONFIG_NAME,
)
from .server import lifecycle
from .server.lifecycle import is_running, start_server, stop_server
from . import joern as joern_mod

app = typer.Typer(
    name="lmc",
    help="Lumos Code - Polyglot CPG-Stack für lokales Live-Coding",
    no_args_is_help=True,
)
console = Console()
_G = {"url": None, "hash": None}


@app.callback()
def _root(
    url: str = typer.Option(None, "--url", help="Codebadger-Server-URL (Default: localhost:4242/mcp)"),
    hash: str = typer.Option(None, "--hash", help="CPG-Hash (sonst Auto-Auflösung aus --path)"),
):
    """Globale Flags: --url und --hash gelten fuer alle Befehle."""
    _G["url"] = url
    _G["hash"] = hash


def _client() -> CodebadgerClient:
    return CodebadgerClient(_G.get("url"))


def _hash_for(path: str) -> str:
    return _G["hash"] or codebase_hash(path)


def _emit(data: dict, as_json: bool):
    if as_json:
        typer.echo(json.dumps(data, ensure_ascii=False))
        return
    if not data.get("success"):
        console.print(f"[bold red]Fehler:[/bold red] {data.get('error')}")
        return
    _render(data)


def _render(data: dict):
    payload = data.get("data")
    if isinstance(payload, dict):
        for k, v in payload.items():
            if isinstance(v, (dict, list)):
                console.print(f"[bold]{k}[/bold]:")
                console.print_json(json.dumps(v, ensure_ascii=False))
            else:
                console.print(f"[bold]{k}[/bold]: {v}")
    else:
        console.print(payload or "Erfolg!")


def _lang_from(path: str):
    cfg = load_config(path)
    if "language" in cfg:
        return cfg["language"], "lumos.yml"
    return detect_language(path), "auto-detect"


# --- Server Lifecycle ---

@app.command()
def up(
    url: str = typer.Option(None, "--url", help="URL, auf der der Server laufen soll"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Startet den lokalen CPG-Server (lmc up)."""
    result = start_server(url)
    _emit(result, as_json)


@app.command()
def down(as_json: bool = typer.Option(False, "--json")):
    """Stoppt den lokalen CPG-Server (lmc down)."""
    _emit(stop_server(), as_json)


@app.command()
def serve(
    host: str = typer.Option(None, "--host"),
    port: int = typer.Option(None, "--port"),
):
    """Laesst den Server im Vordergrund laufen (Debug/Entwicklung)."""
    import os
    if host:
        os.environ["LUMOS_HOST"] = host
    if port:
        os.environ["LUMOS_PORT"] = str(port)
    from .server.__main__ import main as run
    run()


# --- Setup ---

@app.command()
def init(
    path: str = typer.Option(".", "--path", help="Pfad zum Worktree"),
    auto: bool = typer.Option(True, "--auto/--no-auto", help="Auto-Spracherkennung + lumos.yml schreiben"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Initialisiert Lumos in einem Workspace (schreibt lumos.yml)."""
    if not auto:
        _emit({"success": False, "error": "Manueller Modus nicht unterstützt. Nutze 'lmc init --auto'."}, as_json)
        return
    try:
        language = detect_language(path)
        cbh = codebase_hash(path)
        cfg_path = save_config(path, language, extra={"codebase_hash": cbh})
        _emit({"success": True, "data": {
            "language": language, "codebase_hash": cbh, "config": str(cfg_path),
            "supported": SUPPORTED_LANGUAGES}}, as_json)
    except Exception as e:
        _emit({"success": False, "error": str(e)}, as_json)


@app.command()
def build(
    path: str = typer.Option(".", "--path", help="Pfad zum Worktree"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Baut den CPG für den aktuellen Worktree (lmc build)."""
    try:
        language, quelle = _lang_from(path)
    except Exception as e:
        _emit({"success": False, "error": str(e)}, as_json)
        return
    cbh = _hash_for(path)
    if not as_json:
        console.print(f"[bold blue]Baue CPG für {path}[/bold blue] "
                      f"[dim](Sprache: {language} via {quelle}, hash: {cbh})[/dim]")
    result = _client().generate_cpg(source_path=str(Path(path).resolve()), language=language, codebase_hash=cbh)
    # Joern-CPG (<hash>.bin) im Volume — best-effort; nav laeuft ohnehin auf tree-sitter.
    joern_res = joern_mod.joern_parse(str(Path(path).resolve()), cbh)
    if isinstance(result, dict) and result.get("success"):
        result["data"] = {**(result.get("data") or {}), "codebase_hash": cbh,
                          "language": language, "joern": joern_res}
    _emit(result, as_json)


@app.command()
def status(
    path: str = typer.Option(".", "--path", help="Pfad zum Worktree"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Server-Status + CPG-Frische des Worktrees (lmc status)."""
    cbh = _hash_for(path)
    server_up = is_running(_G.get("url"))
    joern_up = joern_mod.JoernClient().is_up()
    try:
        language, quelle = _lang_from(path)
    except Exception:
        language, quelle = None, None
    result = _client().get_cpg_status(cbh)
    data = result.get("data") or {}
    base = {"gateway_up": server_up, "joern_up": joern_up,
            "codebase_hash": cbh, "language": language}
    if not data.get("exists"):
        data = {**base, "cpg_built": False,
                "hinweis": "Kein CPG gebaut — 'lmc build --path <p>' ausfuehren."}
    else:
        data = {**base, "cpg_built": True, **data}
    _emit({"success": result.get("success", True), "data": data}, as_json)


# --- Navigation ---

ENGINE_OPT = lambda: typer.Option("treesitter", "--engine",
    help="joern = genaue Joern-Antwort (langsam); treesitter = instant (Default)")


@app.command()
def find(
    pattern: str = typer.Argument(..., help="Name oder Regex fuer Klassen/Methoden"),
    path: str = typer.Option(".", "--path", help="Pfad zum Worktree"),
    engine: str = ENGINE_OPT(),
    as_json: bool = typer.Option(False, "--json"),
):
    """Klassen/Methoden per Name oder Regex finden (lmc find)."""
    cbh = _hash_for(path)
    result = (joern_mod.nav_find(cbh, pattern, url=_G.get("url"))
             if engine == "joern" else _client().find_methods(cbh, pattern))
    _emit(result, as_json)


@app.command()
def callers(
    method: str = typer.Argument(..., help="Methoden-Spec (Class.method oder name)"),
    path: str = typer.Option(".", "--path", help="Pfad zum Worktree"),
    engine: str = ENGINE_OPT(),
    as_json: bool = typer.Option(False, "--json"),
):
    """Wer ruft diese Methode auf? (lmc callers)"""
    cbh = _hash_for(path)
    result = (joern_mod.nav_callers(cbh, method, url=_G.get("url"))
             if engine == "joern"
             else _client().get_call_graph(cbh, method, direction="incoming", depth=1))
    _emit(result, as_json)


@app.command()
def callees(
    method: str = typer.Argument(..., help="Methoden-Spec (Class.method oder name)"),
    path: str = typer.Option(".", "--path", help="Pfad zum Worktree"),
    engine: str = ENGINE_OPT(),
    as_json: bool = typer.Option(False, "--json"),
):
    """Was ruft diese Methode auf? (lmc callees)"""
    cbh = _hash_for(path)
    result = (joern_mod.nav_callees(cbh, method, url=_G.get("url"))
             if engine == "joern"
             else _client().get_call_graph(cbh, method, direction="outgoing", depth=1))
    _emit(result, as_json)


@app.command()
def source(
    method: str = typer.Argument(..., help="Methoden-Spec (Class.method oder name)"),
    path: str = typer.Option(".", "--path", help="Pfad zum Worktree"),
    engine: str = ENGINE_OPT(),
    as_json: bool = typer.Option(False, "--json"),
):
    """Quelltext + Datei:Zeile einer Methode (lmc source)."""
    cbh = _hash_for(path)
    result = (joern_mod.nav_source(cbh, method, url=_G.get("url"))
             if engine == "joern" else _client().get_source(cbh, method))
    _emit(result, as_json)


@app.command()
def context(
    symbol: str = typer.Argument(..., help="Symbol-Spec (Class.method oder name)"),
    path: str = typer.Option(".", "--path", help="Pfad zum Worktree"),
    engine: str = ENGINE_OPT(),
    as_json: bool = typer.Option(False, "--json"),
):
    """Caller + Callee + Source gebündelt (lmc context)."""
    cbh = _hash_for(path)
    result = (joern_mod.nav_context(cbh, symbol, url=_G.get("url"))
             if engine == "joern" else _client().get_context(cbh, symbol))
    _emit(result, as_json)


# --- Analyse / Guardrails ---

@app.command()
def impact(
    method: str = typer.Argument(..., help="Methoden-Spec (Class.method oder name)"),
    path: str = typer.Option(".", "--path", help="Pfad zum Worktree"),
    depth: int = typer.Option(3, "--depth", help="Ebenen fuer den Blast-Radius"),
    engine: str = ENGINE_OPT(),
    as_json: bool = typer.Option(False, "--json"),
):
    """Blast-Radius: wer ist betroffen, wenn diese Methode geändert wird? (lmc impact)"""
    if not as_json:
        console.print(f"[bold red]⚠️ IMPACT[/bold red] für [bold]{method}[/bold] [dim](depth={depth}, engine={engine})[/dim]\n")
    cbh = _hash_for(path)
    result = (joern_mod.nav_impact(cbh, method, depth, url=_G.get("url"))
             if engine == "joern"
             else _client().get_call_graph(cbh, method, direction="incoming", depth=depth))
    if not as_json and result.get("success"):
        affected = result.get("data", {}).get("affected", {})
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Tiefe")
        table.add_column("Betroffene Methoden")
        for d in sorted(affected, key=lambda x: int(x)):
            table.add_row(f"Depth {d}", ", ".join(affected[d]) or "—")
        console.print(table)
    else:
        _emit(result, as_json)


@app.command()
def check_diff(
    path: str = typer.Option(".", "--path", help="Pfad zum Worktree"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Mappt uncommittetes git diff auf den CPG (lmc check-diff / Precommit)."""
    root = Path(path).resolve()
    changed: list = []
    try:
        out = subprocess.run(["git", "diff", "--name-only", "--relative"],
                             cwd=root, capture_output=True, text=True, check=True)
        changed = [l for l in out.stdout.splitlines() if l]
    except subprocess.CalledProcessError as e:
        _emit({"success": False, "error": f"git diff fehlgeschlagen: {e.stderr or e}"}, as_json)
        return
    except Exception as e:
        _emit({"success": False, "error": f"git diff fehlgeschlagen: {e}"}, as_json)
        return
    cbh = _hash_for(path)
    warnings: list = []
    # ponytail: fuer jede geaenderte Datei schauen wir, ob sie im CPG enthalten ist
    # und liefern die betroffenen Methoden. Tieferes Symbol-Mapping pro Diff-Hunk
    # wuerde Joern-Level Differenzierung brauchen (Upgrade-Pfad).
    st = _client().get_cpg_status(cbh)
    cpg_built = bool((st.get("data") or {}).get("exists"))
    if cpg_built and changed:
        # Methoden in geaenderten Dateien = primaerer Blast-Radius-Kandidat.
        find_all = _client().find_methods(cbh, ".*")
        for m in (find_all.get("data") or {}).get("methods", []):
            if any(m["file"].endswith(c) for c in changed):
                warnings.append({"file": m["file"], "method": m["signature"], "line": m["line"]})
    data = {
        "changed_files": changed,
        "cpg_built": cpg_built,
        "warnings": warnings,
        "status": "safe" if not changed else ("review" if warnings else "clean"),
    }
    if as_json:
        typer.echo(json.dumps(data, ensure_ascii=False))
    else:
        if changed:
            console.print("[bold blue]Geänderte Dateien:[/bold blue]")
            for f in changed:
                console.print(f"  • {f}")
            if warnings:
                console.print("[yellow]Betroffene CPG-Methoden:[/yellow]")
                for w in warnings:
                    console.print(f"  ⚠ {w['method']}  [dim]({w['file']}:{w['line']})[/dim]")
            elif cpg_built:
                console.print("[green]Keine CPG-Methoden in den geänderten Dateien. Commit safe![/green]")
            else:
                console.print("[yellow]CPG nicht gebaut — 'lmc build' fuer strukturelles Mapping.[/yellow]")
        else:
            console.print("[green]Keine uncommitteten Änderungen. Commit safe![/green]")


@app.command()
def precommit(
    path: str = typer.Option(".", "--path", help="Pfad zum Worktree"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Alias für check-diff (lmc precommit)."""
    check_diff(path=path, as_json=as_json)


# --- Escape-Hatch ---

@app.command()
def query(
    cpgql: str = typer.Argument(..., help="Rohe CPGQL Query"),
    path: str = typer.Option(".", "--path", help="Pfad zum Worktree"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Roher Joern/CPGQL-Escape-Hatch gegen das Joern-Backend (lmc query)."""
    result = joern_mod.run_cpgql(_hash_for(path), cpgql, url=_G.get("url"))
    _emit(result, as_json)


if __name__ == "__main__":
    app()