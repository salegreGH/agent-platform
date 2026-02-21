from pathlib import Path

import yaml

from app.core.paths import WorkspacePaths
from app.memory import Memory
from app.platform.evolver import EvolverService


def build_paths(tmp_path: Path) -> WorkspacePaths:
    return WorkspacePaths(
        root=tmp_path,
        workspace=tmp_path / "workspace",
        generated_tools=tmp_path / "workspace" / "generated_tools",
        generated_skills=tmp_path / "workspace" / "generated_skills",
        logs=tmp_path / "logs",
        cache=tmp_path / "cache",
        msal_cache=tmp_path / "msal_cache",
        secrets=tmp_path / "secrets",
        proposals=tmp_path / "proposals",
        artifacts=tmp_path / "artifacts",
        attachments=tmp_path / "attachments",
        memory_db=tmp_path / "memory.db",
    )


def test_apply_proposal_writes_inside_workspace(tmp_path: Path):
    paths = build_paths(tmp_path)
    paths.ensure_exists()
    memory = Memory(str(paths.memory_db))
    evolver = EvolverService(memory=memory, workspace_paths=paths)

    proposal_id = "abc123"
    bundle = {
        "skill": {
            "id": "hello",
            "title": "Hello",
            "triggers": ["hello"],
            "requires": [],
            "action": "generated_action",
            "tool_path": "generated_tools/hello.py",
        },
        "tool_stub": "def execute(ctx):\n    return {'status': 'ok'}",
    }
    memory.save_proposal(proposal_id, "hello", "generated_skills/hello.yml", yaml.safe_dump(bundle))

    result = evolver.apply_proposal(proposal_id)

    assert result["ok"] is True
    assert (paths.generated_skills / "hello.yml").exists()
    assert (paths.generated_tools / "hello.py").exists()


def test_apply_proposal_rejects_outside_workspace(tmp_path: Path):
    paths = build_paths(tmp_path)
    paths.ensure_exists()
    memory = Memory(str(paths.memory_db))
    evolver = EvolverService(memory=memory, workspace_paths=paths)

    proposal_id = "outside1"
    bundle = {
        "skill": {
            "id": "bad",
            "title": "bad",
            "triggers": ["bad"],
            "requires": [],
            "action": "generated_action",
            "tool_path": "../evil.py",
        },
        "tool_stub": "print('nope')",
    }
    memory.save_proposal(proposal_id, "bad", "../evil.yml", yaml.safe_dump(bundle))

    result = evolver.apply_proposal(proposal_id)
    assert result["ok"] is False
