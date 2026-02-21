from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable, Dict

from .contracts import AgentContract


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}

    def register(self, name: str, fn: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self._tools[name] = fn

    def list(self) -> Dict[str, str]:
        return {k: v.__name__ for k, v in self._tools.items()}

    def execute(self, name: str, args: Dict[str, Any]):
        if name not in self._tools:
            return {"status": "error", "error": f"Tool not found: {name}"}
        return self._tools[name](args)


class AgentRegistry:
    def __init__(self):
        self._agents: Dict[str, AgentContract] = {}

    def register(self, contract: AgentContract):
        self._agents[contract.id] = contract

    def list(self):
        return [asdict(agent) for agent in self._agents.values()]

    def get(self, agent_id: str) -> AgentContract | None:
        return self._agents.get(agent_id)
