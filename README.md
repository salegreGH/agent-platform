# Agent Platform v4 (Local ChatGPT-like Orchestrator + Persistent Skills/Agents)

Aquesta v4 millora la UX i el comportament "agentic":
- UI moderna tipus "Chat" amb sidebar d'Agents/Skills i estat
- Orquestrador amb LLM (OpenAI Responses) per: planificar, decidir, preguntar, executar
- Connexió real a Outlook via Microsoft Graph (MSAL device code)
- Skills i agents PERSISTENTS (es guarden a `data/` i es carreguen en arrencar)
- Autoevolució controlada: quan falta una skill, el sistema genera un "Proposal" (YAML + tool stub) i tu l'aproves

## Instal·lació (Windows)
```powershell
cd "C:\path\to\agent-platform"
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
.\scripts\run.bat
```

UI: http://127.0.0.1:8787
