from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class BugFixAgent:
    def __init__(self, selectors_path: Path):
        self.selectors_path = selectors_path

    def run(self, failure_event: Dict[str, Any], evidence_bundle: Dict[str, Any]) -> Dict[str, Any]:
        classification = failure_event.get("classification", "BUG_CORE")
        if classification != "SELECTOR_BROKE":
            return {"actions": [], "patch": None, "safe_patch": False, "summary": "No selector-safe patch available."}

        selectors = json.loads(self.selectors_path.read_text(encoding="utf-8"))
        changed = False
        field_patterns = selectors.setdefault("field_patterns", {})
        fallback_patterns = {
            "subject": r"<title>([^<]+)</title>",
            "from": r"data-testid=[\"']message-from[\"'][^>]*>([^<]+)<",
            "received_at": r"datetime=[\"']([^\"']+)[\"']",
            "preview": r"data-testid=[\"']message-preview[\"'][^>]*>([^<]+)<",
        }
        for field, pattern in fallback_patterns.items():
            current = field_patterns.setdefault(field, [])
            if pattern not in current:
                current.append(pattern)
                changed = True

        if not changed:
            return {
                "actions": ["Selector fallback already present"],
                "patch": None,
                "safe_patch": False,
                "summary": "Selector set already contains fallback patterns.",
            }

        selectors["version"] = int(selectors.get("version", 1)) + 1
        self.selectors_path.write_text(json.dumps(selectors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {
            "actions": ["Updated data/browser_selectors/outlook.json with fallback patterns."],
            "safe_patch": True,
            "patch": {"file": str(self.selectors_path), "type": "selectors_json"},
            "summary": "Applied safe selector patch.",
        }
