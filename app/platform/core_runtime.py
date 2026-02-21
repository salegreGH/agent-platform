from __future__ import annotations

from datetime import timezone, datetime
from typing import Any, Dict
from uuid import uuid4

from ..agents.browser_agent import BrowserAgent
from ..agents.m365_email_agent import M365EmailAgent
from ..memory import Memory
from .models import ConnectorConfig, Run, RunStep
from .registry import ToolRegistry
from .task_graph import AntiLoopGuard, TaskPlanner, graph_to_dict


class CoreRuntimeService:
    def __init__(self, memory: Memory, m365_agent: M365EmailAgent, tool_registry: ToolRegistry, browser_agent: BrowserAgent | None = None):
        self.memory = memory
        self.m365_agent = m365_agent
        self.tool_registry = tool_registry
        self.browser_agent = browser_agent
        self.planner = TaskPlanner()
        self.loop_guard = AntiLoopGuard(memory)

    def connectors_status(self) -> Dict[str, Any]:
        raw = self.memory.get_connector_config("m365_outlook")
        if raw:
            cfg = ConnectorConfig.model_validate(raw)
            return {
                "m365_outlook": {
                    "configured": cfg.enabled and bool(cfg.settings.get("tenant_id") and cfg.settings.get("client_id")),
                    "scopes": cfg.scopes or ["Mail.Read", "User.Read"],
                    "auth_mode": cfg.auth_mode,
                }
            }

        cfg = self.memory.get_json("m365.config") or {}
        ready = bool(cfg.get("tenant_id") and cfg.get("client_id"))
        normalized = ConnectorConfig(
            connector_id="m365_outlook",
            enabled=True,
            auth_mode=cfg.get("auth_mode") or "device_code",
            scopes=cfg.get("scopes") or ["Mail.Read", "User.Read"],
            settings=cfg,
        )
        self.memory.upsert_connector_config("m365_outlook", normalized.model_dump(mode="json"))
        return {
            "m365_outlook": {
                "configured": ready,
                "scopes": normalized.scopes,
                "auth_mode": normalized.auth_mode,
            }
        }

    def _new_run(self, goal: str, graph_payload: Dict[str, Any]) -> Run:
        steps = [
            RunStep(
                id=n["id"],
                agent=n["agent_id"],
                action=n["action"],
                dependencies=n.get("depends_on") or [],
                status="pending",
            )
            for n in graph_payload.get("nodes", [])
        ]
        run = Run(run_id=f"run-{uuid4().hex[:12]}", goal=goal, steps=steps, status="running", metadata={"graph": graph_payload})
        self.memory.upsert_run(run.run_id, goal, run.status, run.model_dump(mode="json"))
        return run

    def _save_run(self, run: Run):
        run.updated_at = datetime.now(timezone.utc)
        self.memory.upsert_run(run.run_id, run.goal, run.status, run.model_dump(mode="json"))

    def execute(self, request: Dict[str, Any]) -> Dict[str, Any]:
        user_text = request.get("message", "")
        status = self.connectors_status()
        graph = self.planner.plan(goal=user_text, connector_ready=status["m365_outlook"]["configured"])
        graph_payload = graph_to_dict(graph)
        run = self._new_run(user_text, graph_payload)
        payload: Dict[str, Any] = {"graph": graph_payload, "result": None, "run": run.model_dump(mode="json")}

        if not status["m365_outlook"]["configured"]:
            run.status = "blocked"
            for step in run.steps:
                if step.id == "form":
                    step.status = "blocked"
                    step.outputs = {
                        "status": "needs_form",
                        "form_type": "m365_config",
                    }
            payload["result"] = {
                "status": "needs_form",
                "form_type": "m365_config",
                "fields": self.m365_agent.config_questions(),
            }
            self._save_run(run)
            payload["run"] = run.model_dump(mode="json")
            self.memory.save_task(graph.task_id, user_text, "blocked", payload)
            return payload

        if "important" in user_text.lower() and ("respond" in user_text.lower() or "sense" in user_text.lower()):
            result = self.m365_agent.triage_important_unanswered()
        else:
            result = self.m365_agent.get_last_email()

        payload["result"] = result
        loop = self.loop_guard.guard("core_execute", {"goal": user_text, "result": result.get("status")})
        payload["loop_guard"] = loop

        run.status = "completed" if result.get("status") == "ok" else "failed"
        for step in run.steps:
            step.status = "completed" if step.id in {"intake", "plan"} else step.status
            if step.id == "exec":
                step.status = "completed" if result.get("status") == "ok" else "failed"
                step.outputs = result
            if step.id == "validate":
                step.status = "blocked" if loop.get("blocked") else "completed"
                step.outputs = loop

        self._save_run(run)
        payload["run"] = run.model_dump(mode="json")
        self.memory.save_task(graph.task_id, user_text, "completed" if result.get("status") == "ok" else "failed", payload)
        return payload

    def start_browser_session(self, start_url: str | None = None) -> Dict[str, Any]:
        if not self.browser_agent:
            return {
                "ok": False,
                "error_code": "BROWSER_AGENT_DISABLED",
                "message": "Browser agent is disabled. Create an evolve proposal to enable worker runtime.",
            }
        session = self.browser_agent.start_session(start_url)
        return {"ok": True, "session": session.model_dump(mode="json")}

    def pause_browser_for_login(self, session_id: str) -> Dict[str, Any]:
        if not self.browser_agent:
            return {"ok": False, "error_code": "BROWSER_AGENT_DISABLED", "message": "Browser agent is disabled."}
        session = self.browser_agent.pause_for_user_login(session_id)
        return {"ok": True, "session": session.model_dump(mode="json")}

    def resume_browser_session(self, session_id: str) -> Dict[str, Any]:
        if not self.browser_agent:
            return {"ok": False, "error_code": "BROWSER_AGENT_DISABLED", "message": "Browser agent is disabled."}
        session = self.browser_agent.resume(session_id)
        return {"ok": True, "session": session.model_dump(mode="json")}

    def browser_sessions(self) -> Dict[str, Any]:
        return {"sessions": self.memory.list_browser_sessions()}

    def suggest_outlook_fallback(self, goal: str) -> Dict[str, Any]:
        if not self.browser_agent:
            return {
                "status": "fallback_unavailable",
                "message": "No puc executar fallback de navegador perquè el BrowserAgent no està actiu.",
                "alternatives": [
                    "Activar BrowserAgent/worker Playwright via proposta Evolve",
                    "Completar autorització device-code de Microsoft Graph",
                    "Pujar un fitxer .eml/.msg perquè pugui extreure el contingut localment",
                ],
            }

        session = self.browser_agent.start_session("https://outlook.office.com/mail/")
        paused = self.browser_agent.pause_for_user_login(
            session.session_id,
            reason="Login manual requerit a Outlook Web per executar fallback browser.",
        )
        return {
            "status": "fallback_started",
            "strategy": "browser_outlook",
            "message": "He preparat una sessió de navegador com a alternativa a Graph API.",
            "session_id": paused.session_id,
            "pause_reason": paused.pause_reason,
            "next_steps": [
                "Obre la pestanya Browser i completa login/2FA manualment",
                "Prem Continue/Resume a la sessió",
                "Reexecuta la consulta per obtenir l'últim email",
            ],
        }
