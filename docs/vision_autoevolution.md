# Visió 2026: Plataforma d'IA generalista autoevolutiva

Aquest document replanteja l'app per apropar-la a l'objectiu: **demanar qualsevol tasca** i que la plataforma la pugui executar de forma robusta, segura i escalable, incloent la capacitat de **crear nous GPTs/agents especialitzats** quan calgui.

## 1) Objectiu producte (north star)

> “Una plataforma d'agents que transforma objectius humans en resultats verificables, amb cost/control de risc acotat, i capacitat d'automillora governada.”

### KPI de producte (mesurables)
- **Task Success Rate (TSR)** per domini (email, calendari, devops, dades, codi, etc.).
- **Time to First Useful Result (TTFUR)**.
- **Intervencions humanes per tasca** (ha de baixar amb el temps).
- **Cost per tasca resolta** i pressupost per client.
- **Percentatge d'accions reversibles / auditables**.
- **Regressions introduïdes per autoevolució** (ha d'apropar-se a 0).

## 2) Principis d'arquitectura (imprescindibles)

1. **Orquestrador separat del runtime d'eines** (control plane vs execution plane).
2. **Planificació explícita i verificació explícita** (no només "prompt in, action out").
3. **Memòria multicapa**: sessió, episòdica, semàntica, i coneixement de codi.
4. **Policies first**: permisos, risc, secrets, PII i compliance abans de l'execució.
5. **Observabilitat total**: traces, decisions, costos, latència, diffs i evidència.
6. **Autoevolució governada**: generar millores sí, desplegar-les només amb gates.

## 3) Proposta de nova arquitectura

## 3.1 Control Plane (cervell)
- **Goal Interpreter**: transforma petició humana en objectiu operatiu + criteris d'èxit.
- **Planner**: crea un DAG de subtasques amb dependències i risc.
- **Policy Engine**: avalua permisos, dades sensibles i nivell d'autonomia admès.
- **Agent Registry**: catàleg d'agents existents (capacitats, versions, fiabilitat).
- **GPT/Agent Factory**: genera nous agents especialitzats i en valida qualitat.
- **Evaluator/Judge**: valida resultats amb tests, constraints i evidència.

## 3.2 Execution Plane (múscul)
- **Tool Runtime** (sandbox): executa connectors i codi temporal.
- **Connector Hub**: Outlook, Gmail, Slack, GitHub, Jira, DB, navegació web, RPA.
- **Job Queue**: reintents, timeouts, idempotència, rate limits.
- **State Store**: estat transaccional de workflows i checkpoints.

## 3.3 Knowledge Plane (memòria)
- **Knowledge Graph d'agents/eines** (qui sap fer què i amb quina qualitat).
- **Code Indexer** (repo map + embeddings + símbols + tests associats).
- **Memory Scoring** (decadència temporal + confiança + reutilització).

## 4) Sistema de "creació de GPTs" dins la plataforma

Per la teva idea (crear GPTs auxiliars), proposo 4 rols base:

1. **Orchestrator Assistant GPT**
   - Coneix tot el context del sistema (agents, skills, eines, versions, mètriques).
   - Ajuda a rutar tasques i detectar llacunes de capacitat.

2. **Skill Builder GPT**
   - Genera skill specs (`YAML`), tool stubs i tests mínims.
   - Proposa permisos mínims i fallback plans.

3. **Safety Reviewer GPT**
   - Revisa risc, dades sensibles, i accions irreversibles.
   - Pot bloquejar execució o requerir aprovació humana.

4. **Evaluator GPT**
   - Verifica resultats contra criteris objectius (tests, snapshots, assertions).
   - Puntua qualitat i alimenta el ranking d'agents.

### Contracte mínim d'un agent generat
- **Capability card**: input/output, eines que pot usar, límits, costos esperats.
- **Policies**: què pot fer autònomament i què requereix confirmació.
- **Test bundle**: happy path + edge cases + rollback.
- **Observability hooks**: logs estructurats i traces.

## 5) Full de ruta en 4 fases

## Fase A (0-6 setmanes): “Base fiable”
- Unificar model de tasca: `Goal -> Plan -> Execute -> Verify -> Learn`.
- Afegir **TaskSpec** formal (objectiu, constraints, budget, risc).
- Afegir **Policy Engine** amb nivells d'autonomia (A0..A3).
- Persistir traces i evidència de cada pas.

**Resultat esperat**: menys accions “màgiques”, més execució explicable.

## Fase B (6-12 setmanes): “Factory d'agents”
- Implementar `AgentFactoryService`.
- Pipeline: detectar gap -> proposar agent -> generar esquelet -> tests -> sandbox run.
- `Agent Registry` amb scoring (success, cost, latència, incidents).

**Resultat esperat**: la plataforma crea especialistes útils de forma semi-automàtica.

## Fase C (12-20 setmanes): “Autoevolució governada”
- Entrenar “selector de plans” basat en historial real.
- Afegir A/B testing d'agents i canary rollout.
- Introduir “self-reflection loops” amb topalls de cost i temps.

**Resultat esperat**: millora contínua sense degradar fiabilitat.

## Fase D (20+ setmanes): “Capacitat generalista”
- Multi-agent collaboration robusta (roles i handoffs).
- Entorns d'execució específics per domini (code, data, ops, office).
- Meta-learning sobre patrons de tasques freqüents.

**Resultat esperat**: augment substancial del TSR en tasques heterogènies.

## 6) Propostes i referents externs (què copiar/adaptar)

Aquestes línies de treball estan molt alineades amb el teu objectiu:

- **LangGraph / graph-based orchestration**: control explícit d'estats i cicles.
- **Microsoft AutoGen**: col·laboració multi-agent amb rols.
- **CrewAI**: especialització per rols i fluxos de treball cooperatius.
- **OpenDevin / OpenHands**: execució de tasques de codi en entorn agentic.
- **MetaGPT**: analogia d'equip d'enginyeria (PM/Architect/Engineer/QA).
- **BabyAGI / AutoGPT (aprendizatge històric)**: memòria + planificació iterativa.

### Aprenentatge clau d'aquests projectes
- Sense **governança i verificació**, l'autonomia no escala.
- El valor real és **workflow reliability**, no només “intel·ligència percebuda”.
- El millor patró és **orquestrador + especialistes + avaluador independent**.

## 7) Canvis tècnics concrets sobre l'app actual

1. **Nova capa `app/control_plane/`**
   - `goal_interpreter.py`, `planner.py`, `policy_engine.py`, `evaluator.py`.
2. **Nova capa `app/agent_factory/`**
   - `factory.py`, `templates/`, `validator.py`, `registry.py`.
3. **`TaskSpec` i `ExecutionReport`** a `app/state.py`.
4. **Traces estructurades** (`JSONL`) + IDs de correlació.
5. **Quality gates** abans d'activar un agent nou.
6. **Benchmark suite** de tasques representatives a `data/benchmarks/`.

## 8) Governança i seguretat

- **Autonomia gradual**:
  - A0: només suggeriments.
  - A1: execució de lectura.
  - A2: escriptura reversible.
  - A3: escriptura irreversible (sempre amb aprovació explícita).
- **Least privilege per tool**.
- **Red-team prompts** i tests d'abús periòdics.
- **Secrets vault** + rotació de credencials.

## 9) Definició d'èxit als pròxims 90 dies

- 3 dominis coberts end-to-end amb TSR > 70%.
- 1 pipeline funcional de creació d'agent (de proposal a deploy amb gates).
- 100% de tasques amb report auditable (`plan`, `actions`, `evidence`, `cost`).
- Reducció d'almenys 30% en intervencions manuals en tasques repetitives.

## 10) Recomanació pràctica immediata

Comença amb un **pilot vertical**:
1. Office automation (Outlook + Calendar + docs).
2. Crea 1 Orchestrator Assistant GPT + 1 Skill Builder GPT + 1 Evaluator GPT.
3. Mesura TSR/cost/risc cada setmana.
4. Itera sobre policies abans d'ampliar capacitats.

Aquest enfocament et dona tracció real cap a la visió ambiciosa, sense perdre control operatiu.
