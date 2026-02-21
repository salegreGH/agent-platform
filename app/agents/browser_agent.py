from __future__ import annotations

from datetime import timezone, datetime
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from ..memory import Memory
from ..platform.models import BrowserAction, BrowserSession


class BrowserAgent:
    def __init__(self, memory: Memory, artifacts_dir: Path):
        self.memory = memory
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def start_session(self, start_url: str | None = None) -> BrowserSession:
        session = BrowserSession(session_id=f"browser-{uuid4().hex[:10]}", current_url=start_url)
        self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
        return session

    def get_session(self, session_id: str) -> BrowserSession:
        payload = self.memory.get_browser_session(session_id)
        if not payload:
            raise ValueError(f"Browser session not found: {session_id}")
        return BrowserSession.model_validate(payload)

    def pause_for_user_login(self, session_id: str, reason: str = "Login o 2FA requerit") -> BrowserSession:
        session = self.get_session(session_id)
        session.status = "paused"
        session.pause_reason = reason
        session.updated_at = datetime.now(timezone.utc)
        session.trace.append({"event": "pause", "reason": reason})
        self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
        return session

    def mark_login_done(self, session_id: str) -> BrowserSession:
        session = self.get_session(session_id)
        session.login_detected = True
        session.status = "running"
        session.pause_reason = None
        session.updated_at = datetime.now(timezone.utc)
        session.trace.append({"event": "login_detected", "signal": "inbox_visible"})
        self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
        return session

    def resume(self, session_id: str) -> BrowserSession:
        session = self.get_session(session_id)
        if session.status != "paused":
            raise ValueError("Session is not paused")
        session.status = "running"
        session.pause_reason = None
        session.updated_at = datetime.now(timezone.utc)
        session.trace.append({"event": "resume"})
        self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
        return session

    def execute_action(self, session_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
        session = self.get_session(session_id)
        if session.status == "paused":
            return {
                "status": "paused",
                "error_code": "BROWSER_SESSION_PAUSED",
                "message": "Session paused waiting for user login/2FA. Resume from UI after manual auth.",
            }

        parsed = BrowserAction.model_validate(action)
        # Controlled fallback: this platform provides browser contracts, but execution
        # requires Playwright runtime in the worker service.
        if parsed.action != "screenshot":
            return {
                "status": "error",
                "error_code": "BROWSER_WORKER_UNAVAILABLE",
                "message": "Browser worker Playwright runtime is not enabled in this service. Open an evolve proposal to deploy worker support.",
                "resolution_plan": [
                    "Enable worker service with Playwright dependencies",
                    "Bind browser session broker between data plane and worker",
                    "Re-run this action",
                ],
            }

        snap_name = f"{session.session_id}-{uuid4().hex[:6]}.txt"
        snap_path = self.artifacts_dir / snap_name
        snap_path.write_text("screenshot placeholder", encoding="utf-8")

        session.last_screenshot = str(snap_path)
        session.trace.append({"event": "screenshot", "artifact": str(snap_path)})
        session.updated_at = datetime.now(timezone.utc)
        self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
        return {"status": "ok", "artifact": str(snap_path)}
