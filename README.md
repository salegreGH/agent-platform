# Agent Platform v6 (Control Plane + Data Plane)

Plataforma local d'agents inspirada en Twin, orientada a conversa natural + workflows executables, amb separació de serveis, persistència i autoevolució governada per proposals.

## 1) Auditoria del repo actual

### Fortaleses detectades
- FastAPI funcional amb UI web i endpoints de control plane bàsics.
- `EvolverService` amb apply/rollback de proposals sobre workspace segur.
- Runtime amb `TaskPlanner` + `AntiLoopGuard` i connector MVP de Microsoft 365 Outlook.
- Persistència SQLite ja present (`kv`, `proposals`, `tasks`, `forms`, `loop_guard`).

### Buits detectats abans del refactor actual
- Faltaven models de domini forts (Run/Step/ActionCall/ConnectorConfig/Proposal).
- No hi havia persistència explícita de runs ni configuracions de connectors typed.
- Browser automation no tenia contracte de sessió/pause-resume orientat a login/2FA.
- L'estat del sistema no exposava sessions browser ni runs estructurats.

## 2) Estructura i models de dades implementats

### Models (`app/platform/models.py`)
- `Run`, `RunStep`: estat executable per run amb steps, dependències i sensibilitat de dades.
- `ActionCall`: contracte de tool-calling estructurat.
- `Proposal`: estat i metadades de desplegament/rollback.
- `ConnectorConfig`: configuració typed de connectors (auth, scopes, retries, cache).
- `BrowserSession`, `BrowserAction`: sessions browser amb trace i pause/resume.

### Persistència (`app/memory.py`)
Taules noves:
- `runs`
- `connector_configs`
- `browser_sessions`

Això amplia la base prèvia (`kv`, `proposals`, `tasks`, `forms`, `loop_guard`) i permet Data Plane observable.

## 3) Arquitectura de serveis

### Control Plane (sempre encès)
- `app/main.py` (UI + API)
- `app/platform/evolver.py`
- Governa proposals, formularis, uploads, estat global i rollback.

### Data Plane (reiniciable)
- `app/platform/core_runtime.py`
- Executa runs, planifica steps i persisteix estat de run.
- Exposa connectors i sessions browser via API `/core/*`.

### Worker Browser (MVP contract-first)
- `app/agents/browser_agent.py`
- Sessió/pause/resume implementats.
- Si falta runtime Playwright, retorna error controlat `BROWSER_WORKER_UNAVAILABLE` + pla de resolució (no stub silenciós).

## 4) Milestones coberts en aquest increment

- ✅ Milestone A: split operatiu control/data plane + workspace + logs + secrets.
- ✅ Milestone B: agent framework/runtime amb models de domini, runs, connector configs i anti-loop persistit.
- 🟡 Milestone C: Browser sessions + pause/resume + contractes d'acció; execució real Playwright pendent de worker dedicat.
- 🟡 Milestone D i següents: parcialment iniciats; pendent evolució completa de UX tabs Twin-level, pipeline auto-evolve complet i MVPs Jira/Clockify/Office.

## 5) API clau

- `GET /api/state` → agents, tasks, runs, forms, connectors, connector configs, browser sessions.
- `POST /api/forms/{form_id}/submit` → guarda formulari i normalitza `ConnectorConfig`.
- `POST /core/execute` → executa run i persisteix timeline de steps.
- `POST /core/browser/session` → crea sessió browser.
- `POST /core/browser/{session_id}/pause_login` → pausa per login/2FA.
- `POST /core/browser/{session_id}/resume` → reprèn sessió.
- `GET /core/browser/sessions` → llista sessions.

## 6) Tests

```bash
pytest -q
```

Inclou regressions per:
- workspace safety
- apply/rollback proposal
- core runtime request form
- models de domini i browser pause/resume amb errors controlats
