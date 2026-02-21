import json
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

def propose_skill(user_text: str) -> dict:
    client = _client()
    schema = {
        "type":"object",
        "properties":{
            "id":{"type":"string"},
            "title":{"type":"string"},
            "triggers":{"type":"array","items":{"type":"string"}},
            "requires":{"type":"array","items":{"type":"string"}},
            "action":{"type":"string"},
            "tool_file":{"type":"string"},
            "tool_stub":{"type":"string"}
        },
        "required":["id","title","triggers","requires","action","tool_file","tool_stub"],
        "additionalProperties": False
    }
    last = None
    for model in DEFAULT_MODELS:
        try:
            r = client.responses.create(
                model=model,
                input=[
                    {"role":"system","content":"Proposa UNA skill nova. Si és Outlook posa requires ['m365_email']. Action ha de ser un nom python_snake_case. tool_file és un nom .py. tool_stub és codi python amb funció execute(ctx)->dict."},
                    {"role":"user","content": user_text}
                ],
                text={"format":{"type":"json_schema","name":"skill","schema": schema}},
                max_output_tokens=700
            )
            return json.loads(r.output_text)
        except Exception as e:
            last = str(e)
    raise RuntimeError(last or "LLM error")
