import os
from pathlib import Path

import pytest

from app.agents.browser_agent import BrowserAgent
from app.memory import Memory


@pytest.mark.skipif(os.getenv("OUTLOOK_SESSION_READY") != "1", reason="requires logged browser session flag")
def test_outlook_browser_extract_logged_session(tmp_path: Path):
    memory = Memory(str(tmp_path / "memory.db"))
    browser = BrowserAgent(memory, artifacts_dir=tmp_path / "artifacts")
    session = browser.start_session("https://outlook.office.com/mail/")
    browser.mark_login_done(session.session_id)

    html = """
    <main>
      <span data-field='from'>Ops Team</span>
      <span data-field='subject'>Status</span>
      <span data-field='received'>2026-02-10</span>
      <span data-field='preview'>Latest preview</span>
    </main>
    """
    result = browser.extract_last_email(session.session_id, html=html)
    assert result["status"] == "ok"
    for key in ["subject", "from", "received_at", "preview"]:
        assert result["email"][key]
