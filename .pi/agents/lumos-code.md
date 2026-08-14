---
name: lumos-code
description: Polyglot CPG-Stack (Joern + tree-sitter) für lokales Live-Coding & Agent-Guardrails. Default-Verhalten für dieses Repo.
---

# Verhaltensregeln für /Users/klein/workspace/_private/lumos_code

## Release-Befehle sind bindend

Wenn der User einen Release auslöst (egal ob explizit „releasen", „publish", „Tag und Push", „auf GitHub", „auf PyPI", oder einfach durch Aufzählen der Schritte), **führe die gesamte Kette in einem Durchgang aus**:

1. `git add` (nur die tatsächlich geänderten release-relevanten Files — nicht `.DS_Store`, nicht `.pi/`, keine Build-Artefakte)
2. `git commit` mit aussagekräftiger Message
3. `git tag -a v<MAJOR>.<MINOR>.<PATCH> -m "v<...>"`
4. `git push origin main && git push origin v<...>`
5. PyPI: `yes | uv publish dist/lumos_code-*.{whl,tar.gz}` (das `yes |` ist Pflicht — uv hat hier kein `--yes` und fragt sonst interaktiv nach)
6. GitHub: `gh release create v<...> dist/lumos_code-*.{whl,tar.gz} --title ... --notes ... --target main`

**Keine Rückfragen** zu: „soll ich?", „commit Message ok?", „Tag-Name korrekt?", „PyPI wirklich?". Der User hat mit dem Release-Befehl implizit all das abgenickt.

**Erlaubte Rückfragen nur bei**: harten Fehlern (Credential fehlt komplett, Branch Protection blockt Push, 401/403, Build brach ab). Dann: **Fehler melden + Stopp**, nicht weiter raten.

## Ponytail-Mode

Im Ponytail-Mode (aktiv per Default hier, level=ultra): bevorzuge die kürzeste existierende Lösung. Keine Flags, kein Scaffolding, keine Helper-Klassen.

## Build-Befehle

- Wheel + sdist: `uv build` (legt nach `dist/`)
- Docker-Image: `docker build -t lmc-joern:latest docker/`
- Self-Check tree-sitter migration: `.venv/bin/python -m lmc.server.graph` (muss mit „graph.py self-check OK" enden)

## Git-Hygiene

- Niemals `git add .` — immer explizit nennen
- `.DS_Store`, `.pi/`, `dist/` (außer bei Release-Artefakten) sind tabu
