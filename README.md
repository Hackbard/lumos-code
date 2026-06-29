# Lumos Code (`lmc`)

Polyglot CPG-Stack (Code Property Graph) für lokales Live-Coding und
Agent-Guardrails. `lmc` bringt **beide Backends selbst mit**:

- **Joern-Backend** (Docker, echtes CPGQL / Data-Flow) — startbar via `lmc up`.
- **tree-sitter-Gateway** (polyglot, instant Navigation) — `find/callers/callees/impact/source/context`.

Kein externer Server nötig.

> **Regel #1:** Bei strukturellen Fragen ("Wer ruft Methode X auf?") raten
> Agenten nie — sie fragen `lmc`.

## Unterstützte Sprachen

`c`, `cpp`, `csharp`, `go`, `java`, `javascript`, `kotlin`, `php`, `python`,
`ruby`, `scala`, `swift`, `typescript`.

Spracherkennung pro Worktree per Datei-Endung; dominierende Sprache wird in
`lumos.yml` abgelegt. Joern selbst spricht zusätzlich Data-Flow/Taint (via
`lmc query`).

**Zweigleisig (ehrlich):**
- **Navigation** (`find/callers/callees/impact/source/context`) → tree-sitter,
  namensbasierte Call-Auflösung, instant, polyglot. Keine dynamische
  Dispatch-Analyse.
- **`lmc query "<CPGQL>"`** → echtes Joern-CPGQL (Data-Flow, Taint, beliebige
  Joern-Queries) gegen den gebauten CPG im Joern-Container.

## Installation

Benötigt Python >=3.10, [uv](https://docs.astral.sh/uv/) und **Docker** (fürs
Joern-Backend).

```bash
uv sync                 # Abhängigkeiten aus uv.lock
uv run lmc --help       # CLI (Entry-Point: lmc = lmc.cli:app)
```

Oder global als Tool:

```bash
uv build
uv tool install dist/lumos_code-0.2.0-py3-none-any.whl --force
lmc up                  # baut einmalig das Joern-Image + startet Backend + Gateway
```

## Architektur

```
Agent / Mensch
   │  typer CLI (--json)
   ▼
┌───────────────────────────────┐
│ Lumos-Gateway (Starlette 4243)│  tree-sitter: find/callers/callees/
│  MCP tools/call               │  impact/source/context (instant, polyglot)
└───────────────┬───────────────┘
                │  (lmc query / run_cpgql_query)
                ▼
┌───────────────────────────────┐
│ Joern-Backend (Docker, 8085)  │  echtes CPGQL / Data-Flow
│  Container lmc-joern          │  CPGs im Volume lmc-cpgs (<hash>.bin)
│  Image lmc-joern:latest       │  (docker/Dockerfile, offizielles Joern-Release)
└───────────────────────────────┘
```

`lmc up` startet beide; `lmc down` stoppt beide (Volume + CPGs bleiben erhalten).

## Schnellstart

```bash
lmc up                                   # Joern-Image bauen + Backend + Gateway starten
lmc init --auto --path . --json          # lumos.yml schreiben (Sprache erkennen)
lmc build --path . --json                # tree-sitter-Index + Joern-CPG (<hash>.bin)
lmc find "Order" --path . --json         # Methoden finden (instant)
lmc impact OrderController.store --path . --depth 3 --json   # Blast-Radius (instant)
lmc query 'cpg.method.name.l.mkString("\n")' --path . --json # echtes Joern-CPGQL
lmc check-diff --path . --json           # Precommit-Guardrail
lmc down                                 # Backend + Gateway stoppen
```

## CLI-Befehle

Globale Flags (für alle Befehle): `--url <gateway>` und `--hash <cpg>` (sonst
Auto-Auflösung aus `--path`). Für Agenten immer `--json`.

### Lifecycle
| Befehl | Zweck |
|---|---|
| `lmc up` | Joern-Image (einmalig) + Joern-Container (8085) + Gateway (4243) starten |
| `lmc down` | Beide stoppen (Volume/CPGs bleiben) |
| `lmc serve [--host] [--port]` | Gateway im Vordergrund (Debug) |

### Setup
| Befehl | Zweck |
|---|---|
| `lmc init --auto --path <w> --json` | Sprache erkennen + `lumos.yml` schreiben |
| `lmc build --path <w> [--scope sub] --json` | tree-sitter-Index + Joern-CPG bauen; `--scope` fuer Teilbaeume |
| `lmc status --path <w> --json` | Gateway- + Joern-Status + CPG-Frische |

### Navigation (tree-sitter = instant; `--engine joern` = genaue Joern-Antwort)
| Befehl | Zweck |
|---|---|
| `lmc find <pattern> --path <w> [--engine joern] --json` | Klassen/Methoden per Regex finden |
| `lmc callers <m> --path <w> [--engine joern] --json` | Wer ruft diese Methode auf? |
| `lmc callees <m> --path <w> [--engine joern] --json` | Was ruft diese Methode auf? |
| `lmc source <m> --path <w> [--engine joern] --json` | Quelltext + Datei:Zeile |
| `lmc context <m> --path <w> [--engine joern] --json` | Caller + Callee + Source gebündelt |
| `lmc methods-of <Class> --path <w> [--engine joern] --json` | Alle Methoden einer Klasse |
| `lmc callees-of-class <Class> --path <w> [--engine joern] --json` | Alle von einer Klasse aufgerufenen Methoden |
| `lmc impact <m> --path <w> --depth N [--engine joern] --json` | Blast-Radius (rekursiv) |

**Planungs-Disziplin:** Beim Planen/Refactoring zuerst `--engine joern` (große,
genaue Sicht, langsam), danach den Default tree-sitter für die schnellen
iterativen Checks beim Coden.

### Analyse / Guardrails
| Befehl | Zweck |
|---|---|
| `lmc check-diff --path <w> --json` | `git diff` auf CPG mappen (Precommit) |
| `lmc precommit --path <w> --json` | Alias für `check-diff` |

### Escape-Hatch (echtes Joern-CPGQL)
| Befehl | Zweck |
|---|---|
| `lmc query "<CPGQL>" --path <w> --json` | Rohe Joern/CPGQL-Abfrage gegen den CPG (Data-Flow/Taint möglich) |

### Agent-Guardrails
1. **Backend:** `lmc up` einmalig (baut Joern-Image, startet Container + Gateway).
2. **Kontext managen:** Neues Verzeichnis? Auf `lumos.yml` prüfen, sonst
   `lmc init --auto`. Bei Monorepos immer `--path` mitgeben.
3. **Vor Refactoring:** `lmc impact <Method> --json` und alle Depth-1-Aufrufer
   anpassen.
4. **Pre-Commit:** `lmc check-diff --json` — betroffene Methoden beheben.
5. **Cross-Boundary:** Frontend-Änderung mit HTTP-Call → Route extrahieren,
   `--path ./backend` wechseln, Backend-Controller per `lmc impact` prüfen.
6. **Frische-Disziplin:** Neue Dateien/Methoden → `lmc build --path .`.
7. **Data-Flow/Taint:** Für tiefe Analysen `lmc query` (Joern-CPGQL).

## Joern-Backend (Docker)

Eigenes Image `lmc-joern:latest` aus `docker/Dockerfile` (basiert auf
`eclipse-temurin:21-jdk` + offiziellem Joern-Release v4.0.548). Beim ersten
`lmc up` wird es automatisch gebaut (~einmalig, Download des Joern-Archivs).

- Container `lmc-joern` läuft mit `joern --server` (REST auf 8085).
- CPGs liegen im Docker-Volume `lmc-cpgs` als `<codebase_hash>.bin`.
- `lmc build` erzeugt sie per `joern-parse`; `lmc query` lädt sie per
  `importCpg` und führt CPGQL aus.

Manuell bauen (optional, vorab):
```bash
docker build -t lmc-joern:latest docker/
```

## Bibliotheks-API (ohne CLI)

```python
from lmc.server.graph import build_index
idx = build_index("hash", "php", "./src")          # tree-sitter
idx.impact("OrderController.save", 3)

from lmc.joern import run_cpgql, joern_parse        # Joern-Backend
joern_parse("./src", "hash")
run_cpgql("hash", 'cpg.method.name.l.mkString("\\n")')
```

Module: `lmc.server.graph` (Extractor/Index: find/callers/callees/source/context/impact/methods_of/callees_of_class), `lmc.server.store`,
`lmc.server.app` (Gateway), `lmc.server.lifecycle` (up/down),
`lmc.joern` (Joern-REST + parse + nav_*), `lmc.diff` (check_diff als Funktion),
`lmc.worktree` (State-Registry), `lmc.config` (lumos.yml/Spracherkennung).

## Paket bauen

```bash
uv build            # dist/lumos_code-0.2.0-py3-none-any.whl + .tar.gz
```

## Projektstruktur

```
lmc/
├── __init__.py
├── cli.py            # typer CLI (alle Befehle + globale Flags)
├── client.py         # LumosClient (httpx JSON-RPC an Gateway)
├── config.py         # lumos.yml + polyglote Sprach-Erkennung
├── joern.py          # Joern-REST-Client + joern-parse (Docker)
└── server/
    ├── __main__.py   # `python -m lmc.server` (uvicorn-Gateway)
    ├── app.py        # Starlette JSON-RPC-Gateway (tree-sitter Tools)
    ├── graph.py      # tree-sitter CPG-Extractor + Index/Queries
    ├── store.py      # in-memory Hash -> Index
    └── lifecycle.py  # up/down (Joern-Container + Gateway)
docker/Dockerfile     # eigenes Joern-Backend-Image (lmc-joern:latest)
pyproject.toml        # Hatchling-Build + Entry-Point `lmc`
uv.lock
SKILL.md              # Guardrail-Regeln für Coding-Agenten
```

## Lizenz

Siehe `LICENSE`.