import sqlite3, os, json, time
from typing import Any, Optional, Dict, List

class Memory:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self._init()
    def _conn(self):
        return sqlite3.connect(self.path)
    def _init(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT NOT NULL, updated_at REAL NOT NULL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS proposals(
                proposal_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                file_path TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL
            )""")
            c.commit()
    def set_json(self, k: str, v: Any):
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO kv(k,v,updated_at) VALUES(?,?,?)", (k, json.dumps(v, ensure_ascii=False), time.time()))
            c.commit()
    def get_json(self, k: str) -> Optional[Any]:
        with self._conn() as c:
            row = c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
            return json.loads(row[0]) if row else None
    def save_proposal(self, proposal_id: str, title: str, file_path: str, content: str):
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO proposals(proposal_id,title,file_path,content,status,created_at) VALUES(?,?,?,?,?,?)",
                      (proposal_id, title, file_path, content, "proposed", time.time()))
            c.commit()
    def list_proposals(self) -> List[Dict]:
        with self._conn() as c:
            rows = c.execute("SELECT proposal_id,title,file_path,status,created_at FROM proposals WHERE status='proposed' ORDER BY created_at DESC").fetchall()
            return [{"proposal_id":r[0],"title":r[1],"file_path":r[2],"status":r[3],"created_at":r[4]} for r in rows]
    def get_proposal(self, proposal_id: str) -> Optional[Dict]:
        with self._conn() as c:
            row = c.execute("SELECT proposal_id,title,file_path,content,status FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
            if not row: return None
            return {"proposal_id":row[0],"title":row[1],"file_path":row[2],"content":row[3],"status":row[4]}
    def set_proposal_status(self, proposal_id: str, status: str):
        with self._conn() as c:
            c.execute("UPDATE proposals SET status=? WHERE proposal_id=?", (status, proposal_id))
            c.commit()
