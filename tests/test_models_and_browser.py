from pathlib import Path

from app.agents.browser_agent import BrowserAgent
from app.agents.m365_email_agent import M365EmailAgent
from app.core.paths import WorkspacePaths
from app.memory import Memory
from app.platform.core_runtime import CoreRuntimeService
from app.platform.models import ActionCall, ConnectorConfig, Run, RunStep
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


def test_domain_models_validate():
    call = ActionCall(agent_id="planner", action="build_plan", args={"goal": "x"})
    assert call.agent_id == "planner"

    run = Run(run_id="run-1", goal="test", steps=[RunStep(id="a", agent="planner", action="build")])
    assert run.steps[0].status == "pending"

    cfg = ConnectorConfig(connector_id="jira", auth_mode="api_key", settings={"base_url": "http://localhost"})
    assert cfg.retry_count == 2


def test_runtime_persists_runs_and_connector_config(tmp_path: Path):
    paths = build_paths(tmp_path)
    paths.ensure_exists()
    memory = Memory(str(paths.memory_db))
    m365 = M365EmailAgent(memory, cache_dir=str(paths.msal_cache))
    runtime = CoreRuntimeService(memory, m365, ToolRegistry())

    result = runtime.execute({"message": "Mostra l'ultim email"})
    assert result["run"]["status"] == "blocked"
    assert memory.list_runs()
    assert memory.get_connector_config("m365_outlook") is not None


def test_browser_pause_resume_and_controlled_error(tmp_path: Path):
    paths = build_paths(tmp_path)
    paths.ensure_exists()
    memory = Memory(str(paths.memory_db))
    browser = BrowserAgent(memory, artifacts_dir=paths.artifacts)
    session = browser.start_session("https://example.com")

    paused = browser.pause_for_user_login(session.session_id)
    assert paused.status == "paused"

    blocked = browser.execute_action(session.session_id, {"action": "click", "selector": "button"})
    assert blocked["status"] == "paused"

    browser.mark_login_done(session.session_id)
    failed = browser.execute_action(session.session_id, {"action": "open_url", "value": "https://example.com"})
    assert failed["error_code"] == "BROWSER_WORKER_UNAVAILABLE"

    assert browser.get_session(session.session_id).login_detected is True

    snap = browser.execute_action(session.session_id, {"action": "screenshot"})
    assert snap["status"] == "ok"
    assert Path(snap["artifact"]).exists()
