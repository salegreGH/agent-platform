from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspacePaths:
    """Single source of truth for writable runtime paths."""

    base: Path
    generated_tools: Path
    generated_skills: Path
    logs: Path
    cache: Path
    msal_cache: Path
    memory_db: Path

    @classmethod
    def from_env(cls) -> "WorkspacePaths":
        local_appdata = os.getenv("LOCALAPPDATA")
        if local_appdata:
            base = Path(local_appdata) / "AgentPlatform" / "workspace"
        else:
            base = Path.home() / ".agentplatform" / "workspace"

        generated_tools = base / "generated_tools"
        generated_skills = base / "generated_skills"
        logs = base / "logs"
        cache = base / "cache"
        msal_cache = base / "msal_cache"
        memory_db = base / "memory.db"

        obj = cls(
            base=base,
            generated_tools=generated_tools,
            generated_skills=generated_skills,
            logs=logs,
            cache=cache,
            msal_cache=msal_cache,
            memory_db=memory_db,
        )
        obj.ensure_exists()
        return obj

    def ensure_exists(self) -> None:
        for directory in [
            self.base,
            self.generated_tools,
            self.generated_skills,
            self.logs,
            self.cache,
            self.msal_cache,
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
