import json
from pathlib import Path

from app.agents.browser_agent import BrowserAgent
from app.agents.bugfix_agent import BugFixAgent
from app.agents.m365_email_agent import M365EmailAgent
from app.memory import Memory
from app.platform.core_runtime import CoreRuntimeService
from app.platform.registry import ToolRegistry
from app.recovery.recovery_manager import RecoveryManager


def build_runtime(tmp_path: Path):
    memory = Memory(str(tmp_path / "memory.db"))
    selectors_path = tmp_path / "outlook.json"
    selectors_path.write_text(json.dumps({"field_patterns": {"from": ["data-field='from'>([^<]+)"], "subject": ["data-field='subject'>([^<]+)"], "received": ["data-field='received'>([^<]+)"], "preview": ["data-field='preview'>([^<]+)"]}}, indent=2), encoding="utf-8")
    browser = BrowserAgent(memory, artifacts_dir=tmp_path / "artifacts", selectors_path=selectors_path)
    recovery = RecoveryManager(memory, workspace_dir=tmp_path / "workspace", bugfix_agent=BugFixAgent(selectors_path))
    runtime = CoreRuntimeService(memory, M365EmailAgent(memory, cache_dir=str(tmp_path / "msal")), ToolRegistry(), browser_agent=browser, recovery_manager=recovery)
    return runtime, memory


def test_classifier_does_not_use_missing_capability_if_tool_exists(tmp_path: Path):
    runtime, _ = build_runtime(tmp_path)
    assert runtime._classify_error("UNKNOWN_ERROR") == "BUG_CORE"


def test_login_done_auto_triggers_extract(tmp_path: Path):
    runtime, _ = build_runtime(tmp_path)
    run = runtime._new_run("ultimo email outlook", {"nodes": []})
    session = runtime.browser_agent.start_session("https://outlook.office.com/mail/")
    runtime.browser_agent.pause_for_user_login(session.session_id)
    run.metadata["browser_session_id"] = session.session_id
    run.metadata["browser_current_url"] = "https://outlook.office.com/mail/"
    run.metadata["browser_inbox_html"] = "<main>Inbox</main><span data-field='from'>Ops</span><span data-field='subject'>Hi</span><span data-field='received'>now</span><span data-field='preview'>body</span>"
    runtime._save_run(run)

    out = runtime.mark_login_done(run.run_id)
    assert out["status"] == "ok"
    assert out["run"]["metadata"]["auth_status"] == "READY"


def test_login_done_requires_inbox_ready(tmp_path: Path):
    runtime, _ = build_runtime(tmp_path)
    run = runtime._new_run("ultimo email outlook", {"nodes": []})
    session = runtime.browser_agent.start_session("https://login.microsoftonline.com/")
    runtime.browser_agent.pause_for_user_login(session.session_id)
    run.metadata["browser_session_id"] = session.session_id
    run.metadata["browser_current_url"] = "https://login.microsoftonline.com/"
    run.metadata["browser_inbox_html"] = "<div>Select an account</div>"
    runtime._save_run(run)

    out = runtime.mark_login_done(run.run_id)
    assert "not_in_inbox" in out["reply"]
    assert out["run"]["metadata"]["task_state"] == "WAITING_HUMAN_LOGIN"


def test_retry_creates_running_step(tmp_path: Path):
    runtime, memory = build_runtime(tmp_path)
    run = runtime._new_run("ultimo email outlook", {"nodes": []})
    session = runtime.browser_agent.start_session("https://outlook.office.com/mail/")
    runtime.browser_agent.mark_login_done(session.session_id)
    run.metadata["browser_session_id"] = session.session_id
    run.metadata["browser_inbox_html"] = "<div>broken</div>"
    runtime._save_run(run)
    runtime._run_browser_extract_step(run, session.session_id)

    runtime.retry_run(run.run_id)
    steps = memory.list_run_steps(run.run_id)
    assert any(s["status"] == "running" for s in steps)


def test_outlook_extractor_fixture_extracts_fields(tmp_path: Path):
    runtime, _ = build_runtime(tmp_path)
    session = runtime.browser_agent.start_session("https://outlook.office.com/mail/")
    runtime.browser_agent.mark_login_done(session.session_id)
    html = """
    <div>
      <span data-field='from'>Alice</span>
      <span data-field='subject'>Quarterly update</span>
      <span data-field='received'>10:22</span>
      <span data-field='preview'>First line</span>
    </div>
    """
    out = runtime.browser_agent.extract_latest_email_outlook_web(session.session_id, html=html)
    assert out["status"] == "ok"
    assert out["email"]["subject"] == "Quarterly update"
