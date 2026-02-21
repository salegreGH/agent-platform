import os
import uuid
import yaml
from typing import Dict, Any

from .skills import load_skills, match_skill
from .llm import propose_skill, quick_check
from .generated_tools import execute_tool
from .agents.m365_email_agent import M365EmailAgent


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

        skills = load_skills(self.skills_dir)
        skill = match_skill(user_text, skills)

        # -------------------------------------------------------
        # 1) NO SKILL → PROPOSAL (auto-evolució)
        # -------------------------------------------------------
        if not skill:
            proposal = propose_skill(user_text)
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
                "reply": (
                    "No tinc una skill per això.\n\n"
                    "He generat una proposta perquè la plataforma evolucioni.\n"
                    "Revisa-la i aprova-la a la sidebar (Proposals)."
                ),
                "cards": [
                    {
                        "proposal_id": proposal_id,
                        "title": proposal["title"],
                        "bundle_preview": bundle
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
                        "Per accedir a Outlook necessito configurar Microsoft Graph.\n\n"
                        "Envia les dades així:\n\n"
                        "tenant_id=...\n"
                        "client_id=...\n"
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

            pending = self.memory.get_json("pending_questions") or {}

            if pending.get("kind") == "m365" and (
                "tenant_id=" in user_text or "client_id=" in user_text
            ):
                answers = {}
                for line in user_text.splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        answers[k.strip()] = v.strip()

                self.m365.set_config(answers)
                self.memory.set_json("pending_questions", None)

                return {
                    "reply": "✅ Configuració guardada. Torna a demanar l'últim email."
                }

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
                        "📩 Últim email:\n\n"
                        f"From: {email.get('from')}\n"
                        f"Subject: {email.get('subject')}\n"
                        f"Date: {email.get('receivedDateTime')}\n"
                        f"Preview: {email.get('bodyPreview')}"
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
        abs_skill = os.path.join(self.repo_root, proposal["file_path"])
        os.makedirs(os.path.dirname(abs_skill), exist_ok=True)

        with open(abs_skill, "w", encoding="utf-8") as f:
            yaml.safe_dump(skill, f, sort_keys=False, allow_unicode=True)

        # Write tool
        tool_rel = skill.get("tool_path")

        if tool_rel:
            abs_tool = os.path.join(self.repo_root, tool_rel)
            os.makedirs(os.path.dirname(abs_tool), exist_ok=True)

            with open(abs_tool, "w", encoding="utf-8") as f:
                f.write(tool_stub + "\n")

        self.memory.set_proposal_status(proposal_id, "applied")

        return {"ok": True}