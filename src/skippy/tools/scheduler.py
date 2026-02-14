"""Scheduler tools for Skippy — create, list, delete, and reminder/timer tasks."""

import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from skippy.config import settings
from skippy.scheduler.engine import _build_trigger
from skippy.scheduler.executor import run_scheduled_task

logger = logging.getLogger("skippy")


@tool
async def create_scheduled_task(
    name: str,
    description: str,
    schedule_type: str,
    hour: int = -1,
    minute: int = 0,
    interval_minutes: int = 0,
    run_date: str = "",
) -> str:
    """Create a new scheduled task. Use this when the user asks you to do something
    on a recurring basis, at a specific time, or as a one-time reminder.

    Args:
        name: A short name for the task (e.g., "Daily email check").
        description: What Skippy should do when the task runs. Be specific — this
            becomes the prompt sent to the agent. Include instructions about whether
            to send a notification.
        schedule_type: 'cron' for daily at a specific time, 'interval' for every N
            minutes, or 'date' for a one-time task.
        hour: For cron tasks, the hour (0-23). Required for cron.
        minute: For cron tasks, the minute (0-59). Defaults to 0.
        interval_minutes: For interval tasks, how often in minutes. Required for interval.
        run_date: For one-shot date tasks, ISO datetime string (e.g., '2026-02-15T10:00:00').
    """
    from skippy.main import app

    task_id = f"chat-{uuid.uuid4().hex[:8]}"

    if schedule_type == "cron":
        if hour < 0:
            return "Error: 'hour' is required for cron tasks (0-23)."
        schedule_config = {"hour": hour, "minute": minute}
    elif schedule_type == "interval":
        if interval_minutes <= 0:
            return "Error: 'interval_minutes' must be > 0 for interval tasks."
        schedule_config = {"minutes": interval_minutes}
    elif schedule_type == "date":
        if not run_date:
            return "Error: 'run_date' is required for date tasks (ISO format)."
        schedule_config = {"run_date": run_date}
    else:
        return f"Error: Unknown schedule_type '{schedule_type}'. Use 'cron', 'interval', or 'date'."

    try:
        trigger = _build_trigger(schedule_type, schedule_config)

        scheduler = app.state.scheduler
        scheduler.add_job(
            run_scheduled_task,
            trigger=trigger,
            id=task_id,
            name=name,
            kwargs={"task_id": task_id, "prompt": description},
            replace_existing=True,
        )

        async with app.state.pool.connection() as conn:
            await conn.execute(
                "INSERT INTO scheduled_tasks (task_id, name, description, schedule_type, "
                "schedule_config, source) VALUES (%s, %s, %s, %s, %s, 'chat')",
                (task_id, name, description, schedule_type, json.dumps(schedule_config)),
            )

        logger.info("Created scheduled task: %s (%s, %s)", name, task_id, schedule_type)
        return (
            f"Scheduled task '{name}' created (id: {task_id}, type: {schedule_type}, "
            f"config: {schedule_config})."
        )
    except Exception as e:
        logger.error("Failed to create scheduled task: %s", e)
        return f"Error creating scheduled task: {e}"


@tool
async def list_scheduled_tasks() -> str:
    """List all active scheduled tasks. Use when the user asks what tasks
    are scheduled, what reminders are set, or wants to see their scheduled items."""
    from skippy.main import app

    try:
        async with app.state.pool.connection() as conn:
            rows = await conn.execute(
                "SELECT task_id, name, description, schedule_type, schedule_config, source "
                "FROM scheduled_tasks WHERE enabled = TRUE ORDER BY created_at"
            )
            results = await rows.fetchall()

        if not results:
            return "No scheduled tasks found."

        lines = []
        for task_id, name, description, stype, sconfig, source in results:
            config_str = json.dumps(sconfig) if isinstance(sconfig, dict) else str(sconfig)
            desc_preview = description[:100] + ("..." if len(description) > 100 else "")
            lines.append(
                f"- {name} (id: {task_id})\n"
                f"  Type: {stype} | Config: {config_str} | Source: {source}\n"
                f"  Action: {desc_preview}"
            )

        return f"Scheduled tasks ({len(results)}):\n\n" + "\n".join(lines)
    except Exception as e:
        logger.error("Failed to list scheduled tasks: %s", e)
        return f"Error listing tasks: {e}"


@tool
async def delete_scheduled_task(task_id: str) -> str:
    """Delete a scheduled task by its ID. Use when the user asks to remove,
    cancel, or stop a scheduled task or reminder.

    Args:
        task_id: The task ID to delete (from list_scheduled_tasks).
    """
    from skippy.main import app

    try:
        scheduler = app.state.scheduler
        try:
            scheduler.remove_job(task_id)
        except Exception:
            pass  # Job may not be in scheduler (already fired one-shot)

        async with app.state.pool.connection() as conn:
            result = await conn.execute(
                "DELETE FROM scheduled_tasks WHERE task_id = %s", (task_id,)
            )
            deleted = result.rowcount

        if deleted:
            logger.info("Deleted scheduled task: %s", task_id)
            return f"Scheduled task '{task_id}' deleted successfully."
        else:
            return f"No task found with id '{task_id}'."
    except Exception as e:
        logger.error("Failed to delete scheduled task: %s", e)
        return f"Error deleting task: {e}"


def _parse_time(time_str: str) -> datetime:
    """Parse a time string like '3pm', '15:00', '2:30pm' into today's datetime."""
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    time_clean = time_str.strip().upper().replace(" ", "")

    if re.match(r"^\d{1,2}:\d{2}[AP]M$", time_clean):
        t = datetime.strptime(time_clean, "%I:%M%p").time()
    elif re.match(r"^\d{1,2}[AP]M$", time_clean):
        t = datetime.strptime(time_clean, "%I%p").time()
    elif re.match(r"^\d{1,2}:\d{2}$", time_clean):
        t = datetime.strptime(time_clean, "%H:%M").time()
    else:
        raise ValueError(f"Could not parse time: '{time_str}'")

    return datetime.combine(now.date(), t, tzinfo=tz)


@tool
async def set_reminder(
    message: str,
    minutes_from_now: int = 0,
    time_today: str = "",
) -> str:
    """Set a timer or reminder. Use this when the user says "remind me", "set a
    timer", or wants to be notified about something after a delay or at a specific
    time today.

    Args:
        message: What to remind the user about (e.g., "leave for dock appointment").
        minutes_from_now: How many minutes from now to fire the reminder. Use this
            for timers like "in 10 minutes" or "in an hour" (60).
        time_today: A specific time today like '3pm', '15:00', '2:30pm'. Use this
            for reminders like "at 3pm" or "this afternoon at 2".
    """
    from skippy.main import app

    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)

    if minutes_from_now > 0:
        run_dt = now + timedelta(minutes=minutes_from_now)
        time_label = f"in {minutes_from_now} minutes"
    elif time_today:
        try:
            run_dt = _parse_time(time_today)
        except ValueError as e:
            return f"Error: {e}"
        if run_dt <= now:
            return f"Error: {time_today} has already passed today."
        time_label = f"at {run_dt.strftime('%I:%M %p')}"
    else:
        return "Error: Provide either minutes_from_now or time_today."

    task_id = f"reminder-{uuid.uuid4().hex[:8]}"
    run_date_iso = run_dt.isoformat()
    prompt = (
        f"Send a push notification to Nolan with this reminder: '{message}'. "
        f"Use the send_notification tool with the message. Be brief and snarky."
    )

    try:
        from apscheduler.triggers.date import DateTrigger

        trigger = DateTrigger(run_date=run_dt)
        scheduler = app.state.scheduler
        scheduler.add_job(
            run_scheduled_task,
            trigger=trigger,
            id=task_id,
            name=f"Reminder: {message[:50]}",
            kwargs={"task_id": task_id, "prompt": prompt},
            replace_existing=True,
        )

        async with app.state.pool.connection() as conn:
            await conn.execute(
                "INSERT INTO scheduled_tasks (task_id, name, description, schedule_type, "
                "schedule_config, source) VALUES (%s, %s, %s, 'date', %s, 'chat')",
                (task_id, f"Reminder: {message[:50]}", prompt,
                 json.dumps({"run_date": run_date_iso})),
            )

        logger.info("Reminder set: '%s' %s (id: %s)", message, time_label, task_id)
        return f"Reminder set {time_label}: '{message}' (id: {task_id})"
    except Exception as e:
        logger.error("Failed to set reminder: %s", e)
        return f"Error setting reminder: {e}"


def get_tools() -> list:
    """Return scheduler tools if scheduler is enabled."""
    if settings.scheduler_enabled:
        return [
            create_scheduled_task,
            list_scheduled_tasks,
            delete_scheduled_task,
            set_reminder,
        ]
    return []
