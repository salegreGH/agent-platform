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
    TOOL_EXTRACT = "browser.outlook.extract_latest_email"

    def __init__(self, memory: Memory, artifacts_dir: Path, selectors_path: Path | None = None):
        self.memory = memory
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.selectors_path = selectors_path

    def has_action(self, action_name: str) -> bool:
        return action_name in {self.TOOL_EXTRACT, "extract_last_email"}

    def _load_outlook_selectors(self) -> Dict[str, Any]:
        if self.selectors_path and self.selectors_path.exists():
            return json.loads(self.selectors_path.read_text(encoding="utf-8"))
        return {
            "inbox_ready": ["aria-label=Inbox", "role=main", "div[data-app-section='message-list']"],
            "message_item": ["div[role='row']", "div[data-convid]", "article[role='listitem']"],
            "field_patterns": {
                "subject": [r"data-field=[\"']subject[\"']>([^<]+)<", r"aria-label=[\"']Subject[\"'][^>]*>([^<]+)<"],
                "from": [r"data-field=[\"']from[\"']>([^<]+)<", r"aria-label=[\"']From[\"'][^>]*>([^<]+)<"],
                "received": [r"data-field=[\"']received[\"']>([^<]+)<", r"aria-label=[\"']Received[\"'][^>]*>([^<]+)<"],
                "preview": [r"data-field=[\"']preview[\"']>([^<]+)<", r"class=[\"'][^\"']*preview[^\"']*[\"'][^>]*>([^<]+)<"],
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

    def validate_outlook_ready(self, session_id: str, *, html: str | None = None, current_url: str | None = None) -> Dict[str, Any]:
        session = self.get_session(session_id)
        source = (html or "").lower()
        url = (current_url or session.current_url or "").lower()
        inbox_url = "outlook.office.com/mail"

        missing: list[str] = []
        if inbox_url not in url:
            missing.append("not_in_inbox")
        if any(k in source for k in ["select an account", "elige una cuenta", "pick an account"]):
            missing.append("account_picker")
        if any(k in source for k in ["consent", "permissions requested", "accept"]):
            missing.append("consent")
        has_message_signals = all(k in source for k in ["data-field='from'", "data-field='subject'", "data-field='received'"]) or all(
            k in source for k in ["data-field=\"from\"", "data-field=\"subject\"", "data-field=\"received\""]
        )
        if "inbox" not in source and "bandeja" not in source and not has_message_signals:
            missing.append("inbox_not_visible")

        ready = len(missing) == 0
        if ready:
            session.login_detected = True
            session.status = "ready"
            session.pause_reason = None
            session.last_error_code = None
        else:
            session.login_detected = False
            session.status = "paused_login"
            session.last_error_code = "NOT_READY"
        session.updated_at = datetime.now(timezone.utc)
        session.last_action_log.append({"action": "validate_ready", "ready": ready, "missing": missing, "ts": session.updated_at.isoformat()})
        self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
        return {"ready": ready, "missing": missing, "session_id": session.session_id, "current_url": session.current_url}

    def apply_recovery_strategy(self, session_id: str, strategy: str) -> Dict[str, Any]:
        session = self.get_session(session_id)
        ts = datetime.now(timezone.utc).isoformat()
        action = {"strategy": strategy, "ts": ts}
        if strategy == "navigate_to_inbox":
            session.current_url = "https://outlook.office.com/mail/"
        session.last_action_log.append({"action": "recovery", **action})
        session.trace.append({"event": "recovery_strategy", **action})
        self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
        return {"ok": True, "strategy": strategy}

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

    def _save_failure_artifacts(self, session: BrowserSession, html: str) -> dict[str, str]:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        base = f"{session.session_id}-{ts}"
        html_path = self.artifacts_dir / f"{base}.html"
        html_path.write_text(html, encoding="utf-8")
        screenshot_path = self.artifacts_dir / f"{base}.png"
        screenshot_path.write_bytes(b"placeholder")
        return {"html_dump_path": str(html_path), "screenshot_path": str(screenshot_path)}

    def extract_latest_email_outlook_web(self, session_id: str, *, html: str | None = None) -> Dict[str, Any]:
        session = self.get_session(session_id)
        if session.status == "paused_login" or not session.login_detected:
            return {"status": "blocked", "error_code": "AUTH_REQUIRED", "message": "Login/2FA pendiente."}

        source = html or ""
        session.status = "running"
        session.updated_at = datetime.now(timezone.utc)
        session.last_action_log.append({"action": self.TOOL_EXTRACT, "ts": session.updated_at.isoformat()})

        if not source:
            session.status = "error"
            session.last_error_code = "NOT_READY"
            self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
            return {
                "status": "error",
                "error_code": "NOT_READY",
                "message": "No HTML de Inbox disponible para extraer.",
                "current_url": session.current_url,
            }

        selectors_cfg = self._load_outlook_selectors()
        field_patterns = selectors_cfg.get("field_patterns", {})
        inbox_hint = bool(re.search(r"inbox|bandeja", source, re.IGNORECASE))
        iframe_hint = "<iframe" in source.lower()
        popup_hint = bool(re.search(r"consent|tips|try the new outlook|got it", source, re.IGNORECASE))
        not_in_inbox = not bool(re.search(r"outlook\.office\.com/mail|inbox|bandeja", (session.current_url or "") + source, re.IGNORECASE))
        data = {
            "subject": self._extract_with_patterns(source, field_patterns.get("subject", [])),
            "from": self._extract_with_patterns(source, field_patterns.get("from", [])),
            "received": self._extract_with_patterns(source, field_patterns.get("received", field_patterns.get("received_at", []))),
            "preview": self._extract_with_patterns(source, field_patterns.get("preview", [])),
            "message_url": session.current_url,

        }

        if not all([data["subject"], data["from"], data["received"], data["preview"]]):
            session.status = "error"
            if popup_hint:
                session.last_error_code = "POPUP_BLOCKING"
            elif not_in_inbox:
                session.last_error_code = "NOT_IN_INBOX"
            elif iframe_hint:
                session.last_error_code = "IFRAME_ISSUE"
            else:
                session.last_error_code = "SELECTOR_BROKE"
            snippet = re.sub(r"\s+", " ", source)[:400]
            artifacts = self._save_failure_artifacts(session, source)
            session.trace.append({"event": "extract_failed", "snippet": snippet, **artifacts})
            self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
            return {
                "status": "error",
                "error_code": session.last_error_code,
                "message": "No se pudo localizar el email más reciente.",
                "html_snippet": snippet,
                "selectors_tried": field_patterns,
                "dom_hints": {"has_inbox_keyword": inbox_hint, "has_iframe": iframe_hint, "has_popup": popup_hint, "source_len": len(source)},
                "current_url": session.current_url,
                "action_log": session.last_action_log[-20:],
                **artifacts,
            }

        data["received_iso"] = data["received"]
        data["received_at"] = data["received"]
        session.status = "ready"
        session.trace.append({"event": "extract_ok", "email": data})
        self.memory.upsert_browser_session(session.session_id, session.model_dump(mode="json"))
        return {"status": "ok", "email": data}

    def extract_last_email(self, session_id: str, *, html: str | None = None) -> Dict[str, Any]:
        return self.extract_latest_email_outlook_web(session_id, html=html)

    def execute_action(self, session_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
        session = self.get_session(session_id)
        if session.status == "paused_login":
            return {
                "status": "paused",
                "error_code": "AUTH_REQUIRED",
                "message": "Session paused waiting for user login/2FA. Resume from UI after manual auth.",
            }

        parsed = BrowserAction.model_validate(action)
        if parsed.action != "screenshot":
            return {
                "status": "error",
                "error_code": "TOOL_NOT_IMPLEMENTED",
                "message": "Browser worker Playwright runtime is not enabled in this service.",
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
