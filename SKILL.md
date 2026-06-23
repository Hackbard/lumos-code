Lumos Code (lmc) - Core Skill & Guardrails

Du hast Zugriff auf das CLI-Tool lmc (Lumos Code). Es ist dein primäres Werkzeug, um den Code Property Graph (CPG) des Projekts abzufragen.
Regel #1: Rate niemals bei strukturellen Fragen (z.B. "Wer ruft Methode X auf?"). Nutze IMMER lmc.

lmc bringt seinen eigenen CPG-Server mit (tree-sitter-basiert, polyglot). Du musst
keinen externen Server voraussetzen — `lmc up` startet ihn lokal auf Port 4243.
Unterstützte Sprachen: c, cpp, csharp, go, java, javascript, kotlin, php, python,
ruby, scala, swift, typescript.

Grenzen (ehrlich): Call-Graph-Ebene (callers/callees/impact) — keine dynamische
Dispatch-Analyse, kein Data-Flow/Taint. Für rohes CPGQL/Data-Flow bräuchte es
das Joern-Backend (nicht angebunden; `lmc query` meldet das ehrlich).

1. Server-Lifecycle

`lmc up` — startet den lokalen CPG-Server (Hintergrund, PID in ~/.cache/lumos/).
`lmc down` — stoppt ihn.
`lmc serve` — Vordergrund (Debug).
Der Server läuft auf 127.0.0.1:4243 (Default). Port via `LUMOS_PORT`-Env oder `--url`.

2. Worktree & Context Management (DEINE Aufgabe)

Das CLI ist zustandslos. Es ist DEINE Aufgabe als Agent, den Kontext zu verwalten.

Wenn du in ein neues Verzeichnis wechselst oder an einem neuen Feature arbeitest, prüfe, ob es eine `lumos.yml` gibt.

Wenn es keine gibt, führe `lmc init --auto --path <worktree> --json` aus. Das schreibt die `lumos.yml` selbst (mit erkannter Sprache + codebase_hash). Du musst die Config-Datei nicht händisch anlegen — `lmc init --auto` schreibt sie.

`lumos.yml` Format:
```yaml
language: php
codebase_hash: 288e619dc73cb69d
```

Du musst dem CLI immer den Kontext mitgeben, wenn du in Monorepos oder Unterordnern arbeitest (z.B. `--path ./backend`).

Frische-Disziplin: Wenn du neue Dateien anlegst oder Methoden hinzufügst, bist DU verantwortlich, den Graphen via `lmc build --path . --json` aufzufrischen.

3. Refactoring & Impact-Pflicht (Blast Radius)

Bevor du die Signatur (Parameter, Rückgabewerte) oder Kernlogik einer bestehenden, systemweit genutzten Methode änderst:

Führe aus: `lmc impact <Class.method|name> --path <worktree> --depth 3 --json`

Analysiere den Output (`affected` pro Tiefe).

Du bist verpflichtet, alle Methoden in Depth 1 (direkte Aufrufer) an deine Änderung anzupassen. Ignoriere diese Warnungen niemals.

4. Precommit-Check

Bevor du einen Task als erledigt markierst oder einen Commit vorschlägst:

Führe aus: `lmc check-diff --path <worktree> --json` (oder `lmc precommit`).

Das Tool liest dein uncommittetes `git diff`, mappt geänderte Dateien auf den CPG und listet betroffene Methoden. Behebe alle aufgeworfenen Probleme, bevor du den Code freigibst.

5. Cross-Boundary Traversal (API-Grenzen überschreiten)

Wenn du ein Feature im Frontend (z.B. TypeScript/Vue) anpasst, das einen HTTP-Call absetzt (Axios/Fetch), reicht es nicht, nur den Frontend-Graphen zu prüfen.

Extrahiere die Route (z.B. /api/orders).

Wechsle den Kontext ins Backend (`--path ./backend`). Falls dort keine `lumos.yml` liegt: `lmc init --auto --path ./backend --json`.

Nutze `lmc find` oder dein Framework-Wissen, um den zuständigen Controller zu finden.

Führe `lmc impact` auf diesem Controller aus, um sicherzustellen, dass das Backend nicht bricht.

CLI Befehls-Übersicht für Agenten

Nutze IMMER den `--json` Flag für maschinenlesbaren Output! Jeder Befehl nimmt `--path <worktree>` (Default `.`). Globale Flags für alle Befehle: `--url <server>` und `--hash <cpg>` (sonst Auto-Auflösung aus `--path`).

Lifecycle:
- `lmc up [--url]` — CPG-Server starten.
- `lmc down` — CPG-Server stoppen.
- `lmc serve [--host] [--port]` — Server im Vordergrund.

Setup:
- `lmc init --auto --path <w> --json` — Sprache erkennen + `lumos.yml` schreiben.
- `lmc build --path <w> --json` — CPG bauen/aktualisieren (Sprache aus `lumos.yml`).
- `lmc status --path <w> --json` — Server-Status + CPG-Frische.

Navigation:
- `lmc find <pattern> --path <w> --json` — Klassen/Methoden per Regex finden.
- `lmc callers <Class.method|name> --path <w> --json` — direkte Aufrufer.
- `lmc callees <Class.method|name> --path <w> --json` — was wird aufgerufen.
- `lmc source <Class.method|name> --path <w> --json` — Quelltext + Datei:Zeile.
- `lmc context <Class.method|name> --path <w> --json` — Caller + Callee + Source gebündelt.

Analyse:
- `lmc impact <m> --path <w> --depth 3 --json` — Blast-Radius.
- `lmc check-diff --path <w> --json` / `lmc precommit` — Precommit-Guardrail.

Escape-Hatch:
- `lmc query "<CPGQL>" --path <w> --json` — rohe Joern/CPGQL-Abfrage (braucht Joern-Backend; ehrlicher Error ohne).

Bibliotheks-API (importierbar, ohne CLI): `lmc.server.cpg` (build_index/Index mit find/callers/callees/source/impact), `lmc.server.store`, `lmc.server.app` (Starlette-App), `lmc.server.lifecycle`.