import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional


class Memory:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self._init()

    def _conn(self):
        return sqlite3.connect(self.path)

    def _init(self):
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT NOT NULL, updated_at REAL NOT NULL)"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS proposals(
                proposal_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                file_path TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL
            )"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS loop_guard(
                fingerprint TEXT PRIMARY KEY,
                attempts INTEGER NOT NULL,
                last_error TEXT,
                updated_at REAL NOT NULL
            )"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS tasks(
                task_id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                status TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS forms(
                form_id TEXT PRIMARY KEY,
                form_type TEXT NOT NULL,
                status TEXT NOT NULL,
                schema_json TEXT NOT NULL,
                values_json TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )"""
            )
            c.commit()

    def set_json(self, k: str, v: Any):
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO kv(k,v,updated_at) VALUES(?,?,?)",
                (k, json.dumps(v, ensure_ascii=False), time.time()),
            )
            c.commit()

    def get_json(self, k: str) -> Optional[Any]:
        with self._conn() as c:
            row = c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
            return json.loads(row[0]) if row else None

    def save_proposal(self, proposal_id: str, title: str, file_path: str, content: str):
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO proposals(proposal_id,title,file_path,content,status,created_at) VALUES(?,?,?,?,?,?)",
                (proposal_id, title, file_path, content, "proposed", time.time()),
            )
            c.commit()

    def list_proposals(self) -> List[Dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT proposal_id,title,file_path,status,created_at FROM proposals ORDER BY created_at DESC"
            ).fetchall()
            return [
                {
                    "proposal_id": r[0],
                    "title": r[1],
                    "file_path": r[2],
                    "status": r[3],
                    "created_at": r[4],
                }
                for r in rows
            ]

    def get_proposal(self, proposal_id: str) -> Optional[Dict]:
        with self._conn() as c:
            row = c.execute(
                "SELECT proposal_id,title,file_path,content,status FROM proposals WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "proposal_id": row[0],
                "title": row[1],
                "file_path": row[2],
                "content": row[3],
                "status": row[4],
            }

    def set_proposal_status(self, proposal_id: str, status: str):
        with self._conn() as c:
            c.execute("UPDATE proposals SET status=? WHERE proposal_id=?", (status, proposal_id))
            c.commit()

    def save_task(self, task_id: str, goal: str, status: str, payload: Dict[str, Any]):
        ts = time.time()
        body = json.dumps(payload, ensure_ascii=False)
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO tasks(task_id,goal,status,payload,created_at,updated_at) VALUES(?,?,?,?,COALESCE((SELECT created_at FROM tasks WHERE task_id=?),?),?)",
                (task_id, goal, status, body, task_id, ts, ts),
            )
            c.commit()

    def list_tasks(self) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT task_id,goal,status,payload,updated_at FROM tasks ORDER BY updated_at DESC LIMIT 100").fetchall()
            return [
                {"task_id": r[0], "goal": r[1], "status": r[2], "payload": json.loads(r[3] or "{}"), "updated_at": r[4]}
                for r in rows
            ]

    def upsert_form(self, form_id: str, form_type: str, status: str, schema: Dict[str, Any], values: Optional[Dict[str, Any]] = None):
        ts = time.time()
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO forms(form_id,form_type,status,schema_json,values_json,created_at,updated_at) VALUES(?,?,?,?,?,COALESCE((SELECT created_at FROM forms WHERE form_id=?),?),?)",
                (
                    form_id,
                    form_type,
                    status,
                    json.dumps(schema, ensure_ascii=False),
                    json.dumps(values, ensure_ascii=False) if values is not None else None,
                    form_id,
                    ts,
                    ts,
                ),
            )
            c.commit()

    def get_form(self, form_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as c:
            row = c.execute("SELECT form_id,form_type,status,schema_json,values_json FROM forms WHERE form_id=?", (form_id,)).fetchone()
            if not row:
                return None
            return {
                "form_id": row[0],
                "form_type": row[1],
                "status": row[2],
                "schema": json.loads(row[3] or "{}"),
                "values": json.loads(row[4]) if row[4] else None,
            }

    def list_forms(self) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT form_id,form_type,status,schema_json,values_json,updated_at FROM forms ORDER BY updated_at DESC").fetchall()
            return [
                {
                    "form_id": r[0],
                    "form_type": r[1],
                    "status": r[2],
                    "schema": json.loads(r[3] or "{}"),
                    "values": json.loads(r[4]) if r[4] else None,
                    "updated_at": r[5],
                }
                for r in rows
            ]

    def mark_attempt(self, fingerprint: str, error: str = "") -> int:
        with self._conn() as c:
            row = c.execute("SELECT attempts FROM loop_guard WHERE fingerprint=?", (fingerprint,)).fetchone()
            attempts = (row[0] if row else 0) + 1
            c.execute(
                "INSERT OR REPLACE INTO loop_guard(fingerprint,attempts,last_error,updated_at) VALUES(?,?,?,?)",
                (fingerprint, attempts, error, time.time()),
            )
            c.commit()
            return attempts

    def get_attempts(self, fingerprint: str) -> int:
        with self._conn() as c:
            row = c.execute("SELECT attempts FROM loop_guard WHERE fingerprint=?", (fingerprint,)).fetchone()
            return int(row[0]) if row else 0
