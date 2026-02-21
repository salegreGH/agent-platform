from pathlib import Path

import pytest

from app.core.paths import WorkspacePaths


def test_safe_join_stays_inside_workspace(tmp_path: Path):
    paths = WorkspacePaths(
        base=tmp_path,
        generated_tools=tmp_path / "generated_tools",
        generated_skills=tmp_path / "generated_skills",
        logs=tmp_path / "logs",
        cache=tmp_path / "cache",
        msal_cache=tmp_path / "msal_cache",
        memory_db=tmp_path / "memory.db",
    )
    paths.ensure_exists()
    candidate = paths.safe_join(paths.base, "generated_tools/tool.py")
    assert str(candidate).startswith(str(tmp_path.resolve()))


def test_safe_join_blocks_escape(tmp_path: Path):
    paths = WorkspacePaths(
        base=tmp_path,
        generated_tools=tmp_path / "generated_tools",
        generated_skills=tmp_path / "generated_skills",
        logs=tmp_path / "logs",
        cache=tmp_path / "cache",
        msal_cache=tmp_path / "msal_cache",
        memory_db=tmp_path / "memory.db",
    )
    with pytest.raises(PermissionError):
        paths.safe_join(paths.base, "../outside/file.py")
