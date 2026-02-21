from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AgentContract:
    id: str
    name: str
    purpose: str
    capabilities: List[str]
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    memory_namespace: str = "memory.default"
    policies: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskNode:
    id: str
    agent_id: str
    action: str
    depends_on: List[str] = field(default_factory=list)
    status: str = "pending"


@dataclass
class TaskGraph:
    task_id: str
    goal: str
    nodes: List[TaskNode]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    name: str
    args: Dict[str, Any]
    expected_schema: Dict[str, Any] = field(default_factory=dict)
