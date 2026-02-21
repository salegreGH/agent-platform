from __future__ import annotations

from typing import Any, Dict

from ..agents.m365_email_agent import M365EmailAgent
from ..memory import Memory
from .registry import ToolRegistry
from .task_graph import AntiLoopGuard, TaskPlanner, graph_to_dict


class CoreRuntimeService:
    def __init__(self, memory: Memory, m365_agent: M365EmailAgent, tool_registry: ToolRegistry):
        self.memory = memory
        self.m365_agent = m365_agent
        self.tool_registry = tool_registry
        self.planner = TaskPlanner()
        self.loop_guard = AntiLoopGuard(memory)

    def connectors_status(self) -> Dict[str, Any]:
        cfg = self.memory.get_json("m365.config") or {}
        ready = bool(cfg.get("tenant_id") and cfg.get("client_id"))
        return {
            "m365_outlook": {
                "configured": ready,
                "scopes": cfg.get("scopes") or ["Mail.Read", "User.Read"],
                "auth_mode": cfg.get("auth_mode") or "device_code",
            }
        }

    def execute(self, request: Dict[str, Any]) -> Dict[str, Any]:
        user_text = request.get("message", "")
        status = self.connectors_status()
        graph = self.planner.plan(goal=user_text, connector_ready=status["m365_outlook"]["configured"])
        payload: Dict[str, Any] = {"graph": graph_to_dict(graph), "result": None}

        if not status["m365_outlook"]["configured"]:
            payload["result"] = {
                "status": "needs_form",
                "form_type": "m365_config",
                "fields": self.m365_agent.config_questions(),
            }
            self.memory.save_task(graph.task_id, user_text, "blocked", payload)
            return payload

        if "important" in user_text.lower() and ("respond" in user_text.lower() or "sense" in user_text.lower()):
            result = self.m365_agent.triage_important_unanswered()
        else:
            result = self.m365_agent.get_last_email()

        payload["result"] = result
        loop = self.loop_guard.guard("core_execute", {"goal": user_text, "result": result.get("status")})
        payload["loop_guard"] = loop
        self.memory.save_task(graph.task_id, user_text, "completed" if result.get("status") == "ok" else "failed", payload)
        return payload
