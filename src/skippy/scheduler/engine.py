"""Scheduler engine — APScheduler setup, startup, and shutdown."""

import asyncio
import importlib
import json
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

from skippy.config import settings
from skippy.scheduler.executor import run_scheduled_task
from skippy.scheduler.routines import DIRECT_ROUTINES, PREDEFINED_ROUTINES

logger = logging.getLogger("skippy")


def _build_trigger(schedule_type: str, schedule_config: dict):
    """Build an APScheduler trigger from schedule type and config."""
    if schedule_type == "cron":
        return CronTrigger(timezone=settings.timezone, **schedule_config)
    elif schedule_type == "interval":
        return IntervalTrigger(**schedule_config)
    elif schedule_type == "date":
        return DateTrigger(**schedule_config)
    else:
        raise ValueError(f"Unknown schedule type: {schedule_type}")


async def _restore_chat_tasks(scheduler: AsyncIOScheduler, pool) -> int:
    """Load chat-created tasks from the database and add them to the scheduler."""
    count = 0
    async with pool.connection() as conn:
        rows = await conn.execute(
            "SELECT task_id, name, description, schedule_type, schedule_config "
            "FROM scheduled_tasks WHERE enabled = TRUE AND source = 'chat'"
        )
        for row in await rows.fetchall():
            task_id, name, description, schedule_type, schedule_config = row
            try:
                trigger = _build_trigger(schedule_type, schedule_config)
                scheduler.add_job(
                    run_scheduled_task,
                    trigger=trigger,
                    id=task_id,
                    name=name,
                    kwargs={"task_id": task_id, "prompt": description},
                    replace_existing=True,
                )
                count += 1
                logger.info("Restored scheduled task: %s (%s)", name, task_id)
            except Exception:
                logger.exception("Failed to restore task '%s'", task_id)
    return count


def _resolve_func(func_path: str):
    """Resolve a 'module.path:function_name' string to a callable."""
    module_path, func_name = func_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, func_name)


def _run_async_func(func_path: str):
    """Wrapper that resolves and runs an async function from APScheduler."""
    func = _resolve_func(func_path)
    loop = asyncio.get_event_loop()
    return loop.create_task(func())


def _register_predefined_routines(scheduler: AsyncIOScheduler) -> int:
    """Register predefined routines with the scheduler."""
    count = 0
    for routine in PREDEFINED_ROUTINES:
        try:
            scheduler.add_job(
                run_scheduled_task,
                trigger=routine["trigger"],
                id=routine["task_id"],
                name=routine["name"],
                kwargs={"task_id": routine["task_id"], "prompt": routine["prompt"]},
                replace_existing=True,
            )
            count += 1
            logger.info("Registered predefined routine: %s", routine["name"])
        except Exception:
            logger.exception("Failed to register routine '%s'", routine["name"])

    # Register direct-function routines (no agent graph, just call the function)
    for routine in DIRECT_ROUTINES:
        try:
            scheduler.add_job(
                _run_async_func,
                trigger=routine["trigger"],
                id=routine["task_id"],
                name=routine["name"],
                args=[routine["func"]],
                replace_existing=True,
            )
            count += 1
            logger.info("Registered direct routine: %s", routine["name"])
        except Exception:
            logger.exception("Failed to register direct routine '%s'", routine["name"])

    return count


async def start_scheduler(app) -> None:
    """Create, configure, and start the scheduler."""
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled via config")
        return

    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    predefined = _register_predefined_routines(scheduler)
    logger.info("Registered %d predefined routines", predefined)

    restored = await _restore_chat_tasks(scheduler, app.state.pool)
    logger.info("Restored %d chat-created tasks", restored)

    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Scheduler started with %d total jobs", len(scheduler.get_jobs()))


async def stop_scheduler(app) -> None:
    """Shut down the scheduler gracefully."""
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
