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
    selectors_path.write_text(
        json.dumps({"version": 1, "inbox_ready": [], "message_item": [], "field_patterns": {"subject": ["x-no-match"]}}, indent=2),
        encoding="utf-8",
    )
    browser = BrowserAgent(memory, artifacts_dir=tmp_path / "artifacts", selectors_path=selectors_path)
    bugfix = BugFixAgent(selectors_path)
    recovery = RecoveryManager(memory, workspace_dir=tmp_path / "workspace", bugfix_agent=bugfix)
    runtime = CoreRuntimeService(memory, M365EmailAgent(memory, cache_dir=str(tmp_path / "msal")), ToolRegistry(), browser_agent=browser, recovery_manager=recovery)
    return runtime, memory


def test_recovery_manager_collects_evidence_and_retries(tmp_path: Path):
    runtime, memory = build_runtime(tmp_path)
    session = runtime.browser_agent.start_session("https://outlook.office.com/mail/")
    runtime.browser_agent.mark_login_done(session.session_id)

    run = runtime._new_run("dame el último email", {"nodes": []})
    run.metadata["browser_session_id"] = session.session_id
    run.metadata["browser_inbox_html"] = "<div>layout changed</div>"
    runtime._save_run(run)

    first = runtime._run_browser_extract_step(run, session.session_id)
    assert first["status"] == "error"
    out = runtime.retry_run(run.run_id)
    assert out["status"] in {"ok", "error"}

    saved = memory.get_run(run.run_id)
    recovery = saved["metadata"].get("recovery", {})
    assert recovery.get("evidence", {}).get("html_dump_path")
    assert Path(recovery["evidence"]["html_dump_path"]).exists()
