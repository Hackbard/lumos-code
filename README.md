# Lumos Code (`lmc`)

Polyglot CPG-Stack (Code Property Graph) für lokales Live-Coding und
Agent-Guardrails. `lmc` ist ein zustandsloses CLI, das einen lokalen
**Codebadger MCP-Server** ansteuert, um Code Property Graphen (via Joern)
aufzubauen und abzufragen — als strukturelles Gedächtnis für Coding-Agenten.

> **Regel #1:** Bei strukturellen Fragen ("Wer ruft Methode X auf?") raten
> Agenten nie — sie fragen `lmc`.

## Status

Frühes Gerüst (v0.1.0). Die CLI-Befehle und der `CodebadgerClient` stehen,
viele Antworten sind noch gemockt (siehe `# Mock`-Stellen in `cli.py`).
Der MCP-Client spricht aber bereits das echte JSON-RPC-Protokoll.

## Installation

Benötigt Python >=3.10 und [uv](https://docs.astral.sh/uv/).

```bash
uv sync                 # Abhängigkeiten aus uv.lock installieren
uv run lmc --help       # CLI starten (Entry-Point: lmc = lmc.cli:app)
```

Oder als Editier-Install in ein bestehendes venv:

```bash
uv pip install -e .
```

## Architektur

```
Agent / Mensch
   │  typer CLI (--json für maschinenlesbaren Output)
   ▼
lmc.cli.CodebadgerClient  ──httpx (JSON-RPC)──►  Codebadger MCP-Server
                                                    (baut/queryt Joern-CPGs)
```

Das CLI ist **zustandslos**: Es speichert keinen Worktree-Kontext. Der Agent
ist für das Kontextmanagement zuständig (`--path`, `lumos.yml`).

## CLI-Befehle

Für Agenten immer `--json` verwenden.

| Befehl | Zweck |
|---|---|
| `lmc init --auto` | Initialisiert Lumos im Workspace (`lumos.yml`) |
| `lmc build --path . --json` | Baut/aktualisiert den CPG für einen Worktree |
| `lmc status --json` | Status des Graphen + geladene Sprache |
| `lmc impact <Method> --depth=3 --json` | Rekursive Blast-Radius-Analyse |
| `lmc check-diff --json` | Mappt `git diff` auf den CPG → Warnungen |
| `lmc callers <Method> --json` | Direkte Aufrufer einer Methode |
| `lmc query <CPGQL> --json` | Rohe CPGQL/Joern-Abfrage (Escape-Hatch) |

### Agent-Guardrails

1. **Kontext managen:** Neues Verzeichnis? Auf `lumos.yml` prüfen, sonst
   `lmc init --auto`. Bei Monorepos immer `--path` mitgeben.
2. **Vor Refactoring:** `lmc impact <Vollst.MethodenName> --json` ausführen und
   alle Depth-1-Aufrufer anpassen.
3. **Pre-Commit:** `lmc check-diff --json` — architektonische Warnungen
   beheben, bevor ein Commit vorgeschlagen wird.
4. **Cross-Boundary:** Frontend-Änderung mit HTTP-Call → Route extrahieren,
   `--path ./backend` wechseln, Backend-Controller per `lmc impact` prüfen.
5. **Frische-Disziplin:** Neue Dateien/Methoden → `lmc build --path .`
   aktualisiert den Graphen.

## Paket bauen

Build-Backend ist [Hatchling](https://hatch.pypa.io/). Ein Rad und ein sdist
in `dist/` erzeugen:

```bash
uv build            # erzeugt dist/lumos_code-0.1.0-py3-none-any.whl + .tar.gz
```

Vorab prüfen, dass das Wheel den `lmc`-Paket-Ordner enthält:

```bash
uv run python -c "import zipfile,glob; \
w=sorted(glob.glob('dist/*.whl'))[-1]; \
print('\n'.join(zipfile.ZipFile(w).namelist()))"
```

## Projektstruktur

```
lmc/
├── __init__.py   # Paketmarker + __version__
├── cli.py        # typer CLI-Befehle
└── client.py     # CodebadgerClient (httpx JSON-RPC an MCP-Server)
pyproject.toml    # Projekt + Hatchling-Build-Config + Entry-Point `lmc`
uv.lock           # gesperrte Abhängigkeiten
SKILL.md          # Guardrail-Regeln für Coding-Agenten
```

## Lizenz

Siehe `LICENSE`.