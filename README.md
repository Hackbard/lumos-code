# Lumos Code (`lmc`)

Polyglot CPG-Stack (Code Property Graph) für lokales Live-Coding und
Agent-Guardrails. `lmc` bringt **seinen eigenen CPG-Server** mit
(tree-sitter-basiert) — kein externer Server nötig. Er baut echte
Code-Property-Graphen für 13 Sprachen und beantwortet strukturelle Fragen
(callers/callees/impact/source) als Gedächtnis für Coding-Agenten.

> **Regel #1:** Bei strukturellen Fragen ("Wer ruft Methode X auf?") raten
> Agenten nie — sie fragen `lmc`.

## Unterstützte Sprachen

`c`, `cpp`, `csharp`, `go`, `java`, `javascript`, `kotlin`, `php`, `python`,
`ruby`, `scala`, `swift`, `typescript`.

Spracherkennung pro Worktree per Datei-Endung; dominierende Sprache wird in
`lumos.yml` abgelegt.

**Grenzen (ehrlich):** Call-Graph-Ebene (callers/callees/impact) — keine
dynamische Dispatch-Analyse, kein Data-Flow/Taint. Rohe CPGQL/Data-Flow
braucht das Joern-Backend (nicht angebunden; `lmc query` meldet das ehrlich).

## Installation

Benötigt Python >=3.10 und [uv](https://docs.astral.sh/uv/).

```bash
uv sync                 # Abhängigkeiten aus uv.lock installieren
uv run lmc --help       # CLI starten (Entry-Point: lmc = lmc.cli:app)
```

Oder global als Tool:

```bash
uv build
uv tool install dist/lumos_code-0.1.0-py3-none-any.whl --force
lmc up                  # CPG-Server starten (Port 4243)
```

## Architektur

```
Agent / Mensch
   │  typer CLI (--json für maschinenlesbaren Output)
   ▼
CodebadgerClient (httpx JSON-RPC)
   ▼
Lumos CPG-Server (Starlette + uvicorn, 127.0.0.1:4243)
   │  tools/call: generate_cpg, get_cpg_status, find_methods,
   │              get_call_graph, get_source, get_context, run_cpgql_query
   ▼
tree-sitter CPG-Extractor (polyglot) -> in-memory Index (Methoden + Call-Kanten)
```

Das CLI ist **zustandslos**: Es speichert keinen Worktree-Kontext. Der Agent
ist für das Kontextmanagement zuständig (`--path`, `lumos.yml`).

## Schnellstart

```bash
lmc up                                   # Server starten
lmc init --auto --path . --json          # lumos.yml schreiben (Sprache erkennen)
lmc build --path . --json                # CPG bauen
lmc find "Order" --path . --json         # Methoden finden
lmc impact OrderController.store --path . --depth 3 --json   # Blast-Radius
lmc check-diff --path . --json           # Precommit-Guardrail
lmc down                                 # Server stoppen
```

## CLI-Befehle

Globale Flags (für alle Befehle): `--url <server>` und `--hash <cpg>` (sonst
Auto-Auflösung aus `--path`). Für Agenten immer `--json`.

### Lifecycle
| Befehl | Zweck |
|---|---|
| `lmc up [--url]` | CPG-Server starten (Hintergrund, PID in `~/.cache/lumos/`) |
| `lmc down` | CPG-Server stoppen |
| `lmc serve [--host] [--port]` | Server im Vordergrund (Debug) |

### Setup
| Befehl | Zweck |
|---|---|
| `lmc init --auto --path <w> --json` | Sprache erkennen + `lumos.yml` schreiben |
| `lmc build --path <w> --json` | CPG bauen/aktualisieren (Sprache aus `lumos.yml`) |
| `lmc status --path <w> --json` | Server-Status + CPG-Frische |

### Navigation
| Befehl | Zweck |
|---|---|
| `lmc find <pattern> --path <w> --json` | Klassen/Methoden per Regex finden |
| `lmc callers <m> --path <w> --json` | Wer ruft diese Methode auf? |
| `lmc callees <m> --path <w> --json` | Was ruft diese Methode auf? |
| `lmc source <m> --path <w> --json` | Quelltext + Datei:Zeile |
| `lmc context <m> --path <w> --json` | Caller + Callee + Source gebündelt |

### Analyse / Guardrails
| Befehl | Zweck |
|---|---|
| `lmc impact <m> --path <w> --depth N --json` | Blast-Radius (rekursiv) |
| `lmc check-diff --path <w> --json` | `git diff` auf CPG mappen (Precommit) |
| `lmc precommit --path <w> --json` | Alias für `check-diff` |

### Escape-Hatch
| Befehl | Zweck |
|---|---|
| `lmc query "<CPGQL>" --path <w> --json` | Rohe Joern/CPGQL-Abfrage (braucht Joern-Backend) |

### Agent-Guardrails
1. **Server:** `lmc up` einmalig; der Server hält CPGs in-memory.
2. **Kontext managen:** Neues Verzeichnis? Auf `lumos.yml` prüfen, sonst
   `lmc init --auto`. Bei Monorepos immer `--path` mitgeben.
3. **Vor Refactoring:** `lmc impact <Method> --json` und alle Depth-1-Aufrufer
   anpassen.
4. **Pre-Commit:** `lmc check-diff --json` — betroffene Methoden beheben.
5. **Cross-Boundary:** Frontend-Änderung mit HTTP-Call → Route extrahieren,
   `--path ./backend` wechseln, Backend-Controller per `lmc impact` prüfen.
6. **Frische-Disziplin:** Neue Dateien/Methoden → `lmc build --path .`.

## Bibliotheks-API (ohne CLI)

```python
from lmc.server.cpg import build_index
idx = build_index("hash", "php", "./src")
[idx.callers("OrderController.save"), idx.impact("OrderController.save", 3)]
```

Module: `lmc.server.cpg` (Extractor/Index), `lmc.server.store`,
`lmc.server.app` (Starlette-App), `lmc.server.lifecycle`.

## Paket bauen

```bash
uv build            # dist/lumos_code-0.1.0-py3-none-any.whl + .tar.gz
```

## Projektstruktur

```
lmc/
├── __init__.py
├── cli.py            # typer CLI (alle Befehle + globale Flags)
├── client.py         # CodebadgerClient (httpx JSON-RPC)
├── config.py         # lumos.yml + polyglote Sprach-Erkennung
└── server/
    ├── __main__.py   # `python -m lmc.server` (uvicorn)
    ├── app.py        # Starlette JSON-RPC-Server (Tools)
    ├── cpg.py        # tree-sitter CPG-Extractor + Index/Queries
    ├── store.py      # in-memory Hash -> Index
    └── lifecycle.py  # up/down (subprocess + pidfile)
pyproject.toml        # Hatchling-Build + Entry-Point `lmc`
uv.lock
SKILL.md              # Guardrail-Regeln für Coding-Agenten
```

## Lizenz

Siehe `LICENSE`.