# Agent Platform v5 (platform-first)

Plataforma agèntica local amb **Control Plane (Evolver)** + **Core Runtime reiniciable**, orientada a automatització corporativa i autoevolució segura.

## 1) Auditoria ràpida (abans vs ara)

### Què hi havia
- FastAPI monolític amb `chat/state/proposals` bàsics.
- Agent M365 Outlook parcial (últim email + triatge simple).
- Proposals simples al workspace.
- UI amb pestanyes bàsiques (agents/skills/proposals/logs).

### Què faltava
- Split clar Evolver/Core.
- Contractes d’agents, task graph estructurat, registries de tools/agents.
- Política de seguretat centralitzada (allowed paths/actions).
- Forms/uploads com a flux oficial per dades mancants.
- Pipeline release/rollback gestionat pel control plane.

### Què s’ha implementat en aquest refactor
- Milestone A-B: workspace ampliat + policies + registries + task graph + anti-loop.
- Milestone C-D: proposta/apply/rollback MVP + UI moderna amb tabs extenses, forms i uploads.
- MVP Outlook E2E: formulari de configuració, auth device-code, fetch de correu, triatge d’importants.

## 2) Arquitectura definitiva de carpetes

```text
app/
  main.py                     # Evolver API + proxy Core API
  orchestrator.py             # OrchestratorAgent (classify/delegate/evolve)
  memory.py                   # persistència (kv, proposals, tasks, forms, loop_guard)
  agents/
    m365_email_agent.py       # Connector Outlook MVP
  platform/
    contracts.py              # contractes d'agents, task graph, tool calls
    registry.py               # agent registry + tool registry
    policy.py                 # PolicyEngine + SecurityPolicyAgent
    task_graph.py             # planner + anti-loop guard
    core_runtime.py           # Core Runtime Service (/core/*)
    evolver.py                # Evolver service (proposals/apply/rollback)
  core/
    paths.py                  # workspace root + subpaths segur
    logging.py
ui/
  index.html
  app.js                      # chat + tabs + forms + uploads + proposals
tests/
  test_workspace_paths.py
  test_proposal_apply.py
  test_core_runtime.py
```

## 3) Serveis

### Evolver Service (control plane)
- Endpoints: `/api/state`, `/api/chat`, `/api/proposals/approve`, `/api/evolve/rollback`, `/api/forms/*`, `/api/uploads`.
- Responsable de proposals i release controlat.

### Core Runtime Service (reiniciable)
- Endpoints: `/core/execute`, `/core/tools`, `/core/connectors`, `/core/memory`, `/core/health`.
- Responsable d’execució de task graph i connectors.

## 4) Workspace writable

Per defecte a Windows: `%LOCALAPPDATA%/AgentPlatform/`.

```text
AgentPlatform/
  workspace/
    generated_skills/
    generated_tools/
  logs/
  cache/
  secrets/
  memory.db
  attachments/
  msal_cache/
  proposals/
  artifacts/
```

## 5) One-click run

```powershell
cd "C:\path\to\agent-platform"
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
.\scripts\run.bat
```

UI: `http://127.0.0.1:8787`

## 6) Tests

```bash
pytest -q
```
