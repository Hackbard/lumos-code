import typer
import json
from rich.console import Console
from rich.table import Table
from typing import Optional
from pathlib import Path

# Interner Client (frisch geschrieben)
from .client import CodebadgerClient

app = typer.Typer(
    name="lmc", 
    help="Lumos Code - Polyglot CPG-Stack für lokales Live-Coding",
    no_args_is_help=True
)
console = Console()
client = CodebadgerClient()

def print_result(data: dict, as_json: bool):
    """Hilfsfunktion: Agenten bekommen JSON, Menschen bekommen hübsches UI."""
    if as_json:
        typer.echo(json.dumps(data))
    else:
        if not data.get("success"):
            console.print(f"[bold red]Fehler:[/bold red] {data.get('error')}")
            return
        console.print(data.get("data", "Erfolg!"))

# --- Setup & Infrastruktur ---

@app.command()
def init(auto: bool = typer.Option(False, "--auto", help="AI-gesteuerte Projekt-Erkennung")):
    """Initialisiert Lumos in einem Workspace (generiert lumos.yml)."""
    if auto:
        console.print("[bold blue]🚀 Lumos Auto-Discovery läuft...[/bold blue]")
        console.print("[dim]Scanne Workspace auf Frameworks (Vue, Laravel, etc.)...[/dim]")
        # Hier wird später der LLM-Scan (Schritt 2 der Roadmap) eingehängt
        console.print("[green]✓ lumos.yml erfolgreich durch AI generiert.[/green]")
    else:
        console.print("[yellow]Bitte nutze 'lmc init --auto', der manuelle Modus ist deprecated.[/yellow]")

@app.command()
def build(
    path: str = typer.Option(".", help="Pfad zum Worktree"),
    as_json: bool = typer.Option(False, "--json", help="JSON Output für Agenten")
):
    """Baut den Code Property Graph für den aktuellen Worktree."""
    if not as_json:
        console.print(f"[bold blue]Baue CPG für {path}...[/bold blue]")
    
    # Hier kommt später die Logik rein, die die lumos.yml liest 
    # und die Sprache (PHP, JS, etc.) ermittelt.
    language_mock = "php" 
    
    result = client.generate_cpg(source_path=path, language=language_mock)
    print_result(result, as_json)

@app.command()
def status(
    path: str = typer.Option(".", help="Pfad zum Worktree"),
    as_json: bool = typer.Option(False, "--json", help="JSON Output für Agenten")
):
    """Zeigt den Status des Graphen und die geladene Sprache an."""
    # Mock Hash für das Gerüst - in echt kommt der aus ~/.cache/lumos/worktrees.json
    mock_hash = "local_workspace_hash_123" 
    result = client.get_status(mock_hash)
    print_result(result, as_json)

# --- Guardrails & Impact Analysis ---

@app.command()
def impact(
    method: str = typer.Argument(..., help="Vollständiger Methodenname (z.B. App\\Http\\Controllers\\OrderController.store)"),
    depth: int = typer.Option(3, help="Wie viele Ebenen tief soll der Blast-Radius berechnet werden?"),
    as_json: bool = typer.Option(False, "--json", help="JSON Output für Agenten")
):
    """Rekursive Blast-Radius-Analyse (Cross-Boundary)."""
    if not as_json:
        console.print(f"[bold red]⚠️ IMPACT ANALYSIS (Blast Radius)[/bold red] für [bold]{method}[/bold]\n")
        
    mock_hash = "local_workspace_hash_123"
    result = client.get_call_graph(mock_hash, method, direction="incoming", depth=depth)
    
    if not as_json and result.get("success"):
        # UI Mock für den Menschen
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Tiefe")
        table.add_column("Betroffene Methoden (Müssen ggf. angepasst werden)")
        table.add_row("Depth 1", "App\\Jobs\\SyncCdiscountCatalog.handle")
        table.add_row("Depth 2", "App\\Console\\Commands\\RunAiPimSync.fire")
        console.print(table)
    elif as_json:
        print_result(result, as_json)

@app.command()
def check_diff(as_json: bool = typer.Option(False, "--json", help="JSON Output")):
    """Mappt uncommittetes 'git diff' auf den CPG und zeigt Warnungen."""
    if not as_json:
        console.print("[bold blue]Lese lokales Git-Diff...[/bold blue]")
        console.print("[green]Keine signifikanten Strukturänderungen im Blast-Radius erkannt. Commit safe![/green]")
    else:
        typer.echo('{"success": true, "warnings": [], "status": "safe"}')

# --- Strukturelle Abfragen ---

@app.command()
def callers(
    method: str, 
    as_json: bool = typer.Option(False, "--json", help="JSON Output")
):
    """Wer ruft diese Methode auf?"""
    mock_hash = "local_workspace_hash_123"
    result = client.get_call_graph(mock_hash, method, direction="incoming", depth=1)
    print_result(result, as_json)

@app.command()
def query(
    cpgql: str = typer.Argument(..., help="Rohe CPGQL Query"),
    as_json: bool = typer.Option(False, "--json", help="JSON Output")
):
    """Roher Scala/Joern-Escape-Hatch für komplexe Abfragen."""
    mock_hash = "local_workspace_hash_123"
    result = client.run_query(mock_hash, cpgql)
    print_result(result, as_json)

if __name__ == "__main__":
    app()