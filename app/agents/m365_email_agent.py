\
import os, requests
import msal
from typing import Dict, Any, Optional

GRAPH = "https://graph.microsoft.com/v1.0"

class M365EmailAgent:
    def __init__(self, memory, data_dir: str):
        self.memory = memory
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.cache_path = os.path.join(self.data_dir, "msal_cache.json")

    def _load_cache(self) -> msal.SerializableTokenCache:
        cache = msal.SerializableTokenCache()
        if os.path.exists(self.cache_path):
            try:
                cache.deserialize(open(self.cache_path, "r", encoding="utf-8").read())
            except Exception:
                pass
        return cache

    def _save_cache(self, cache: msal.SerializableTokenCache):
        if cache.has_state_changed:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                f.write(cache.serialize())

    def _get_cfg(self) -> Optional[Dict[str, Any]]:
        return self.memory.get_json("m365.config")

    def config_questions(self):
        cfg = self._get_cfg()
        if cfg and cfg.get("tenant_id") and cfg.get("client_id"):
            return []
        return [
            {"key":"tenant_id","question":"Tenant ID (GUID) o 'common' si no el saps","placeholder":"xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"},
            {"key":"client_id","question":"Client ID de l'App Registration","placeholder":"xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"},
        ]

    def set_config(self, answers: Dict[str,str]):
        cfg = self._get_cfg() or {}
        cfg["tenant_id"] = (answers.get("tenant_id") or "").strip()
        cfg["client_id"] = (answers.get("client_id") or "").strip()
        cfg["scopes"] = cfg.get("scopes") or ["Mail.Read"]
        cfg["auth_mode"] = "device_code"
        self.memory.set_json("m365.config", cfg)
        return cfg

    def _acquire_token(self) -> Dict[str, Any]:
        cfg = self._get_cfg()
        if not cfg:
            return {"ok": False, "error": "missing_config"}
        tenant = cfg["tenant_id"]
        client_id = cfg["client_id"]
        scopes = cfg.get("scopes") or ["Mail.Read"]

        cache = self._load_cache()
        app = msal.PublicClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant}",
            token_cache=cache
        )

        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(scopes, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache(cache)
                return {"ok": True, "token": result["access_token"]}

        flow = app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            return {"ok": False, "error": "device_flow_failed", "details": flow}

        self._save_cache(cache)
        return {"ok": False, "error": "needs_device_code", "message": flow.get("message")}

    def get_last_email(self) -> Dict[str, Any]:
        tok = self._acquire_token()
        if not tok.get("ok"):
            if tok.get("error") == "needs_device_code":
                return {"status":"auth_required","message": tok.get("message")}
            return {"status":"error","error": tok}

        headers = {"Authorization": f"Bearer {tok['token']}"}
        url = GRAPH + "/me/messages?$top=1&$orderby=receivedDateTime%20desc&$select=subject,from,receivedDateTime,bodyPreview,isRead"
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            return {"status":"error","http": r.status_code, "body": r.text}
        items = (r.json() or {}).get("value", [])
        if not items:
            return {"status":"ok","message":"No he trobat emails."}
        m = items[0]
        return {"status":"ok","email":{
            "subject": m.get("subject"),
            "from": (m.get("from") or {}).get("emailAddress", {}),
            "receivedDateTime": m.get("receivedDateTime"),
            "bodyPreview": m.get("bodyPreview"),
            "isRead": m.get("isRead"),
        }}

    def triage_important_unanswered(self) -> Dict[str, Any]:
        tok = self._acquire_token()
        if not tok.get("ok"):
            if tok.get("error") == "needs_device_code":
                return {"status":"auth_required","message": tok.get("message")}
            return {"status":"error","error": tok}

        headers = {"Authorization": f"Bearer {tok['token']}"}
        url = GRAPH + "/me/messages?$top=50&$orderby=receivedDateTime%20desc&$select=subject,from,receivedDateTime,bodyPreview,isRead,importance"
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            return {"status":"error","http": r.status_code, "body": r.text}
        items = (r.json() or {}).get("value", [])
        keywords = ["urgent","asap","important","factura","invoice","bloquejat","blocked","revisar","review","prioritat","deadline"]
        scored = []
        for m in items:
            if m.get("isRead") is True:
                continue
            text = f"{m.get('subject','')} {m.get('bodyPreview','')}".lower()
            score = sum(1 for k in keywords if k in text)
            if (m.get("importance","normal") or "normal").lower() == "high":
                score += 2
            if score <= 0:
                continue
            scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [m for _, m in scored[:10]]
        return {"status":"ok","count": len(top),"emails":[{
            "subject": m.get("subject"),
            "from": (m.get("from") or {}).get("emailAddress", {}),
            "receivedDateTime": m.get("receivedDateTime"),
            "bodyPreview": m.get("bodyPreview"),
            "importance": m.get("importance"),
        } for m in top]}
