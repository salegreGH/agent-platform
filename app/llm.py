import json
import os
from openai import OpenAI
from .tools.secrets import get_secret

DEFAULT_MODELS = ["gpt-4.1-mini", "gpt-4o-mini"]

def _client() -> OpenAI:
    k = get_secret("OPENAI_API_KEY")
    if not k:
        raise RuntimeError("Falta OPENAI_API_KEY. Ves a Settings i guarda-la.")
    return OpenAI(api_key=k)

def quick_check() -> str:
    client = _client()
    last = None
    for model in DEFAULT_MODELS:
        try:
            r = client.responses.create(model=model, input=[{"role":"user","content":"Respond només amb 'ok'."}], max_output_tokens=8)
            txt = (r.output_text or "").strip().lower()
            return "ok" if "ok" in txt else (r.output_text or "ok")
        except Exception as e:
            last = str(e)
    raise RuntimeError(last or "LLM error")

def _repository_snapshot(repo_root: str, limit_chars: int = 120_000) -> str:
    chunks = []
    total = 0
    include_ext = {".py", ".yml", ".yaml", ".md", ".html", ".js", ".txt"}

    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".venv", "node_modules"}]
        for name in sorted(files):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, repo_root)

            if rel.startswith("data/generated_tools"):
                continue

            if os.path.splitext(name)[1].lower() not in include_ext:
                continue

            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue

            piece = f"\n--- FILE: {rel} ---\n{content}\n"
            if total + len(piece) > limit_chars:
                remaining = max(0, limit_chars - total)
                if remaining > 200:
                    chunks.append(piece[:remaining])
                return "".join(chunks)

            chunks.append(piece)
            total += len(piece)

    return "".join(chunks)


def propose_skill(user_text: str, repo_root: str, runtime_context: dict | None = None) -> dict:
    client = _client()
    schema = {
        "type":"object",
        "properties":{
            "assistant_reply":{"type":"string"},
            "execution_notes":{"type":"array","items":{"type":"string"},"default":[]},
            "id":{"type":"string"},
            "title":{"type":"string"},
            "triggers":{"type":"array","items":{"type":"string"}},
            "requires":{"type":"array","items":{"type":"string"}},
            "action":{"type":"string"},
            "tool_file":{"type":"string"},
            "tool_stub":{"type":"string"}
        },
        "required":["assistant_reply","execution_notes","id","title","triggers","requires","action","tool_file","tool_stub"],
        "additionalProperties": False
    }
    runtime_context = runtime_context or {}
    context_dump = json.dumps(runtime_context, ensure_ascii=False, indent=2)
    repo_dump = _repository_snapshot(repo_root)
    last = None
    for model in DEFAULT_MODELS:
        try:
            r = client.responses.create(
                model=model,
                input=[
                    {"role":"system","content":"Ets l'arquitecte de la plataforma d'agents. Dona resposta en llenguatge natural i defineix UNA proposta única per la tasca completa (no una proposta per cada pas). La proposta ha d'explicar a l'agent local què ha d'implementar i com s'executa després la tasca amb programari local. Prioritza sempre reutilitzar agents/software locals existents abans d'invocar directament el LLM. Si cal nova capacitat, proposa-la dins la mateixa evolució completa. Si és Outlook posa requires ['m365_email']. Action ha de ser python_snake_case. tool_file ha de ser només nom relatiu .py (sense rutes absolutes) i tool_stub ha de contenir execute(ctx)->dict."},
                    {"role":"system","content":f"Context d'execució actual:\n{context_dump}"},
                    {"role":"system","content":f"Snapshot del repositori:\n{repo_dump}"},
                    {"role":"user","content": user_text}
                ],
                text={"format":{"type":"json_schema","name":"skill","schema": schema}},
                max_output_tokens=700
            )
            return json.loads(r.output_text)
        except Exception as e:
            last = str(e)
    raise RuntimeError(last or "LLM error")
