import importlib.util
from typing import Dict, Any

def execute_tool(tool_path: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    spec = importlib.util.spec_from_file_location("gen_tool", tool_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No puc carregar tool: {tool_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    if not hasattr(mod, "execute"):
        return {"status":"error","message":"El tool no té funció execute(ctx)."}
    return mod.execute(ctx)  # type: ignore
