import os
import base64
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agents.m365_email_agent import M365EmailAgent
from .core.logging import configure_logging
from .core.paths import WorkspacePaths
from .memory import Memory
from .orchestrator import Orchestrator
from .platform.core_runtime import CoreRuntimeService
from .platform.evolver import EvolverService
from .platform.policy import PolicyEngine, SecurityPolicyAgent
from .platform.registry import AgentRegistry, ToolRegistry
from .platform.contracts import AgentContract
from .state import load_skills_state
from .tools.secrets import set_secret

APP_PORT = int(os.getenv("AGENT_PLATFORM_PORT", "8787"))
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKSPACE = WorkspacePaths.from_env()
configure_logging(WORKSPACE.logs)

memory = Memory(str(WORKSPACE.memory_db))
m365 = M365EmailAgent(memory, cache_dir=str(WORKSPACE.msal_cache))

tool_registry = ToolRegistry()
agent_registry = AgentRegistry()
agent_registry.register(AgentContract(id="orchestrator", name="OrchestratorAgent", purpose="Control plane coordinator", capabilities=["classify", "delegate"]))
agent_registry.register(AgentContract(id="planner", name="PlannerAgent", purpose="Task graph planning", capabilities=["task_graph"]))
agent_registry.register(AgentContract(id="triage", name="TriageAgent", purpose="Anti-loop diagnostics", capabilities=["classify_error", "anti_loop"]))
agent_registry.register(AgentContract(id="m365_outlook", name="M365OutlookAgent", purpose="Outlook connector", capabilities=["get_latest_email", "list_important_unreplied", "draft_reply", "send_email"]))

policy_engine = PolicyEngine(allowed_write_roots=[WORKSPACE.root, WORKSPACE.workspace])
security_agent = SecurityPolicyAgent(policy_engine)

core_runtime = CoreRuntimeService(memory, m365, tool_registry)
evolver = EvolverService(memory, WORKSPACE)
orch = Orchestrator(memory, repo_root=REPO_ROOT, core_runtime=core_runtime, evolver=evolver, security=security_agent)

app = FastAPI(title="Agent Platform v5", version="0.5")
app.mount("/ui", StaticFiles(directory=os.path.join(REPO_ROOT, "ui")), name="ui")


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(REPO_ROOT, "ui", "index.html"), "r", encoding="utf-8") as f:
        return f.read()


class KeyReq(BaseModel):
    api_key: str


class ChatReq(BaseModel):
    message: str


class ApproveReq(BaseModel):
    proposal_id: str


class FormSubmitReq(BaseModel):
    values: dict


class UploadReq(BaseModel):
    filename: str
    content_base64: str


@app.post("/api/settings/openai_key")
def save_key(req: KeyReq):
    try:
        set_secret("OPENAI_API_KEY", req.api_key.strip())
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/state")
def state():
    return {
        "agents": agent_registry.list(),
        "skills": load_skills_state(str(WORKSPACE.generated_skills)),
        "proposals": memory.list_proposals(),
        "tasks": memory.list_tasks(),
        "forms": memory.list_forms(),
        "connectors": core_runtime.connectors_status(),
        "configs": {"workspace": str(WORKSPACE.root)},
    }


@app.get("/api/logs")
def logs():
    log_file = WORKSPACE.logs / "agent-platform.log"
    if not log_file.exists():
        return {"ok": True, "content": ""}
    return {"ok": True, "content": log_file.read_text(encoding="utf-8")[-20000:]}


@app.post("/api/chat")
def chat(req: ChatReq):
    try:
        return orch.run(req.message)
    except Exception as e:
        return JSONResponse(status_code=200, content={"reply": f"❌ Error: {e}"})


@app.post("/api/proposals/approve")
def approve(req: ApproveReq):
    return orch.approve_proposal(req.proposal_id)


# Evolver service API
@app.get("/api/evolver/state")
def evolver_state():
    return {"ok": True, "core": "running", "workspace": str(WORKSPACE.root), "release": memory.get_json("release.last")}


@app.post("/api/evolve/rollback")
def evolve_rollback():
    return evolver.rollback_last()


@app.post("/api/forms/{form_id}/submit")
def forms_submit(form_id: str, req: FormSubmitReq):
    memory.upsert_form(form_id, "m365_config", "submitted", memory.get_form(form_id).get("schema", {}), req.values)
    m365.set_config(req.values)
    return {"ok": True}


@app.post("/api/uploads")
def upload_file(req: UploadReq):
    target = WORKSPACE.attachments / Path(req.filename or "upload.bin").name
    payload = base64.b64decode(req.content_base64.encode("utf-8"))
    target.write_bytes(payload)
    return {"ok": True, "path": str(target), "name": target.name}


# Core runtime API
@app.post("/core/execute")
def core_execute(req: ChatReq):
    return core_runtime.execute({"message": req.message})


@app.get("/core/tools")
def core_tools():
    return {"tools": tool_registry.list()}


@app.get("/core/connectors")
def core_connectors():
    return core_runtime.connectors_status()


@app.get("/core/memory")
def core_memory():
    return {"tasks": memory.list_tasks(), "forms": memory.list_forms()}


@app.get("/core/health")
def core_health():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=APP_PORT, reload=False)
