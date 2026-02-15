"""Tests for tool auto-discovery and collection."""

from skippy.tools import collect_tools


def test_collect_tools_returns_list():
    """collect_tools should return a non-empty list."""
    tools = collect_tools()
    assert isinstance(tools, list)
    assert len(tools) > 0


def test_collect_tools_count():
    """Should load all expected tools (41 per README)."""
    tools = collect_tools()
    # Allow some flexibility if tools are disabled by missing config
    assert len(tools) >= 30, f"Expected 30+ tools, got {len(tools)}"


def test_all_tools_have_names():
    """Every tool should have a name attribute."""
    tools = collect_tools()
    for t in tools:
        assert hasattr(t, "name"), f"Tool missing name: {t}"
        assert t.name, f"Tool has empty name: {t}"
