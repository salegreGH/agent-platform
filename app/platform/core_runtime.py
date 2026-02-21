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
    RUN_STATES = {
        "INIT",
        "CHOOSE_STRATEGY",
        "NEED_AUTH_GRAPH",
        "GRAPH_NOT_VIABLE",
        "START_BROWSER_SESSION",
        "BROWSER_WAITING_FOR_LOGIN",
        "BROWSER_READY",
        "RUNNING",
        "DONE",
        "FAILED",
    }

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
        run = Run(
            run_id=f"run-{uuid4().hex[:12]}",
            goal=goal,
            steps=steps,
            status="running",
            metadata={
                "graph": graph_payload,
                "task_state": "INIT",
                "flags": {"graph_not_viable": False},
                "strategy": None,
                "browser_session_id": None,
                "locale": "es",
                "messages": [],
            },
        )
        self.memory.upsert_run(run.run_id, goal, run.status, run.model_dump(mode="json"))
        return run

    def _save_run(self, run: Run):
        run.updated_at = datetime.now(timezone.utc)
        self.memory.upsert_run(run.run_id, run.goal, run.status, run.model_dump(mode="json"))

    def _get_active_run(self) -> Optional[Run]:
        run_id = self.memory.get_json("chat.active_run_id")
        if not run_id:
            return None
        payload = self.memory.get_run(run_id)
        if not payload:
            return None
        return Run.model_validate(payload)

    def _set_active_run(self, run_id: Optional[str]):
        self.memory.set_json("chat.active_run_id", run_id)

    @staticmethod
    def _detect_locale(text: str) -> str:
        t = (text or "").lower()
        if any(k in t for k in ["dame", "ultimo", "puedo", "permisos", "correo"]):
            return "es"
        if any(k in t for k in ["últim", "correu", "permisos", "puc"]):
            return "ca"
        return "es"

    @staticmethod
    def _is_graph_unviable_intent(text: str) -> bool:
        t = (text or "").lower()
        markers = ["no es viable", "no és viable", "no puc", "no puedo", "no tinc permisos", "no tengo permisos", "no soc admin", "no soy admin"]
        return any(m in t for m in markers)

    @staticmethod
    def _is_login_done_intent(text: str) -> bool:
        t = (text or "").lower()
        markers = ["he fet login", "ya hice login", "listo", "continua", "continuar", "done login"]
        return any(m in t for m in markers)

    def _remember_browser_preference(self):
        prefs = self.memory.get_json("memory.user_preferences") or {}
        prefs["outlook_strategy"] = "browser"
        self.memory.set_json("memory.user_preferences", prefs)

    def _append_message(self, run: Run, msg: str):
        run.metadata.setdefault("messages", []).append(msg)

    def _human_reply(self, locale: str, understood: str, doing: str, need: str, ctas: list[dict[str, str]]) -> Dict[str, Any]:
        label_next = "Siguiente paso" if locale == "es" else "Proper pas"
        return {
            "reply": f"Entendido: {understood}\n\nQué haré ahora: {doing}\n\nQué necesito de ti: {need}\n\n{label_next}: usa uno de los botones.",
            "actions": ctas,
        }

    def _ensure_browser_flow(self, run: Run, user_text: str) -> Dict[str, Any]:
        run.metadata["task_state"] = "START_BROWSER_SESSION"
        run.metadata["strategy"] = "browser"
        run.metadata.setdefault("flags", {})["graph_not_viable"] = True
        self._remember_browser_preference()

        if not self.browser_agent:
            run.metadata["task_state"] = "FAILED"
            run.status = "failed"
            self._save_run(run)
            return {"reply": "No puedo abrir navegador porque BrowserAgent está desactivado.", "run": run.model_dump(mode="json")}

        session = self.browser_agent.start_session("https://outlook.office.com/mail/")
        paused = self.browser_agent.pause_for_user_login(session.session_id, reason="Esperando login en Outlook Web")
        run.metadata["browser_session_id"] = paused.session_id
        run.metadata["task_state"] = "BROWSER_WAITING_FOR_LOGIN"
        self._append_message(run, user_text)
        self._save_run(run)
        return {
            **self._human_reply(
                run.metadata.get("locale", "es"),
                "No puedes usar Graph/device code en este entorno.",
                "Cambio automáticamente a la vía navegador y dejo bloqueado Graph para este run.",
                "1) Pulsa 'Abrir navegador'. 2) Haz login + 2FA. 3) Pulsa 'Ya hice login'.",
                [
                    {"id": "open_browser", "label": "Abrir navegador", "kind": "open_browser"},
                    {"id": "done_login", "label": "Ya hice login", "kind": "mark_login_done"},
                ],
            ),
            "run": run.model_dump(mode="json"),
            "wizard": {
                "show": True,
                "state": "BROWSER_WAITING_FOR_LOGIN",
                "session_id": paused.session_id,
                "status_text": "Esperando login...",
            },
        }

    def _continue_browser_after_login(self, run: Run) -> Dict[str, Any]:
        session_id = run.metadata.get("browser_session_id")
        if not session_id or not self.browser_agent:
            run.metadata["task_state"] = "FAILED"
            run.status = "failed"
            self._save_run(run)
            return {"reply": "No encuentro sesión de navegador para continuar.", "run": run.model_dump(mode="json")}

        session = self.browser_agent.mark_login_done(session_id)
        run.metadata["task_state"] = "BROWSER_READY"
        run.metadata["login_detected"] = bool(session.login_detected)
        run.metadata["task_state"] = "RUNNING"
        run.status = "running"

        # Browser worker real no está en este servicio; entregamos estado claro y finalizamos sin bucles.
        run.metadata["task_state"] = "DONE"
        run.status = "completed"
        run.metadata["result"] = {
            "status": "ok",
            "strategy": "browser",
            "message": "Login detectado. Flujo de navegador listo para extraer el último email.",
        }
        self._set_active_run(None)
        self._save_run(run)
        return {
            **self._human_reply(
                run.metadata.get("locale", "es"),
                "Ya completaste el login en Outlook Web.",
                "Reanudo el run por navegador y mantengo Graph desactivado en este run.",
                "Si quieres, pulsa 'Reintentar lectura' para ejecutar extracción cuando el worker esté activo.",
                [{"id": "retry", "label": "Reintentar", "kind": "retry"}],
            ),
            "run": run.model_dump(mode="json"),
            "wizard": {"show": True, "state": "DONE", "session_id": session_id, "status_text": "Hecho"},
        }

    def get_run_state(self, run_id: str) -> Dict[str, Any]:
        payload = self.memory.get_run(run_id)
        if not payload:
            return {"ok": False, "error": "run_not_found"}
        run = Run.model_validate(payload)
        return {"ok": True, "run": run.model_dump(mode="json"), "task_state": run.metadata.get("task_state")}

    def start_browser_session(self, run_id: str | None = None, start_url: str | None = None) -> Dict[str, Any]:
        if not self.browser_agent:
            return {"ok": False, "error_code": "BROWSER_AGENT_DISABLED", "message": "Browser agent is disabled."}
        session = self.browser_agent.start_session(start_url or "https://outlook.office.com/mail/")
        paused = self.browser_agent.pause_for_user_login(session.session_id, reason="Esperando login en Outlook Web")
        if run_id:
            payload = self.memory.get_run(run_id)
            if payload:
                run = Run.model_validate(payload)
                run.metadata["browser_session_id"] = paused.session_id
                run.metadata["task_state"] = "BROWSER_WAITING_FOR_LOGIN"
                self._save_run(run)
        return {"ok": True, "session": paused.model_dump(mode="json")}

    def mark_login_done(self, run_id: str) -> Dict[str, Any]:
        payload = self.memory.get_run(run_id)
        if not payload:
            return {"ok": False, "error": "run_not_found"}
        run = Run.model_validate(payload)
        return self._continue_browser_after_login(run)

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

    def converse(self, user_text: str) -> Dict[str, Any]:
        run = self._get_active_run()
        if not run or run.metadata.get("task_state") in {"DONE", "FAILED"}:
            status = self.connectors_status()
            graph = self.planner.plan(goal=user_text, connector_ready=status["m365_outlook"]["configured"])
            run = self._new_run(user_text, graph_to_dict(graph))
            run.metadata["locale"] = self._detect_locale(user_text)
            run.metadata["task_state"] = "CHOOSE_STRATEGY"
            self._set_active_run(run.run_id)
            if not status['m365_outlook']['configured']:
                run.status = 'blocked'
                run.metadata['task_state'] = 'FAILED'
                self._save_run(run)
                self._set_active_run(None)
                return {'reply': 'Necesito configurar Outlook antes de continuar.', 'run': run.model_dump(mode='json'), 'graph': run.metadata.get('graph'), 'result': {'status': 'needs_form', 'fields': self.m365_agent.config_questions()}}

        if self._is_graph_unviable_intent(user_text):
            run.metadata["task_state"] = "GRAPH_NOT_VIABLE"
            run.metadata.setdefault("flags", {})["graph_not_viable"] = True
            return self._ensure_browser_flow(run, user_text)

        state = run.metadata.get("task_state")
        prefs = self.memory.get_json("memory.user_preferences") or {}
        prefer_browser = prefs.get("outlook_strategy") == "browser"
        graph_not_viable = bool(run.metadata.get("flags", {}).get("graph_not_viable"))

        if state in {"BROWSER_WAITING_FOR_LOGIN", "START_BROWSER_SESSION"}:
            if self._is_login_done_intent(user_text):
                return self._continue_browser_after_login(run)
            return {
                **self._human_reply(
                    run.metadata.get("locale", "es"),
                    "Estamos en espera de tu login en navegador.",
                    "Mantengo el run en pausa sin volver a Graph.",
                    "Pulsa 'Abrir navegador' y luego 'Ya hice login'.",
                    [
                        {"id": "open_browser", "label": "Abrir navegador", "kind": "open_browser"},
                        {"id": "done_login", "label": "Ya hice login", "kind": "mark_login_done"},
                    ],
                ),
                "run": run.model_dump(mode="json"),
                "wizard": {"show": True, "state": "BROWSER_WAITING_FOR_LOGIN", "session_id": run.metadata.get("browser_session_id"), "status_text": "Esperando login..."},
            }

        if prefer_browser or graph_not_viable:
            return self._ensure_browser_flow(run, user_text)

        run.metadata["strategy"] = "graph"
        run.metadata["task_state"] = "RUNNING"
        result = self.m365_agent.get_last_email()
        run.metadata["last_result"] = result
        if result.get("status") == "auth_required":
            run.metadata["task_state"] = "NEED_AUTH_GRAPH"
            run.status = "blocked"
            self._save_run(run)
            return {
                **self._human_reply(
                    run.metadata.get("locale", "es"),
                    "Quieres el último email de Outlook.",
                    "Primero intento Graph porque está configurado.",
                    "Completa el login con el código o pulsa 'Cambiar a navegador' si no es viable.",
                    [
                        {"id": "open_ms", "label": "Abrir web de Microsoft", "kind": "open_device_login", "url": "https://microsoft.com/devicelogin"},
                        {"id": "switch_browser", "label": "Cambiar a navegador", "kind": "switch_browser"},
                    ],
                ),
                "run": run.model_dump(mode="json"),
                "device_code_message": result.get("message", ""),
            }

        run.metadata["task_state"] = "DONE" if result.get("status") == "ok" else "FAILED"
        run.status = "completed" if result.get("status") == "ok" else "failed"
        self._set_active_run(None)
        self._save_run(run)
        if result.get("status") == "ok":
            return {"reply": "Listo. Ya tengo el último email.", "run": run.model_dump(mode="json"), "result": result}
        return {"reply": "No pude completar la consulta.", "run": run.model_dump(mode="json"), "result": result}

    # Backwards compatible
    def execute(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self.converse(request.get("message", ""))
