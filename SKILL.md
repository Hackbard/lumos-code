Lumos Code (lmc) - Core Skill & Guardrails

Du hast Zugriff auf das CLI-Tool lmc (Lumos Code). Es ist dein primäres Werkzeug, um den Code Property Graph (CPG) des Projekts abzufragen.
Regel #1: Rate niemals bei strukturellen Fragen (z.B. "Wer ruft Methode X auf?"). Nutze IMMER lmc.

1. Worktree & Context Management (DEINE Aufgabe)

Das CLI ist zustandslos. Es ist DEINE Aufgabe als Agent, den Kontext zu verwalten.

Wenn du in ein neues Verzeichnis wechselst oder an einem neuen Feature arbeitest, prüfe, ob es eine lumos.yml gibt.

Wenn es keine gibt, führe lmc init --auto aus.

Du musst dem CLI immer den Kontext mitgeben, wenn du in Monorepos oder Unterordnern arbeitest (z.B. --path ./backend).

Frische-Disziplin: Wenn du neue Dateien anlegst oder Methoden hinzufügst, bist DU verantwortlich, den Graphen via lmc build --path . aufzufrischen.

2. Refactoring & Impact-Pflicht (Blast Radius)

Bevor du die Signatur (Parameter, Rückgabewerte) oder Kernlogik einer bestehenden, systemweit genutzten Methode änderst:

Führe aus: lmc impact <Vollständiger.MethodenName> --json

Analysiere den Output ("Blast Radius").

Du bist verpflichtet, alle Methoden in Depth 1 (direkte Aufrufer) an deine Änderung anzupassen. Ignoriere diese Warnungen niemals.

3. Precommit-Check

Bevor du einen Task als erledigt markierst oder einen Commit vorschlägst:

Führe aus: lmc check-diff --json

Das Tool mappt deine uncommitteten Änderungen auf den Graphen und zeigt architektonische Warnungen.

Behebe alle aufgeworfenen Probleme, bevor du den Code freigibst.

4. Cross-Boundary Traversal (API-Grenzen überschreiten)

Wenn du ein Feature im Frontend (z.B. TypeScript/Vue) anpasst, das einen HTTP-Call absetzt (Axios/Fetch), reicht es nicht, nur den Frontend-Graphen zu prüfen.

Extrahiere die Route (z.B. /api/orders).

Wechsle den Kontext ins Backend (--path ./backend).

Nutze lmc find oder dein Framework-Wissen, um den zuständigen Controller zu finden.

Führe lmc impact auf diesem Controller aus, um sicherzustellen, dass das Backend nicht bricht.

CLI Befehls-Übersicht für Agenten

Nutze IMMER den --json Flag für maschinenlesbaren Output!

lmc build --json -> Baut/Aktualisiert den Graphen.

lmc callers <method> --json -> Listet direkte Aufrufer.

lmc context <symbol> --json -> Liefert Caller, Callee und Quelltext.

lmc impact <method> --depth=3 --json -> Rekursive Warnungen.

lmc check-diff --json -> Prüft lokales Git-Diff auf CPG-Brüche.
