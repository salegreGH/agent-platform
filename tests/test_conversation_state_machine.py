from pathlib import Path

from app.agents.browser_agent import BrowserAgent
from app.agents.m365_email_agent import M365EmailAgent
from app.core.paths import WorkspacePaths
from app.memory import Memory
from app.platform.core_runtime import CoreRuntimeService
from app.platform.registry import ToolRegistry


def build_runtime(tmp_path: Path):
    paths = WorkspacePaths(
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
    paths.ensure_exists()
    memory = Memory(str(paths.memory_db))
    m365 = M365EmailAgent(memory, cache_dir=str(paths.msal_cache))
    m365.set_config({"tenant_id": "common", "client_id": "test-client-id"})
    m365._acquire_token = lambda: {"ok": False, "error": "needs_device_code", "message": "Device code required"}
    runtime = CoreRuntimeService(memory, m365, ToolRegistry(), browser_agent=BrowserAgent(memory, artifacts_dir=paths.artifacts))
    return runtime, memory


def test_no_device_code_after_graph_marked_unviable(tmp_path: Path):
    runtime, _ = build_runtime(tmp_path)
    runtime.converse("dame el ultimo email")
    switched = runtime.converse("no puedo, no es viable")
    assert switched["run"]["metadata"]["flags"]["graph_not_viable"] is True
    followup = runtime.converse("continua")
    assert "device code" not in followup["reply"].lower()


def test_human_reply_includes_next_step_and_cta(tmp_path: Path):
    runtime, _ = build_runtime(tmp_path)
    payload = runtime.converse("dame el ultimo email")
    assert "Siguiente paso" in payload["reply"]
    assert payload["actions"]
