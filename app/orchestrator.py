import logging
from typing import Any, Dict

from .llm import propose_skill, quick_check
from .platform.core_runtime import CoreRuntimeService
from .platform.evolver import EvolverService
from .platform.policy import SecurityPolicyAgent
from .state import load_agents


class Orchestrator:
    def __init__(self, memory, repo_root: str, core_runtime: CoreRuntimeService, evolver: EvolverService, security: SecurityPolicyAgent):
        self.memory = memory
        self.repo_root = repo_root
        self.core_runtime = core_runtime
        self.evolver = evolver
        self.security = security
        self.log = logging.getLogger("orchestrator")

    def run(self, user_text: str) -> Dict[str, Any]:
        if "connex" in user_text.lower() and "openai" in user_text.lower():
            try:
                result = quick_check()
                return {"reply": f"✅ Sí. Estic connectat al LLM (resposta: {result})."}
            except Exception as e:
                return {"reply": f"❌ Error connectant amb l'API OpenAI: {e}"}

        core_payload = self.core_runtime.execute({"message": user_text})
        result = core_payload.get("result") or {}

        if result.get("status") == "needs_form":
            form_id = "m365_config_form"
            self.memory.upsert_form(form_id, "m365_config", "pending", {"fields": result.get("fields", [])})
            return {
                "reply": "Per continuar necessito dades de Microsoft 365. Omple el formulari de Connectors i tornaré a provar automàticament.",
                "cards": [{"form_id": form_id, "questions": result.get("fields", [])}],
            }

        if result.get("status") == "auth_required":
            loop_guard = core_payload.get("loop_guard") or {}
            attempts = int(loop_guard.get("attempts") or 1)

            if attempts >= 2:
                fallback = self.core_runtime.suggest_outlook_fallback(user_text)
                fallback_steps = "\n".join(f"- {step}" for step in (fallback.get("next_steps") or fallback.get("alternatives") or []))
                reply = (
                    "He detectat que l'autorització de Outlook està en bucle i canvio d'estratègia automàticament.\n\n"
                    f"Intentos detectats: {attempts}.\n"
                    f"Estratègia alternativa: {fallback.get('strategy', 'manual_recovery')}.\n"
                    f"{fallback.get('message', '')}\n\n"
                    "Passos següents:\n"
                    f"{fallback_steps}"
                )
                return {"reply": reply, "cards": [core_payload, {"fallback": fallback}]}

            return {
                "reply": (
                    "Necessito autorització (device code).\n\n"
                    f"{result.get('message')}\n\n"
                    "Si aquest pas falla, aplicaré fallback automàtic (browser/manual) per evitar repetir el mateix bloqueig."
                )
            }

        if result.get("status") == "ok" and result.get("email"):
            email = result["email"]
            return {
                "reply": (
                    "He trobat l'últim correu de la safata d'entrada:\n\n"
                    f"Remitent: {email.get('from')}\nAssumpte: {email.get('subject')}\n"
                    f"Data: {email.get('receivedDateTime')}\nResum: {email.get('bodyPreview')}"
                ),
                "cards": [core_payload],
            }

        if result.get("status") == "ok" and result.get("emails") is not None:
            return {"reply": f"He prioritzat {result.get('count')} emails importants sense resposta.", "cards": [core_payload]}

        # capability gap -> evolution proposal
        runtime_context = {
            "agents": load_agents(self.repo_root),
            "connectors": self.core_runtime.connectors_status(),
        }
        proposal = propose_skill(user_text, repo_root=self.repo_root, runtime_context=runtime_context)
        bundle = {
            "skill": {
                "id": proposal["id"],
                "title": proposal["title"],
                "triggers": proposal["triggers"],
                "requires": proposal["requires"],
                "action": proposal["action"],
                "tool_path": f"generated_tools/{proposal['tool_file']}",
            },
            "tool_stub": proposal["tool_stub"],
        }
        created = self.evolver.create_proposal(proposal["title"], bundle)
        return {
            "reply": proposal.get("assistant_reply") or "He creat una proposta d'evolució.",
            "cards": [{"proposal_id": created.get("proposal_id"), "title": proposal["title"], "execution_notes": proposal.get("execution_notes", [])}],
        }

    def approve_proposal(self, proposal_id: str) -> Dict[str, Any]:
        return self.evolver.apply_proposal(proposal_id)
