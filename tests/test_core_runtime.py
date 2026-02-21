from pathlib import Path

from app.agents.m365_email_agent import M365EmailAgent
from app.core.paths import WorkspacePaths
from app.memory import Memory
from app.platform.core_runtime import CoreRuntimeService
from app.platform.registry import ToolRegistry


def build_paths(tmp_path: Path) -> WorkspacePaths:
    return WorkspacePaths(
        root=tmp_path,
        workspace=tmp_path / "workspace",
        generated_tools=tmp_path / "workspace" / "generated_tools",
        generated_skills=tmp_path / "workspace" / "generated_skills",
        logs=tmp_path / "logs",
        cache=tmp_path / "cache",
        msal_cache=tmp_path / "msal_cache",
        secrets=tmp_path / "secrets",
        proposals=tmp_path / "proposals",
        artifacts=tmp_path / "artifacts",
        attachments=tmp_path / "attachments",
        memory_db=tmp_path / "memory.db",
    )


def test_core_runtime_requests_form_when_connector_missing(tmp_path: Path):
    paths = build_paths(tmp_path)
    paths.ensure_exists()
    memory = Memory(str(paths.memory_db))
    m365 = M365EmailAgent(memory, cache_dir=str(paths.msal_cache))
    runtime = CoreRuntimeService(memory, m365, ToolRegistry())

    result = runtime.execute({"message": "Mostra l'ultim email"})
    assert result["result"]["status"] == "needs_form"
    assert result["graph"]["nodes"][2]["action"] == "request_form"
