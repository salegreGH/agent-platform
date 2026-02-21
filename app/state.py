import os, yaml
from typing import Dict, Any, List
from .skills import load_skills

def load_agents(repo_root: str) -> List[Dict[str,Any]]:
    p = os.path.join(repo_root, "data", "agents.yml")
    if not os.path.exists(p): return []
    with open(p, "r", encoding="utf-8") as f:
        d = yaml.safe_load(f) or {}
    agents = d.get("agents") or []
    for a in agents:
        a["status"] = "ready"
    return agents

def load_skills_state(repo_root: str) -> List[Dict[str,Any]]:
    skills = load_skills(os.path.join(repo_root,"data","skills"))
    return [{"id": s.get("id"), "title": s.get("title"), "action": s.get("action")} for s in skills]
