from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspacePaths:
    """Single source of truth for writable runtime paths."""

    root: Path
    workspace: Path
    generated_tools: Path
    generated_skills: Path
    logs: Path
    cache: Path
    msal_cache: Path
    secrets: Path
    proposals: Path
    artifacts: Path
    attachments: Path
    memory_db: Path

    @property
    def base(self) -> Path:
        return self.workspace

    @classmethod
    def from_env(cls) -> "WorkspacePaths":
        local_appdata = os.getenv("LOCALAPPDATA")
        if local_appdata:
            root = Path(local_appdata) / "AgentPlatform"
        else:
            root = Path.home() / ".agentplatform"

        workspace = root / "workspace"
        obj = cls(
            root=root,
            workspace=workspace,
            generated_tools=workspace / "generated_tools",
            generated_skills=workspace / "generated_skills",
            logs=root / "logs",
            cache=root / "cache",
            msal_cache=root / "msal_cache",
            secrets=root / "secrets",
            proposals=root / "proposals",
            artifacts=root / "artifacts",
            attachments=root / "attachments",
            memory_db=root / "memory.db",
        )
        obj.ensure_exists()
        return obj

    def ensure_exists(self) -> None:
        for directory in [
            self.root,
            self.workspace,
            self.generated_tools,
            self.generated_skills,
            self.logs,
            self.cache,
            self.msal_cache,
            self.secrets,
            self.proposals,
            self.artifacts,
            self.attachments,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    def safe_join(self, base: Path, requested_path: str | None) -> Path:
        candidate = (base / (requested_path or "")).resolve()
        base_resolved = base.resolve()
        if not str(candidate).startswith(str(base_resolved)):
            raise PermissionError(
                f"Blocked write outside workspace. base={base_resolved} requested={requested_path} resolved={candidate}"
            )
        return candidate
