# Agent Platform v4

Plataforma agentica local amb FastAPI + UI web, autoevolució controlada i workspace segur per evitar errors de permisos.

## Arquitectura (MVP actual)

```text
┌──────────────┐        HTTP         ┌────────────────────┐
│ Browser UI   │ ─────────────────▶ │ Core API (FastAPI) │
│ Chat/Skills/ │                    │ app/main.py         │
│ Proposals    │ ◀───────────────── │                     │
└──────────────┘      JSON/NL        └─────────┬──────────┘
                                                │
                                  ┌─────────────▼─────────────┐
                                  │ Orchestrator              │
                                  │ app/orchestrator.py       │
                                  │ - planning i execució     │
                                  │ - proposals + apply       │
                                  │ - anti-loop guard         │
                                  └───────┬─────────┬─────────┘
                                          │         │
                                ┌─────────▼───┐ ┌──▼──────────────┐
                                │ M365 Agent  │ │ Generated tools │
                                │ device-code │ │ execute_tool()  │
                                └─────────────┘ └─────────────────┘

Workspace writable únic:
%LOCALAPPDATA%\AgentPlatform\workspace\
  - generated_skills/
  - generated_tools/
  - logs/
  - cache/
  - msal_cache/
  - memory.db
```

## Canvi crític de permisos

Ara **cap proposal ni skill generada s'escriu dins del repo**. Tot es desa al workspace d'usuari resolt per `WorkspacePaths` (`app/core/paths.py`).

Si un patch intenta sortir del workspace (`../` o ruta absoluta fora), es bloqueja amb error clar i registre al log. Això evita el loop de `Permission denied`.

## Arrencada 1-click (Windows)

```powershell
cd "C:\path\to\agent-platform"
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
.\scripts\run.bat
```

UI: `http://127.0.0.1:8787`

## Ports

- Core API/UI: `8787` (configurable amb `AGENT_PLATFORM_PORT`)

## Troubleshooting

- **No guarda proposals/tools:** revisa `GET /api/logs` o el fitxer `...\workspace\logs\agent-platform.log`.
- **Outlook demana auth:** és esperat la primera vegada; segueix el missatge de device-code i torna a provar.
- **Bucle de proposta repetida:** ara es talla automàticament amb anti-loop guard i es marca com a triatge.

## Tests

```bash
pytest -q
```

Inclou tests de path safety i apply de proposals dins workspace.
