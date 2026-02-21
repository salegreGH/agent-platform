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

        core_payload = self.core_runtime.converse(user_text)
        if core_payload.get("reply"):
            return core_payload

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
