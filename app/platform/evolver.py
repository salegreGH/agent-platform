from __future__ import annotations

import hashlib
import os
import shutil
import time
from typing import Any, Dict

import yaml

from ..core.paths import WorkspacePaths
from ..generated_tools import execute_tool
from ..memory import Memory


class EvolverService:
    def __init__(self, memory: Memory, workspace_paths: WorkspacePaths):
        self.memory = memory
        self.workspace_paths = workspace_paths

    def create_proposal(self, title: str, skill_bundle: Dict[str, Any]) -> Dict[str, Any]:
        proposal_id = hashlib.sha1(f"{title}-{time.time()}".encode("utf-8")).hexdigest()[:8]
        skill = skill_bundle["skill"]
        file_path = f"generated_skills/{skill['id']}.yml"
        self.memory.save_proposal(proposal_id, title, file_path, yaml.safe_dump(skill_bundle, allow_unicode=True, sort_keys=False))
        return {"ok": True, "proposal_id": proposal_id}

    def apply_proposal(self, proposal_id: str) -> Dict[str, Any]:
        proposal = self.memory.get_proposal(proposal_id)
        if not proposal:
            return {"ok": False, "error": "Proposal no trobada"}
        if proposal["status"] != "proposed":
            return {"ok": False, "error": f"Estat invàlid: {proposal['status']}"}

        bundle = yaml.safe_load(proposal["content"]) or {}
        skill = bundle.get("skill") or {}
        tool_stub = bundle.get("tool_stub", "")

        try:
            skill_rel = (proposal.get("file_path") or "").lstrip("/").replace("\\", "/")
            abs_skill = self.workspace_paths.safe_join(self.workspace_paths.base, skill_rel)
            abs_skill.parent.mkdir(parents=True, exist_ok=True)
            abs_skill.write_text(yaml.safe_dump(skill, allow_unicode=True, sort_keys=False), encoding="utf-8")

            tool_rel = (skill.get("tool_path") or "").lstrip("/").replace("\\", "/")
            if tool_rel:
                abs_tool = self.workspace_paths.safe_join(self.workspace_paths.base, tool_rel)
                abs_tool.parent.mkdir(parents=True, exist_ok=True)
                abs_tool.write_text(tool_stub + "\n", encoding="utf-8")

            backup_dir = self.workspace_paths.proposals / f"{proposal_id}.backup"
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(abs_skill, backup_dir / os.path.basename(abs_skill))
            self.memory.set_json("release.last", {"proposal_id": proposal_id, "backup_dir": str(backup_dir)})
            self.memory.set_proposal_status(proposal_id, "applied")
            return {"ok": True, "message": "Patch aplicat al workspace i release registrat."}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def rollback_last(self) -> Dict[str, Any]:
        rel = self.memory.get_json("release.last")
        if not rel:
            return {"ok": False, "error": "No hi ha release per rollback."}
        self.memory.set_json("release.last_rollback", {"at": time.time(), "source": rel})
        return {"ok": True, "message": "Rollback registrat (mode MVP)."}

    def run_generated_tool(self, rel_tool_path: str, ctx: Dict[str, Any]):
        abs_tool = self.workspace_paths.safe_join(self.workspace_paths.base, rel_tool_path)
        return execute_tool(str(abs_tool), ctx)
