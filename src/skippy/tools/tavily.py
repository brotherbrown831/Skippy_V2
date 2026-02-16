"""Tavily web search tools for Skippy."""

import logging
import httpx
from langchain_core.tools import tool
from skippy.config import settings

logger = logging.getLogger("skippy")


def _get_tavily_headers() -> dict:
    """Build Tavily API request headers with authentication."""
    return {
        "Authorization": f"Bearer {settings.tavily_api_key}",
        "Content-Type": "application/json",
    }


@tool
async def search_web(query: str, max_results: int = 5) -> str:
    """Search the web for current information using Tavily API.

    Use this when the user asks about:
    - Current events or recent news
    - Real-time information (weather, stock prices, sports scores)
    - Facts that may have changed since knowledge cutoff
    - Anything requiring up-to-date web information

    Args:
        query: The search query string
        max_results: Maximum number of results to return (default 5, max 10)

    Returns:
        Formatted search results with titles, snippets, and URLs
    """
    if not settings.tavily_api_key:
        return "Web search is not configured. Please set TAVILY_API_KEY in .env file."

    # Clamp max_results to valid range (1-10)
    max_results = min(max(1, max_results), 10)

    try:
        url = f"{settings.tavily_api_base.rstrip('/')}/search"
        headers = _get_tavily_headers()
        payload = {
            "query": query,
            "max_results": max_results,
            "include_answer": False,  # Get raw results, not AI-generated summary
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

        data = response.json()
        results = data.get("results", [])

        if not results:
            return f"No web results found for '{query}'."

        # Format results as numbered list
        lines = [f"Web search results for '{query}' ({len(results)} found):\n"]
        for i, result in enumerate(results, 1):
            title = result.get("title", "No title")
            content = result.get("content", "")
            url_link = result.get("url", "")

            # Limit snippet to 200 chars
            snippet = content[:200] + "..." if len(content) > 200 else content

            lines.append(f"{i}. **{title}**")
            if snippet:
                lines.append(f"   {snippet}")
            if url_link:
                lines.append(f"   URL: {url_link}")
            lines.append("")  # Blank line between results

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        logger.error("Tavily search failed (HTTP %s): %s", e.response.status_code, e)
        if e.response.status_code == 401:
            return "Web search failed: Invalid API key. Please check TAVILY_API_KEY."
        elif e.response.status_code == 429:
            return "Web search failed: Rate limit exceeded. Please try again later."
        return f"Web search failed (HTTP {e.response.status_code}). Please try again."

    except httpx.TimeoutException:
        logger.error("Tavily search timed out for query: %s", query)
        return f"Web search timed out after 15 seconds. Please try a simpler query."

    except Exception as e:
        logger.exception("Tavily search failed unexpectedly")
        return f"Web search failed: {str(e)}"


def get_tools() -> list:
    """Return Tavily tools if API key is configured, otherwise empty list."""
    if settings.tavily_api_key:
        return [search_web]
    logger.info("Tavily API key not configured, skipping web search tools")
    return []
