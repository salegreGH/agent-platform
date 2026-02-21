from pathlib import Path

from app.agents.browser_agent import BrowserAgent
from app.agents.m365_email_agent import M365EmailAgent
from app.core.paths import WorkspacePaths
from app.memory import Memory
from app.orchestrator import Orchestrator
from app.platform.core_runtime import CoreRuntimeService
from app.platform.evolver import EvolverService
from app.platform.policy import PolicyEngine, SecurityPolicyAgent
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


def test_orchestrator_switches_to_fallback_after_repeated_auth_block(tmp_path: Path):
    paths = build_paths(tmp_path)
    paths.ensure_exists()
    memory = Memory(str(paths.memory_db))

    m365 = M365EmailAgent(memory, cache_dir=str(paths.msal_cache))
    m365.set_config({"tenant_id": "common", "client_id": "test-client-id"})
    m365._acquire_token = lambda: {
        "ok": False,
        "error": "needs_device_code",
        "message": "Go to https://microsoft.com/devicelogin and enter code ABC123",
    }

    browser = BrowserAgent(memory, artifacts_dir=paths.artifacts)
    runtime = CoreRuntimeService(memory, m365, ToolRegistry(), browser_agent=browser)
    evolver = EvolverService(memory, paths)
    security = SecurityPolicyAgent(PolicyEngine(allowed_write_roots=[paths.root, paths.workspace]))
    orch = Orchestrator(memory, str(tmp_path), runtime, evolver, security)

    first = orch.run("dame mi ultimo email de outlook")
    assert "Necessito autorització" in first["reply"]

    second = orch.run("dame mi ultimo email de outlook")
    assert "Canvio de via" in second["reply"]
    fallback = second["cards"][1]["fallback"]
    assert fallback["strategy"] == "browser_outlook"

    sessions = memory.list_browser_sessions()
    assert len(sessions) == 1
    assert sessions[0]["status"] == "paused"


def test_orchestrator_switches_to_fallback_if_user_marks_path_unviable(tmp_path: Path):
    paths = build_paths(tmp_path)
    paths.ensure_exists()
    memory = Memory(str(paths.memory_db))

    m365 = M365EmailAgent(memory, cache_dir=str(paths.msal_cache))
    m365.set_config({"tenant_id": "common", "client_id": "test-client-id"})
    m365._acquire_token = lambda: {
        "ok": False,
        "error": "needs_device_code",
        "message": "Go to https://microsoft.com/devicelogin and enter code DEF456",
    }

    browser = BrowserAgent(memory, artifacts_dir=paths.artifacts)
    runtime = CoreRuntimeService(memory, m365, ToolRegistry(), browser_agent=browser)
    evolver = EvolverService(memory, paths)
    security = SecurityPolicyAgent(PolicyEngine(allowed_write_roots=[paths.root, paths.workspace]))
    orch = Orchestrator(memory, str(tmp_path), runtime, evolver, security)

    response = orch.run("esta via no es viable, busca alternativa para conectar al email")
    assert "Canvio de via" in response["reply"]
    assert "no és viable" in response["reply"]
    fallback = response["cards"][1]["fallback"]
    assert fallback["strategy"] == "browser_outlook"

    sessions = memory.list_browser_sessions()
    assert len(sessions) == 1
    assert sessions[0]["status"] == "paused"
