from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    requires_confirmation: bool = False


class PolicyEngine:
    def __init__(self, allowed_write_roots: Iterable[Path], allowed_commands: Iterable[str] | None = None):
        self.allowed_write_roots = [p.resolve() for p in allowed_write_roots]
        self.allowed_commands = set(allowed_commands or {"python", "pytest", "uvicorn", "echo"})
        self.sensitive_actions = {"send_email", "post_message", "delete_file", "upload_file"}

    def validate_write_path(self, path: Path) -> PolicyDecision:
        candidate = path.resolve()
        for root in self.allowed_write_roots:
            if str(candidate).startswith(str(root)):
                return PolicyDecision(True, "path_allowed")
        return PolicyDecision(False, f"write blocked outside allowlist: {candidate}")

    def check_action(self, role: str, action: str) -> PolicyDecision:
        if action in self.sensitive_actions and role != "user":
            return PolicyDecision(True, "sensitive_requires_confirmation", requires_confirmation=True)
        return PolicyDecision(True, "ok")

    def check_command(self, command: str) -> PolicyDecision:
        program = (command or "").split(" ", 1)[0].strip()
        if program not in self.allowed_commands:
            return PolicyDecision(False, f"command not allowlisted: {program}")
        return PolicyDecision(True, "ok")


class SecurityPolicyAgent:
    def __init__(self, engine: PolicyEngine):
        self.engine = engine

    def evaluate_tool(self, role: str, tool_name: str, args: Dict[str, str]) -> PolicyDecision:
        return self.engine.check_action(role=role, action=tool_name)
