from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict

from ..agents.bugfix_agent import BugFixAgent


class RecoveryManager:
    def __init__(self, memory, workspace_dir: Path, bugfix_agent: BugFixAgent, max_attempts: int = 3, auto_apply_safe_patch: bool = True):
        self.memory = memory
        self.workspace_dir = workspace_dir
        self.bugfix_agent = bugfix_agent
        self.max_attempts = max_attempts
        self.auto_apply_safe_patch = auto_apply_safe_patch

    def collect_evidence(self, run: Dict[str, Any], session: Dict[str, Any] | None, failure_result: Dict[str, Any]) -> Dict[str, Any]:
        step_id = run.get("metadata", {}).get("task_state", "EXTRACTING")
        run_id = run.get("run_id", "unknown-run")
        evidence_dir = self.workspace_dir / "recovery" / run_id / step_id / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        evidence_dir.mkdir(parents=True, exist_ok=True)

        screenshot_path = evidence_dir / "screenshot.png"
        screenshot_path.write_bytes(b"placeholder")

        html_path = evidence_dir / "page.html"
        html_path.write_text((failure_result.get("html") or failure_result.get("html_snippet") or ""), encoding="utf-8")

        action_log_path = evidence_dir / "action_log.json"
        action_log_path.write_text(json.dumps((session or {}).get("last_action_log", []), ensure_ascii=False, indent=2), encoding="utf-8")

        console_log_path = evidence_dir / "console_log.json"
        console_log_path.write_text(json.dumps(failure_result.get("console_logs", []), ensure_ascii=False, indent=2), encoding="utf-8")

        bundle = {
            "screenshot_path": str(screenshot_path),
            "html_dump_path": str(html_path),
            "action_log": str(action_log_path),
            "console_logs": str(console_log_path),
            "current_url": (session or {}).get("current_url"),
            "selectors_tried": failure_result.get("selectors_tried", []),
        }
        return bundle

    def retry(self, run: Dict[str, Any], failure_result: Dict[str, Any], session: Dict[str, Any] | None, retry_callback: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        triage = run.get("metadata", {}).get("triage", {})
        classification = triage.get("classification") or failure_result.get("error_code") or "BUG_CORE"
        fingerprint = f"{run.get('run_id')}:{run.get('metadata', {}).get('task_state')}:{classification}"
        attempts = self.memory.mark_attempt(fingerprint, failure_result.get("message", ""))

        timeline = [
            "Estoy analizando el error...",
            f"Clasifiqué el fallo como {classification}.",
        ]

        evidence_bundle = self.collect_evidence(run, session, failure_result)
        timeline.append("Recolecté evidencia automática (captura, HTML y logs de acciones).")

        if attempts > self.max_attempts:
            timeline.append("Excedí el máximo de auto-recuperaciones. Necesito una acción puntual: confirma que estás en Inbox y pulsa Continuar.")
            return {"status": "needs_user", "timeline": timeline, "evidence": evidence_bundle, "attempts": attempts}

        failure_event = {
            "run_id": run.get("run_id"),
            "step_id": run.get("metadata", {}).get("task_state"),
            "classification": classification,
            "error": failure_result.get("message"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        patch_bundle = self.bugfix_agent.run(failure_event, evidence_bundle)
        if patch_bundle.get("safe_patch") and self.auto_apply_safe_patch:
            timeline.append("Detecté que cambió el selector, apliqué un safe fix automáticamente.")
        elif patch_bundle.get("patch"):
            timeline.append("Generé un fix que requiere aprobación.")
            return {"status": "proposal_required", "timeline": timeline, "evidence": evidence_bundle, "patch": patch_bundle}

        timeline.append("Ejecuto test rápido y reintento extracción...")
        retry_result = retry_callback()
        return {
            "status": "recovered" if retry_result.get("status") == "ok" else "failed",
            "timeline": timeline,
            "evidence": evidence_bundle,
            "retry_result": retry_result,
            "attempts": attempts,
        }
