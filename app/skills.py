import os, yaml
from typing import List, Dict, Optional
def load_skills(skills_dir: str) -> List[Dict]:
    out = []
    if not os.path.isdir(skills_dir): return out
    for fn in os.listdir(skills_dir):
        if fn.endswith(".yml") or fn.endswith(".yaml"):
            p = os.path.join(skills_dir, fn)
            with open(p, "r", encoding="utf-8") as f:
                d = yaml.safe_load(f) or {}
                d["_file"] = p
                out.append(d)
    return out
def match_skill(user_text: str, skills: List[Dict]) -> Optional[Dict]:
    t = user_text.lower()
    best, score = None, 0
    for s in skills:
        triggers = [x.lower() for x in (s.get("triggers") or [])]
        sc = sum(1 for tr in triggers if tr in t)
        if sc > score:
            best, score = s, sc
    return best if score > 0 else None
