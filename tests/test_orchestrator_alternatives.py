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


def build_orchestrator(tmp_path: Path):
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
    return orch, memory


def test_unviable_intent_blocks_device_code_loop(tmp_path: Path):
    orch, memory = build_orchestrator(tmp_path)

    first = orch.run("dame el ultimo email de outlook")
    assert any(a["label"] == "Abrir web de Microsoft" for a in first["actions"])

    second = orch.run("no es viable")
    assert "Cambio automáticamente a la vía navegador" in second["reply"]
    assert second["run"]["metadata"]["flags"]["graph_not_viable"] is True

    third = orch.run("continua")
    assert "mantengo Graph desactivado" in third["reply"]
    assert "device code" not in third["reply"].lower()

    sessions = memory.list_browser_sessions()
    assert sessions


def test_browser_waiting_then_done_login_flow(tmp_path: Path):
    orch, _ = build_orchestrator(tmp_path)

    response = orch.run("no es viable, hazlo por navegador")
    assert response["wizard"]["state"] == "BROWSER_WAITING_FOR_LOGIN"
    run_id = response["run"]["run_id"]

    done = orch.core_runtime.mark_login_done(run_id)
    assert done["wizard"]["state"] == "DONE"
    assert "Siguiente paso" in done["reply"]
