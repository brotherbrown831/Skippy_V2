"""Scheduled task executor — invokes the Skippy agent graph."""

import logging
import time
from typing import Any

from langchain_core.messages import HumanMessage

logger = logging.getLogger("skippy")

# Cache of specialized graphs for scheduled tasks
_scheduled_graphs: dict[str, Any] = {}

# Tool module requirements for each scheduled task
SCHEDULED_TASK_TOOL_MODULES = {
    "morning-briefing": ["google_calendar", "tasks", "telegram"],
    "evening-summary": ["google_calendar", "tasks", "telegram"],
    "upcoming-event-check": ["google_calendar", "telegram"],
}


async def get_graph_for_task(task_id: str):
    """Get or create a graph with appropriate tools for the scheduled task.

    Args:
        task_id: The scheduled task identifier (e.g., "morning-briefing")

    Returns:
        Compiled graph with filtered tools for this task, or the default
        graph with all tools if task_id is not in the mapping.
    """
    from skippy.main import app
    from skippy.agent.graph import build_graph

    # For chat-created scheduled tasks, use the default graph (all tools)
    if task_id not in SCHEDULED_TASK_TOOL_MODULES:
        logger.info(f"Using default graph for custom task '{task_id}'")
        return app.state.graph

    # Check cache
    if task_id not in _scheduled_graphs:
        # Build and cache a filtered graph for this task
        modules = SCHEDULED_TASK_TOOL_MODULES[task_id]
        logger.info(f"Building specialized graph for '{task_id}' with modules: {modules}")

        _scheduled_graphs[task_id] = await build_graph(
            app.state.checkpointer,
            tool_modules=modules
        )

    return _scheduled_graphs[task_id]


async def execute_scheduled_task(task_id: str, prompt: str) -> str:
    """Execute a scheduled task by invoking the Skippy agent graph.

    The prompt becomes a HumanMessage sent through the full agent pipeline,
    so Skippy can use tools, access memories, and respond in character.
    """
    # Get appropriate graph for this task (filtered or default)
    graph = await get_graph_for_task(task_id)
    thread_id = f"scheduled-{task_id}-{int(time.time())}"

    logger.info("Executing scheduled task '%s'", task_id)

    try:
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=prompt)]},
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "source": "scheduler",
                    "user_id": "nolan",
                }
            },
        )
        response = result["messages"][-1].content
        logger.info("Scheduled task '%s' completed: %s", task_id, response[:200])
        return response
    except Exception as e:
        logger.error("Scheduled task '%s' failed: %s", task_id, e)
        return f"Error: {e}"


async def run_scheduled_task(task_id: str, prompt: str) -> None:
    """Async entry point for APScheduler — runs directly on the event loop."""
    await execute_scheduled_task(task_id, prompt)
