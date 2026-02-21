from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any, Dict, List

from .contracts import TaskGraph, TaskNode


class TaskPlanner:
    def plan(self, goal: str, connector_ready: bool) -> TaskGraph:
        task_id = hashlib.sha1(goal.encode("utf-8")).hexdigest()[:10]
        nodes: List[TaskNode] = [
            TaskNode(id="intake", agent_id="orchestrator", action="intake"),
            TaskNode(id="plan", agent_id="planner", action="build_plan", depends_on=["intake"]),
        ]
        if not connector_ready:
            nodes.append(TaskNode(id="form", agent_id="orchestrator", action="request_form", depends_on=["plan"]))
        else:
            nodes.append(TaskNode(id="exec", agent_id="m365_outlook", action="outlook_get_last_email", depends_on=["plan"]))
            nodes.append(TaskNode(id="validate", agent_id="triage", action="validate_result", depends_on=["exec"]))
        return TaskGraph(task_id=task_id, goal=goal, nodes=nodes, metadata={"connector_ready": connector_ready})


class AntiLoopGuard:
    def __init__(self, memory):
        self.memory = memory

    def guard(self, kind: str, payload: Dict[str, Any], threshold: int = 3) -> Dict[str, Any]:
        key = hashlib.sha256(json.dumps({"kind": kind, "payload": payload}, sort_keys=True).encode("utf-8")).hexdigest()
        attempts = self.memory.mark_attempt(key)
        return {"fingerprint": key, "attempts": attempts, "blocked": attempts >= threshold}


def graph_to_dict(graph: TaskGraph) -> Dict[str, Any]:
    return {
        "task_id": graph.task_id,
        "goal": graph.goal,
        "nodes": [asdict(n) for n in graph.nodes],
        "metadata": graph.metadata,
    }
