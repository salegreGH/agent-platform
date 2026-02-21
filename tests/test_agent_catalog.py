from app.main import agent_registry


def test_agent_catalog_includes_multi_agent_roles():
    ids = {a["id"] for a in agent_registry.list()}
    expected = {
        "orchestrator",
        "planner",
        "triage",
        "dev",
        "test",
        "release",
        "security",
        "knowledge",
        "m365_outlook",
        "teams",
        "sharepoint",
        "jira",
        "clockify",
        "local_office",
        "filesystem",
        "browser",
    }
    assert expected.issubset(ids)
