import os
import re
import uuid
import yaml
from typing import Dict, Any

from .skills import load_skills, match_skill
from .llm import propose_skill, quick_check
from .generated_tools import execute_tool
from .agents.m365_email_agent import M365EmailAgent
from .state import load_agents


class Orchestrator:

    def __init__(self, memory, repo_root: str):
        self.memory = memory
        self.repo_root = repo_root
        self.data_dir = os.path.join(repo_root, "data")
        self.skills_dir = os.path.join(self.data_dir, "skills")
        self.tools_dir = os.path.join(self.data_dir, "generated_tools")

        os.makedirs(self.skills_dir, exist_ok=True)
        os.makedirs(self.tools_dir, exist_ok=True)

        self.m365 = M365EmailAgent(memory, data_dir=os.path.join(self.data_dir, "m365"))

    def run(self, user_text: str) -> Dict[str, Any]:

        pending = self.memory.get_json("pending_questions") or {}
        if pending.get("kind") == "m365":
            parsed = self._parse_key_values(user_text)
            expected_keys = {q.get("key") for q in (pending.get("questions") or [])}
            if expected_keys.intersection(parsed.keys()):
                self.m365.set_config(parsed)
                self.memory.set_json("pending_questions", None)
                return {
                    "reply": "Perfecte, ja he guardat la configuració de forma segura. Ara ja pots tornar-me a demanar qualsevol tasca d'Outlook.",
                    "cards": []
                }

        skills = load_skills(self.skills_dir)
        skill = match_skill(user_text, skills)

        # -------------------------------------------------------
        # 1) NO SKILL → PROPOSAL (auto-evolució)
        # -------------------------------------------------------
        if not skill:
            runtime_context = {
                "agents": load_agents(self.repo_root),
                "skills": [{"id": s.get("id"), "action": s.get("action")} for s in skills],
                "pending_questions": pending,
            }
            proposal = propose_skill(user_text, repo_root=self.repo_root, runtime_context=runtime_context)
            proposal_id = str(uuid.uuid4())[:8]

            skill_file = os.path.join("data", "skills", f"{proposal['id']}.yml")
            tool_file = os.path.join("data", "generated_tools", proposal["tool_file"])

            bundle = {
                "skill": {
                    "id": proposal["id"],
                    "title": proposal["title"],
                    "triggers": proposal["triggers"],
                    "requires": proposal["requires"],
                    "action": proposal["action"],
                    "tool_path": tool_file
                },
                "tool_stub": proposal["tool_stub"]
            }

            content = yaml.safe_dump(bundle, sort_keys=False, allow_unicode=True)
            self.memory.save_proposal(proposal_id, proposal["title"], skill_file, content)

            return {
                "reply": proposal.get("assistant_reply") or (
                    "Encara no tinc aquesta capacitat integrada.\n\n"
                    "He preparat una proposta d'evolució i la pots aprovar a la pestanya de Proposals."
                ),
                "cards": [
                    {
                        "proposal_id": proposal_id,
                        "title": proposal["title"],
                        "bundle_preview": bundle,
                        "execution_notes": proposal.get("execution_notes") or []
                    }
                ]
            }

        # -------------------------------------------------------
        # 2) CHECK REQUIRES
        # -------------------------------------------------------
        requires = skill.get("requires") or []

        if "m365_email" in requires:
            questions = self.m365.config_questions()
            if questions:
                self.memory.set_json("pending_questions", {"kind": "m365", "questions": questions})

                return {
                    "reply": (
                        "Per continuar, necessito les dades de Microsoft Graph.\n"
                        "Pots enviar-les en una sola línia, per exemple:\n\n"
                        "tenant_id=... client_id=..."
                    ),
                    "cards": [{"questions": questions}]
                }

        action = skill.get("action")

        # -------------------------------------------------------
        # 3) BUILT-IN ACTIONS
        # -------------------------------------------------------

        if action == "check_openai_connection":
            try:
                result = quick_check()
                return {
                    "reply": f"✅ Sí. Estic connectat al LLM (resposta: {result})."
                }
            except Exception as e:
                return {
                    "reply": f"❌ Error connectant amb l'API OpenAI: {e}"
                }

        if action == "outlook_get_last_email":
            result = self.m365.get_last_email()

            if result.get("status") == "auth_required":
                return {
                    "reply": (
                        "Necessito autorització (device code).\n\n"
                        f"{result.get('message')}"
                    )
                }

            if result.get("status") == "ok":
                email = result.get("email", {})
                return {
                    "reply": (
                        "He trobat l'últim correu de la safata d'entrada:\n\n"
                        f"Remitent: {email.get('from')}\n"
                        f"Assumpte: {email.get('subject')}\n"
                        f"Data: {email.get('receivedDateTime')}\n"
                        f"Resum: {email.get('bodyPreview')}"
                    ),
                    "cards": [result]
                }

            return {"reply": f"❌ Error Outlook: {result}"}

        if action == "outlook_triage_important_unanswered":

            result = self.m365.triage_important_unanswered()

            if result.get("status") == "auth_required":
                return {
                    "reply": (
                        "Necessito autorització (device code).\n\n"
                        f"{result.get('message')}"
                    )
                }

            if result.get("status") == "ok":
                return {
                    "reply": (
                        f"He trobat {result.get('count')} emails potencialment importants."
                    ),
                    "cards": [result]
                }

            return {"reply": f"❌ Error: {result}"}

        # -------------------------------------------------------
        # 4) GENERATED TOOL
        # -------------------------------------------------------

        tool_path = skill.get("tool_path")

        if tool_path:
            abs_tool = os.path.join(self.repo_root, tool_path)
            result = execute_tool(abs_tool, {"user_text": user_text, "skill": skill})

            return {
                "reply": "He executat una skill generada.",
                "cards": [result]
            }

        return {
            "reply": "Skill trobada però no executable encara.",
            "cards": [{"skill": skill}]
        }

    def _parse_key_values(self, text: str) -> Dict[str, str]:
        pairs = re.findall(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([^\s]+)", text)
        return {k.strip(): v.strip() for k, v in pairs}

    def _normalize_rel_path(self, path_value: str | None) -> str:
        if not path_value:
            return ""

        normalized = str(path_value).strip().replace("\\", "/")
        data_idx = normalized.lower().find("data/")
        if data_idx >= 0:
            normalized = normalized[data_idx:]
        else:
            drive_match = re.match(r"^[a-zA-Z]:/", normalized)
            if drive_match:
                normalized = normalized[3:]

        return normalized.lstrip("/")

    # -----------------------------------------------------------
    # APPLY PROPOSAL
    # -----------------------------------------------------------

    def approve_proposal(self, proposal_id: str) -> Dict[str, Any]:

        proposal = self.memory.get_proposal(proposal_id)

        if not proposal:
            return {"ok": False, "error": "Proposal no trobada"}

        if proposal["status"] != "proposed":
            return {"ok": False, "error": f"Estat invàlid: {proposal['status']}"}

        bundle = yaml.safe_load(proposal["content"]) or {}
        skill = bundle.get("skill") or {}
        tool_stub = bundle.get("tool_stub") or ""

        # Write skill
        skill_rel = self._normalize_rel_path(proposal.get("file_path"))
        abs_skill = os.path.join(self.repo_root, skill_rel)
        os.makedirs(os.path.dirname(abs_skill), exist_ok=True)

        with open(abs_skill, "w", encoding="utf-8") as f:
            yaml.safe_dump(skill, f, sort_keys=False, allow_unicode=True)

        # Write tool
        tool_rel = self._normalize_rel_path(skill.get("tool_path"))

        if tool_rel:
            abs_tool = os.path.join(self.repo_root, tool_rel)
            tool_dir = os.path.dirname(abs_tool)
            if tool_dir:
                os.makedirs(tool_dir, exist_ok=True)

            with open(abs_tool, "w", encoding="utf-8") as f:
                f.write(tool_stub + "\n")

        self.memory.set_proposal_status(proposal_id, "applied")

        return {"ok": True}
