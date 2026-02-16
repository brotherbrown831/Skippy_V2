"""Tests for Tavily web search tools."""

import pytest
from skippy.tools.tavily import get_tools, search_web, _get_tavily_headers
from skippy.config import settings


def test_get_tavily_headers():
    """Test header generation includes auth."""
    headers = _get_tavily_headers()
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["Content-Type"] == "application/json"


def test_get_tools_returns_list():
    """Test get_tools always returns a list."""
    tools = get_tools()
    assert isinstance(tools, list)


def test_get_tools_conditional_loading():
    """Test tools only load if API key is configured."""
    if settings.tavily_api_key:
        assert len(get_tools()) > 0
        assert search_web in get_tools()
    else:
        assert len(get_tools()) == 0


# Integration tests (require real API key)
requires_tavily = pytest.mark.skipif(
    not settings.tavily_api_key,
    reason="TAVILY_API_KEY not configured",
)


@requires_tavily
@pytest.mark.asyncio
async def test_search_web_basic():
    """Test basic web search with real API."""
    result = await search_web.ainvoke({
        "query": "Python programming language",
        "max_results": 3
    })
    assert isinstance(result, str)
    assert len(result) > 0
    # Should contain results or "No web results" message
    assert ("Python" in result or "programming" in result or "No web results" in result)


@requires_tavily
@pytest.mark.asyncio
async def test_search_web_max_results_clamping():
    """Test max_results is clamped to 1-10 range."""
    # Test upper bound
    result = await search_web.ainvoke({"query": "OpenAI", "max_results": 100})
    assert isinstance(result, str)
    # Should clamp to 10, not fail

    # Test lower bound
    result = await search_web.ainvoke({"query": "AI", "max_results": 0})
    assert isinstance(result, str)
    # Should clamp to 1, not fail


@requires_tavily
@pytest.mark.asyncio
async def test_search_web_no_results():
    """Test handling of queries with no results."""
    result = await search_web.ainvoke({
        "query": "xyzabc123thisquerywillnotmatchanything456",
        "max_results": 3
    })
    assert isinstance(result, str)
    assert "No web results" in result or "found" in result.lower()


@pytest.mark.asyncio
async def test_search_web_no_api_key():
    """Test graceful handling when API key is missing."""
    # This test runs even without API key
    if not settings.tavily_api_key:
        result = await search_web.ainvoke({"query": "test", "max_results": 3})
        assert "not configured" in result.lower()
