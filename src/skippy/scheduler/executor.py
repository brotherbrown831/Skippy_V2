"""Scheduled task executor — invokes the Skippy agent graph."""

import asyncio
import logging
import time

from langchain_core.messages import HumanMessage

logger = logging.getLogger("skippy")


async def execute_scheduled_task(task_id: str, prompt: str) -> str:
    """Execute a scheduled task by invoking the Skippy agent graph.

    The prompt becomes a HumanMessage sent through the full agent pipeline,
    so Skippy can use tools, access memories, and respond in character.
    """
    from skippy.main import app

    graph = app.state.graph
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


def run_scheduled_task(task_id: str, prompt: str) -> None:
    """Sync wrapper for APScheduler to call — runs the async executor."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(execute_scheduled_task(task_id, prompt))
    else:
        asyncio.run(execute_scheduled_task(task_id, prompt))
