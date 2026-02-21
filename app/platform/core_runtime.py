from __future__ import annotations

from datetime import timezone, datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from ..agents.browser_agent import BrowserAgent
from ..agents.m365_email_agent import M365EmailAgent
from ..memory import Memory
from .models import ConnectorConfig, Run, RunStep
from .registry import ToolRegistry
from .task_graph import AntiLoopGuard, TaskPlanner, graph_to_dict


class CoreRuntimeService:
    def __init__(self, memory: Memory, m365_agent: M365EmailAgent, tool_registry: ToolRegistry, browser_agent: BrowserAgent | None = None, recovery_manager=None):
        self.memory = memory
        self.m365_agent = m365_agent
        self.tool_registry = tool_registry
        self.browser_agent = browser_agent
        self.recovery_manager = recovery_manager
        self.planner = TaskPlanner()
        self.loop_guard = AntiLoopGuard(memory)

    def connectors_status(self) -> Dict[str, Any]:
        raw = self.memory.get_connector_config("m365_outlook")
        if raw:
            cfg = ConnectorConfig.model_validate(raw)
            return {"m365_outlook": {"configured": cfg.enabled and bool(cfg.settings.get("tenant_id") and cfg.settings.get("client_id")), "scopes": cfg.scopes or ["Mail.Read", "User.Read"], "auth_mode": cfg.auth_mode}}

        cfg = self.memory.get_json("m365.config") or {}
        ready = bool(cfg.get("tenant_id") and cfg.get("client_id"))
        normalized = ConnectorConfig(connector_id="m365_outlook", enabled=True, auth_mode=cfg.get("auth_mode") or "device_code", scopes=cfg.get("scopes") or ["Mail.Read", "User.Read"], settings=cfg)
        self.memory.upsert_connector_config("m365_outlook", normalized.model_dump(mode="json"))
        return {"m365_outlook": {"configured": ready, "scopes": normalized.scopes, "auth_mode": normalized.auth_mode}}

    def _new_run(self, goal: str, graph_payload: Dict[str, Any]) -> Run:
        run = Run(
            run_id=f"run-{uuid4().hex[:12]}",
            goal=goal,
            steps=[
                RunStep(id="validate_session", kind="browser", agent="browser", action="browser.outlook.validate_session"),
                RunStep(id="extract_latest_email", kind="browser", agent="browser", action="browser.outlook.extract_latest_email"),
            ],
            status="running",
            metadata={
                "graph": graph_payload,
                "task_state": "INIT",
                "flags": {"graph_not_viable": False},
                "strategy": None,
                "browser_session_id": None,
                "auth_status": "UNKNOWN",
                "current_step": None,
                "locale": "es",
                "messages": [],
            },
        )
        self._save_run(run)
        return run

    def _save_run(self, run: Run):
        run.updated_at = datetime.now(timezone.utc)
        self.memory.upsert_run(run.run_id, run.goal, run.status, run.model_dump(mode="json"))

    def _set_active_run(self, run_id: Optional[str]):
        self.memory.set_json("chat.active_run_id", run_id)

    def _get_active_run(self) -> Optional[Run]:
        run_id = self.memory.get_json("chat.active_run_id")
        payload = self.memory.get_run(run_id) if run_id else None
        return Run.model_validate(payload) if payload else None

    @staticmethod
    def _is_graph_unviable_intent(text: str) -> bool:
        t = (text or "").lower()
        return any(m in t for m in ["no es viable", "no puedo", "no tinc permisos", "no tengo permisos"])

    @staticmethod
    def _is_login_done_intent(text: str) -> bool:
        t = (text or "").lower()
        return any(m in t for m in ["ya hice login", "he fet login", "continuar", "done login", "listo"])


    def _human_reply(self, understood: str, doing: str, need: str, ctas: list[dict[str, str]]) -> Dict[str, Any]:
        return {
            "reply": f"Entendido: {understood}\n\nQué haré ahora: {doing}\n\nQué necesito de ti: {need}\n\nSiguiente paso: usa uno de los botones.",
            "actions": ctas,
        }

    def _remember_browser_preference(self):
        prefs = self.memory.get_json("memory.user_preferences") or {}
        prefs["outlook_strategy"] = "browser"
        self.memory.set_json("memory.user_preferences", prefs)

    def _mark_step(self, run: Run, step_id: str, status: str, output: Dict[str, Any] | None = None, error: Dict[str, Any] | None = None):
        now = datetime.now(timezone.utc)
        for step in run.steps:
            if step.id == step_id:
                step.status = status
                if status == "running" and not step.started_at:
                    step.started_at = now
                if status in {"completed", "failed", "blocked"}:
                    step.finished_at = now
                if output:
                    step.output_json = output
                    step.outputs = output
                if error:
                    step.error_json = error
                    step.error = error.get("message")
                self.memory.upsert_run_step(
                    step_id=f"{run.run_id}:{step_id}:{int(now.timestamp()*1000)}",
                    run_id=run.run_id,
                    status=status,
                    started_at=step.started_at.timestamp() if step.started_at else None,
                    finished_at=step.finished_at.timestamp() if step.finished_at else None,
                    output_json=step.output_json,
                    error_json=step.error_json,
                )
                break
        run.metadata["current_step"] = step_id

    def _classify_error(self, error_code: str) -> str:
        known = {"AUTH_REQUIRED", "NOT_READY", "SELECTOR_BROKE", "IFRAME_ISSUE", "NAVIGATION_FAIL", "TOOL_NOT_IMPLEMENTED", "BUG_CORE"}
        if error_code in known:
            return error_code
        tool_exists = bool(self.browser_agent and self.browser_agent.has_action("browser.outlook.extract_latest_email"))
        if not tool_exists:
            return "MISSING_CAPABILITY"
        return "BUG_CORE"

    def _ensure_browser_flow(self, run: Run) -> Dict[str, Any]:
        run.metadata["strategy"] = "browser"
        run.metadata.setdefault("flags", {})["graph_not_viable"] = True
        self._remember_browser_preference()
        if not self.browser_agent:
            run.status = "failed"
            run.metadata["task_state"] = "FAILED"
            self._save_run(run)
            return {"reply": "No he podido ejecutar navegador porque BrowserAgent no está disponible.", "run": run.model_dump(mode="json")}

        # reuse READY session to avoid repeating wizard
        session_id = run.metadata.get("browser_session_id")
        if session_id:
            session = self.browser_agent.get_session(session_id)
            if session.login_detected and session.status in {"ready", "running", "open"}:
                run.metadata["auth_status"] = "READY"
                run.metadata["task_state"] = "BROWSER_READY"
                self._save_run(run)
                out = self._run_browser_extract_step(run, session_id)
                out["wizard"] = {"show": True, "state": "DONE" if out.get("status") == "ok" else "ERROR", "session_id": session_id, "status_text": "Hecho" if out.get("status") == "ok" else "Error"}
                return out

        session = self.browser_agent.start_session("https://outlook.office.com/mail/")
        paused = self.browser_agent.pause_for_user_login(session.session_id, reason="Esperando login en Outlook Web")
        run.metadata["browser_session_id"] = paused.session_id
        run.metadata["task_state"] = "WAITING_HUMAN_LOGIN"
        run.metadata["auth_status"] = "AUTH_REQUIRED"
        self._save_run(run)
        return {
            "reply": "Cambio automáticamente a la vía navegador. Necesito tu ayuda: abre navegador y completa login en Outlook.",
            "actions": [{"id": "open_browser", "label": "Abrir navegador", "kind": "open_browser"}, {"id": "done_login", "label": "Ya hice login", "kind": "mark_login_done"}],
            "run": run.model_dump(mode="json"),
            "wizard": {"show": True, "state": "BROWSER_WAITING_FOR_LOGIN", "session_id": paused.session_id, "status_text": "Esperando login"},
        }

    def _run_browser_extract_step(self, run: Run, session_id: str) -> Dict[str, Any]:
        run.status = "running"
        run.metadata["task_state"] = "EXTRACTING"
        self._mark_step(run, "extract_latest_email", "running")
        self._save_run(run)

        html = run.metadata.get("browser_inbox_html")
        result = self.browser_agent.extract_latest_email_outlook_web(session_id, html=html)
        if result.get("status") == "ok":
            self._mark_step(run, "extract_latest_email", "completed", output=result)
            run.metadata["task_state"] = "DONE"
            run.metadata["auth_status"] = "READY"
            run.metadata["result"] = {"status": "ok", "strategy": "browser", "email": result["email"]}
            run.status = "completed"
            self._set_active_run(None)
            self._save_run(run)
            return {"status": "ok", "reply": "Extracción completada.", "run": run.model_dump(mode="json"), "result": run.metadata["result"]}

        classification = self._classify_error(result.get("error_code", "BUG_CORE"))
        self._mark_step(run, "extract_latest_email", "failed", error={"classification": classification, **result})
        run.metadata["task_state"] = "FAILED"
        run.metadata["triage"] = {"classification": classification, "error_code": result.get("error_code"), "raw": result}
        run.status = "failed"
        self._save_run(run)
        return {"status": "error", "reply": f"No he podido ejecutar extracción porque {classification}.", "run": run.model_dump(mode="json"), "result": result}

    def _continue_browser_after_login(self, run: Run) -> Dict[str, Any]:
        session_id = run.metadata.get("browser_session_id")
        if not session_id or not self.browser_agent:
            return {"reply": "No he podido ejecutar validación de sesión porque no hay browser_session_id.", "run": run.model_dump(mode="json")}

        self._mark_step(run, "validate_session", "running")
        session = self.browser_agent.mark_login_done(session_id)
        run.metadata["auth_status"] = "READY" if session.login_detected else "AUTH_REQUIRED"
        run.metadata["task_state"] = "BROWSER_READY" if session.login_detected else "WAITING_HUMAN_LOGIN"
        self._mark_step(run, "validate_session", "completed", output={"login_detected": session.login_detected, "session_id": session_id})
        self._save_run(run)

        if not session.login_detected:
            return {"reply": "No he podido validar Inbox. Vuelve a intentar login.", "run": run.model_dump(mode="json")}
        out = self._run_browser_extract_step(run, session_id)
        out["wizard"] = {"show": True, "state": "DONE" if out.get("status") == "ok" else "ERROR", "session_id": session_id, "status_text": "Hecho" if out.get("status") == "ok" else "Error"}
        return out

    def retry_run(self, run_id: str) -> Dict[str, Any]:
        payload = self.memory.get_run(run_id)
        if not payload:
            return {"ok": False, "error": "run_not_found"}
        run = Run.model_validate(payload)
        session_id = run.metadata.get("browser_session_id")
        if not session_id:
            return {"ok": False, "error": "browser_session_not_found"}

        self._mark_step(run, "extract_latest_email", "running")
        self._save_run(run)

        if not self.recovery_manager:
            out = self._run_browser_extract_step(run, session_id)
            out["wizard"] = {"show": True, "state": "DONE" if out.get("status") == "ok" else "ERROR", "session_id": session_id, "status_text": "Hecho" if out.get("status") == "ok" else "Error"}
            return out

        failure_result = (run.metadata.get("triage") or {}).get("raw") or {}
        recovery = self.recovery_manager.retry(
            run=run.model_dump(mode="json"),
            failure_result=failure_result,
            session=self.browser_agent.get_session(session_id).model_dump(mode="json") if self.browser_agent else None,
            retry_callback=lambda: self._run_browser_extract_step(run, session_id),
        )
        updated_payload = self.memory.get_run(run_id)
        updated_run = Run.model_validate(updated_payload) if updated_payload else run
        updated_run.metadata["recovery"] = {"timeline": recovery.get("timeline", []), "evidence": recovery.get("evidence", {}), "attempts": recovery.get("attempts", 0), "status": recovery.get("status")}
        self._save_run(updated_run)
        return {"status": "ok" if recovery.get("status") == "recovered" else "error", "reply": "\n".join(recovery.get("timeline", [])), "run": updated_run.model_dump(mode="json"), "result": updated_run.metadata.get("result")}

    def get_run_state(self, run_id: str) -> Dict[str, Any]:
        payload = self.memory.get_run(run_id)
        if not payload:
            return {"ok": False, "error": "run_not_found"}
        run = Run.model_validate(payload)
        return {"ok": True, "run": run.model_dump(mode="json"), "task_state": run.metadata.get("task_state")}

    def start_browser_session(self, run_id: str | None = None, start_url: str | None = None) -> Dict[str, Any]:
        if not self.browser_agent:
            return {"ok": False, "error_code": "TOOL_NOT_IMPLEMENTED", "message": "Browser agent is disabled."}
        session = self.browser_agent.start_session(start_url or "https://outlook.office.com/mail/")
        paused = self.browser_agent.pause_for_user_login(session.session_id, reason="Esperando login en Outlook Web")
        if run_id:
            payload = self.memory.get_run(run_id)
            if payload:
                run = Run.model_validate(payload)
                run.metadata["browser_session_id"] = paused.session_id
                run.metadata["task_state"] = "WAITING_HUMAN_LOGIN"
                run.metadata["auth_status"] = "AUTH_REQUIRED"
                self._save_run(run)
        return {"ok": True, "session": paused.model_dump(mode="json")}

    def mark_login_done(self, run_id: str) -> Dict[str, Any]:
        payload = self.memory.get_run(run_id)
        if not payload:
            return {"ok": False, "error": "run_not_found"}
        return self._continue_browser_after_login(Run.model_validate(payload))

    def pause_browser_for_login(self, session_id: str) -> Dict[str, Any]:
        session = self.browser_agent.pause_for_user_login(session_id)
        return {"ok": True, "session": session.model_dump(mode="json")}

    def resume_browser_session(self, session_id: str) -> Dict[str, Any]:
        session = self.browser_agent.resume(session_id)
        return {"ok": True, "session": session.model_dump(mode="json")}

    def browser_sessions(self) -> Dict[str, Any]:
        return {"sessions": self.memory.list_browser_sessions()}

    def converse(self, user_text: str) -> Dict[str, Any]:
        run = self._get_active_run()
        if not run or run.metadata.get("task_state") in {"DONE", "FAILED"}:
            status = self.connectors_status()
            graph = self.planner.plan(goal=user_text, connector_ready=status["m365_outlook"]["configured"])
            run = self._new_run(user_text, graph_to_dict(graph))
            self._set_active_run(run.run_id)
            if not status["m365_outlook"]["configured"]:
                run.status = "blocked"
                run.metadata["task_state"] = "FAILED"
                self._save_run(run)
                self._set_active_run(None)
                return {"reply": "Necesito configurar Outlook antes de continuar.", "run": run.model_dump(mode="json"), "graph": run.metadata.get("graph"), "result": {"status": "needs_form", "fields": self.m365_agent.config_questions()}}

        if self._is_login_done_intent(user_text):
            return self._continue_browser_after_login(run)

        if run.metadata.get("task_state") == "WAITING_HUMAN_LOGIN" and not self._is_login_done_intent(user_text):
            return {
                "reply": "Intenté extraer el email, pero no he podido ejecutar la extracción porque falta login válido en Inbox.",
                "actions": [{"id": "open_browser", "label": "Abrir navegador", "kind": "open_browser"}, {"id": "done_login", "label": "Ya hice login", "kind": "mark_login_done"}],
                "run": run.model_dump(mode="json"),
                "wizard": {"show": True, "state": "BROWSER_WAITING_FOR_LOGIN", "session_id": run.metadata.get("browser_session_id"), "status_text": "Esperando login"},
            }
        if self._is_graph_unviable_intent(user_text):
            return self._ensure_browser_flow(run)

        prefs = self.memory.get_json("memory.user_preferences") or {}
        if prefs.get("outlook_strategy") == "browser" or run.metadata.get("auth_status") == "READY":
            return self._ensure_browser_flow(run)

        run.metadata["strategy"] = "graph"
        run.metadata["task_state"] = "EXTRACTING"
        result = self.m365_agent.get_last_email()
        run.metadata["last_result"] = result
        if result.get("status") == "auth_required":
            run.metadata["task_state"] = "GRAPH_AUTH"
            run.status = "blocked"
            self._save_run(run)
            return {
                **self._human_reply(
                    "Quieres el último email de Outlook.",
                    "Primero intento Graph porque está configurado.",
                    "Completa login de Microsoft o cambia a navegador.",
                    [
                        {"id": "open_ms", "label": "Abrir web de Microsoft", "kind": "open_device_login", "url": "https://microsoft.com/devicelogin"},
                        {"id": "switch_browser", "label": "Cambiar a navegador", "kind": "switch_browser"},
                    ],
                ),
                "run": run.model_dump(mode="json"),
            }

        run.metadata["task_state"] = "DONE" if result.get("status") == "ok" else "FAILED"
        run.status = "completed" if result.get("status") == "ok" else "failed"
        self._set_active_run(None)
        self._save_run(run)
        return {"reply": "Listo." if result.get("status") == "ok" else "No he podido completar la consulta.", "run": run.model_dump(mode="json"), "result": result}

    def execute(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self.converse(request.get("message", ""))
