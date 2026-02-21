import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .memory import Memory
from .tools.secrets import set_secret
from .orchestrator import Orchestrator
from .state import load_agents, load_skills_state

APP_PORT = int(os.getenv("AGENT_PLATFORM_PORT","8787"))
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

memory = Memory(os.path.join(REPO_ROOT, "data", "memory.db"))
orch = Orchestrator(memory, repo_root=REPO_ROOT)

app = FastAPI(title="Agent Platform v4", version="0.4")
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
        "agents": load_agents(REPO_ROOT),
        "skills": load_skills_state(REPO_ROOT),
        "proposals": memory.list_proposals(),
        "configs": {"m365_configured": bool(memory.get_json("m365.config"))}
    }

@app.post("/api/chat")
def chat(req: ChatReq):
    try:
        return orch.run(req.message)
    except Exception as e:
        return JSONResponse(status_code=200, content={"reply": f"❌ Error: {e}"})

@app.post("/api/proposals/approve")
def approve(req: ApproveReq):
    try:
        return orch.approve_proposal(req.proposal_id)
    except Exception as e:
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=APP_PORT, reload=False)
