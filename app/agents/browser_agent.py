from __future__ import annotations

from datetime import timezone, datetime
from pathlib import Path
import json
import re
from typing import Any, Dict
from uuid import uuid4

from ..memory import Memory
from ..platform.models import BrowserAction, BrowserSession


class BrowserAgent:
    def __init__(self, memory: Memory, artifacts_dir: Path, selectors_path: Path | None = None):
        self.memory = memory
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.selectors_path = selectors_path

    def _load_outlook_selectors(self) -> Dict[str, Any]:
        if self.selectors_path and self.selectors_path.exists():
            return json.loads(self.selectors_path.read_text(encoding="utf-8"))
        return {
            "inbox_ready": ["aria-label=Inbox", "role=main", "div[data-app-section='message-list']"],
            "message_item": ["div[role='row']", "div[data-convid]", "article[role='listitem']"],
            "field_patterns": {
                "subject": [r'data-field=["\']subject["\']>([^<]+)<', r'aria-label=["\']Subject["\'][^>]*>([^<]+)<'],
                "from": [r'data-field=["\']from["\']>([^<]+)<', r'aria-label=["\']From["\'][^>]*>([^<]+)<'],
                "received_at": [r'data-field=["\']received["\']>([^<]+)<', r'aria-label=["\']Received["\'][^>]*>([^<]+)<'],
                "preview": [r'data-field=["\']preview["\']>([^<]+)<', r'class=["\'][^"\']*preview[^"\']*["\'][^>]*>([^<]+)<'],
            },
        }

    def start_session(self, start_url: str | None = None) -> BrowserSession:
        selectors_cfg = self._load_outlook_selectors()
        session = BrowserSession(
            session_id=f"browser-{uuid4().hex[:10]}",
            current_url=start_url,
            status="open",
            selectors={
                "inbox_ready": selectors_cfg.get("inbox_ready", []),
                "message_item": selectors_cfg.get("message_item", []),
            },
        )
        self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
        return session

    def get_session(self, session_id: str) -> BrowserSession:
        payload = self.memory.get_browser_session(session_id)
        if not payload:
            raise ValueError(f"Browser session not found: {session_id}")
        return BrowserSession.model_validate(payload)

    def pause_for_user_login(self, session_id: str, reason: str = "Login o 2FA requerit") -> BrowserSession:
        session = self.get_session(session_id)
        session.status = "paused_login"
        session.pause_reason = reason
        session.updated_at = datetime.now(timezone.utc)
        session.trace.append({"event": "pause", "reason": reason})
        session.last_action_log.append({"action": "pause_for_login", "reason": reason, "ts": session.updated_at.isoformat()})
        self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
        return session

    def mark_login_done(self, session_id: str) -> BrowserSession:
        session = self.get_session(session_id)
        session.login_detected = True
        session.status = "ready"
        session.pause_reason = None
        session.updated_at = datetime.now(timezone.utc)
        session.trace.append({"event": "login_detected", "signal": "inbox_visible"})
        session.last_action_log.append({"action": "mark_login_done", "ts": session.updated_at.isoformat()})
        self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
        return session

    def resume(self, session_id: str) -> BrowserSession:
        session = self.get_session(session_id)
        if session.status != "paused_login":
            raise ValueError("Session is not paused")
        session.status = "ready"
        session.pause_reason = None
        session.updated_at = datetime.now(timezone.utc)
        session.trace.append({"event": "resume"})
        session.last_action_log.append({"action": "resume", "ts": session.updated_at.isoformat()})
        self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
        return session

    @staticmethod
    def _extract_with_patterns(html: str, patterns: list[str]) -> str | None:
        for pattern in patterns:
            m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
            if m:
                return re.sub(r"\s+", " ", m.group(1)).strip()
        return None

    def extract_last_email(self, session_id: str, *, html: str | None = None) -> Dict[str, Any]:
        session = self.get_session(session_id)
        if session.status == "paused_login":
            return {"status": "blocked", "error_code": "AUTH_REQUIRED", "message": "Login/2FA pendiente."}

        source = html or ""
        session.status = "running"
        session.updated_at = datetime.now(timezone.utc)
        session.last_action_log.append({"action": "extract_last_email", "ts": session.updated_at.isoformat()})

        if not source:
            session.status = "error"
            session.last_error_code = "MISSING_CAPABILITY"
            self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
            return {
                "status": "error",
                "error_code": "MISSING_CAPABILITY",
                "message": "No browser worker content available for extraction.",
            }

        selectors_cfg = self._load_outlook_selectors()
        field_patterns = selectors_cfg.get("field_patterns", {})
        data = {
            "subject": self._extract_with_patterns(source, field_patterns.get("subject", [])),
            "from": self._extract_with_patterns(source, field_patterns.get("from", [])),
            "received_at": self._extract_with_patterns(source, field_patterns.get("received_at", [])),
            "preview": self._extract_with_patterns(source, field_patterns.get("preview", [])),
        }

        if not all(data.values()):
            session.status = "error"
            session.last_error_code = "SELECTOR_BROKE"
            snippet = re.sub(r"\s+", " ", source)[:400]
            session.trace.append({"event": "selector_broke", "snippet": snippet})
            self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
            return {
                "status": "error",
                "error_code": "SELECTOR_BROKE",
                "message": "No se pudo localizar el email más reciente con los selectores actuales.",
                "html_snippet": snippet,
                "selectors_tried": field_patterns,
                "dom_hints": {"has_inbox_keyword": "inbox" in source.lower(), "source_len": len(source)},
                "current_url": session.current_url,
            }

        session.status = "ready"
        session.trace.append({"event": "extract_ok", "email": data})
        self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
        return {"status": "ok", "email": data}

    def execute_action(self, session_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
        session = self.get_session(session_id)
        if session.status == "paused_login":
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
