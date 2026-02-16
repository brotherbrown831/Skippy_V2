"""Task management tools for Skippy - create, manage, and track todos."""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json

import psycopg
from langchain_core.tools import tool

from skippy.config import settings
from skippy.utils.activity_logger import log_activity

logger = logging.getLogger(__name__)


def _calculate_urgency_score(
    priority: int = 0,
    status: str = "inbox",
    due_date: datetime = None,
    is_backlog: bool = False,
    defer_until: datetime = None,
) -> float:
    """Calculate dynamic urgency score for task prioritization.

    Factors:
    - Priority weight: urgent=100, high=50, medium=25, low=10, none=0
    - Status boost: in_progress=+30, next_up=+20, inbox=0
    - Due date proximity: exponential increase as deadline approaches
    - Backlog penalty: -50
    - Deferred penalty: -100
    """
    # Priority weights
    priority_weights = {0: 0, 1: 10, 2: 25, 3: 50, 4: 100}
    base_score = float(priority_weights.get(priority, 0))

    # Status boost
    status_boost = {
        "in_progress": 30,
        "next_up": 20,
        "blocked": 5,
        "waiting": 5,
        "inbox": 0,
        "done": -100,
        "archived": -100,
    }
    base_score += status_boost.get(status, 0)

    # Due date proximity
    if due_date:
        now = datetime.now(tz=ZoneInfo("UTC"))
        days_until_due = (due_date - now).days
        hours_until = (due_date - now).total_seconds() / 3600

        if hours_until < 0:  # Overdue
            due_urgency = 200 + abs(int(hours_until)) * 2
        elif hours_until <= 24:  # Due today
            due_urgency = 100
        elif days_until_due <= 3:  # Due within 3 days
            due_urgency = 80 - (days_until_due * 15)
        elif days_until_due <= 7:  # Due within a week
            due_urgency = 50 - ((days_until_due - 3) * 5)
        else:  # More than a week out
            due_urgency = max(0, 30 - days_until_due)

        base_score += due_urgency

    # Backlog penalty
    if is_backlog:
        base_score -= 50

    # Deferred penalty
    if defer_until:
        now = datetime.now(tz=ZoneInfo("UTC"))
        if defer_until > now:
            base_score -= 100

    return max(0, base_score)


def _parse_due_date(due_date_str: str) -> datetime:
    """Parse due date from various formats.

    Handles: ISO format, natural language ("tomorrow", "next Friday"), etc.
    """
    if not due_date_str:
        return None

    due_date_str = due_date_str.strip().lower()

    # Simple natural language parsing
    now = datetime.now(tz=ZoneInfo("UTC"))

    if due_date_str == "today":
        return now.replace(hour=23, minute=59, second=59)
    elif due_date_str == "tomorrow":
        return (now + timedelta(days=1)).replace(hour=23, minute=59, second=59)
    elif due_date_str == "tonight":
        return now.replace(hour=23, minute=59, second=59)

    # Try parsing as ISO format
    try:
        return datetime.fromisoformat(due_date_str.replace("z", "+00:00"))
    except (ValueError, AttributeError):
        pass

    # Try dateutil parser if available
    try:
        from dateutil import parser as dateutil_parser

        parsed = dateutil_parser.parse(due_date_str, fuzzy=False)
        # If no time was specified, set to end of day
        if ":" not in due_date_str:
            parsed = parsed.replace(hour=23, minute=59, second=59)
        return parsed
    except (ValueError, TypeError):
        pass

    logger.warning("Could not parse due_date: %s", due_date_str)
    return None


@tool
async def create_task(
    title: str,
    description: str = "",
    priority: int = 0,
    due_date: str = "",
    project: str = "",
    is_backlog: bool = False,
    energy_level: str = "",
    context: str = "",
    estimated_minutes: int = 0,
) -> str:
    """Create a new task. Use when the user asks to add, create, or remember a todo.

    Args:
        title: Task title (required) - what needs to be done
        description: Detailed description or notes
        priority: 0=none, 1=low, 2=medium, 3=high, 4=urgent
        due_date: When it's due (ISO format or natural language like "tomorrow")
        project: Project/area this belongs to (e.g., "work", "home", "skippy")
        is_backlog: True if this is a long-term backlog item (not urgent)
        energy_level: "low", "medium", "high" - energy required to do this
        context: Where/how to do it (e.g., "@computer", "@home", "@phone")
        estimated_minutes: How long you think it will take
    """
    try:
        title = title.strip()
        if not title:
            return "Error: Task title is required."

        # Parse due_date
        parsed_due_date = None
        if due_date:
            parsed_due_date = _parse_due_date(due_date)

        # Determine initial status
        status = "backlog" if is_backlog else "inbox"

        # Calculate initial urgency score
        urgency_score = _calculate_urgency_score(
            priority=priority,
            status=status,
            due_date=parsed_due_date,
            is_backlog=is_backlog,
        )

        # Insert task
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO tasks (
                        user_id, title, description, priority, due_date, project,
                        is_backlog, status, urgency_score, energy_level, context, estimated_minutes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING task_id, title
                    """,
                    (
                        "nolan",
                        title,
                        description or None,
                        priority,
                        parsed_due_date,
                        project or None,
                        is_backlog,
                        status,
                        urgency_score,
                        energy_level or None,
                        context or None,
                        estimated_minutes if estimated_minutes > 0 else None,
                    ),
                )
                row = await cur.fetchone()
                task_id = row[0]
                task_title = row[1]

        # Log activity
        await log_activity(
            activity_type="task_created",
            entity_type="task",
            entity_id=str(task_id),
            description=f"Added task: {task_title}",
            metadata={
                "priority": priority,
                "project": project,
                "is_backlog": is_backlog,
                "due_date": parsed_due_date.isoformat() if parsed_due_date else None,
            },
        )

        due_str = f" (due {due_date})" if parsed_due_date else ""
        return f"✓ Task created: {task_title}{due_str}"

    except Exception as e:
        logger.exception("Failed to create task")
        return f"Error creating task: {str(e)}"


@tool
async def list_tasks(
    status: str = "", project: str = "", include_backlog: bool = False, limit: int = 20
) -> str:
    """List tasks with optional filtering.

    Args:
        status: Filter by status (inbox, next_up, in_progress, blocked, waiting, done, archived)
        project: Filter by project name
        include_backlog: Include backlog items (default: False)
        limit: Max results to return (default: 20)
    """
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                # Build WHERE clause
                where_conditions = ["user_id = 'nolan'"]

                if status:
                    where_conditions.append(f"status = '{status}'")
                if project:
                    where_conditions.append(f"project = '{project}'")
                if not include_backlog:
                    where_conditions.append("is_backlog = FALSE")

                # Only show non-archived items by default
                if status != "done" and status != "archived":
                    where_conditions.append("status NOT IN ('done', 'archived')")

                where_clause = " AND ".join(where_conditions)

                await cur.execute(
                    f"""
                    SELECT task_id, title, status, priority, due_date, project, urgency_score, estimated_minutes
                    FROM tasks
                    WHERE {where_clause}
                    ORDER BY urgency_score DESC, due_date ASC NULLS LAST
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = await cur.fetchall()

                if not rows:
                    return "No tasks found."

                # Format output
                result_lines = []
                for row in rows:
                    task_id, title, task_status, priority, due_date, proj, urgency, est_min = row

                    priority_str = {0: "", 1: "🔽 ", 2: "➡️ ", 3: "⬆️ ", 4: "🔴 "}[priority]
                    status_emoji = {
                        "inbox": "📥",
                        "next_up": "⚡",
                        "in_progress": "🔄",
                        "blocked": "🚫",
                        "waiting": "⏳",
                        "done": "✓",
                        "archived": "📦",
                    }.get(task_status, "•")

                    due_str = ""
                    if due_date:
                        now = datetime.now(tz=ZoneInfo("UTC"))
                        due_date_obj = due_date if hasattr(due_date, "tzinfo") else due_date
                        if due_date_obj.tzinfo is None:
                            due_date_obj = due_date_obj.replace(tzinfo=ZoneInfo("UTC"))

                        days_until = (due_date_obj.date() - now.date()).days
                        if days_until < 0:
                            due_str = " 🔴 OVERDUE"
                        elif days_until == 0:
                            due_str = " 🎯 TODAY"
                        elif days_until == 1:
                            due_str = " 📅 TOMORROW"
                        elif days_until <= 7:
                            due_str = f" 📅 in {days_until}d"

                    proj_str = f"[{proj}]" if proj else ""

                    line = f"[{task_id}] {status_emoji} {priority_str}{title} {proj_str}{due_str}"
                    result_lines.append(line)

                return "\n".join(result_lines)

    except Exception as e:
        logger.exception("Failed to list tasks")
        return f"Error listing tasks: {str(e)}"


@tool
async def get_task(task_id: int) -> str:
    """Get full details of a specific task.

    Args:
        task_id: The task ID
    """
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT task_id, title, description, status, priority, due_date,
                           project, is_backlog, blocked_reason, waiting_for,
                           energy_level, context, estimated_minutes, notes, created_at
                    FROM tasks
                    WHERE task_id = %s AND user_id = 'nolan'
                    """,
                    (task_id,),
                )
                row = await cur.fetchone()

                if not row:
                    return f"Task {task_id} not found."

                (
                    tid,
                    title,
                    description,
                    status,
                    priority,
                    due_date,
                    project,
                    is_backlog,
                    blocked_reason,
                    waiting_for,
                    energy_level,
                    context,
                    estimated_minutes,
                    notes,
                    created_at,
                ) = row

                # Format output
                result = f"**Task #{tid}: {title}**\n"
                result += f"Status: {status.upper()}\n"
                result += f"Priority: {['None', 'Low', 'Medium', 'High', 'Urgent'][priority]}\n"

                if due_date:
                    result += f"Due: {due_date.strftime('%Y-%m-%d %H:%M')}\n"

                if project:
                    result += f"Project: {project}\n"

                if description:
                    result += f"\nDescription:\n{description}\n"

                if blocked_reason:
                    result += f"\nBlocked: {blocked_reason}\n"

                if waiting_for:
                    result += f"Waiting for: {waiting_for}\n"

                if energy_level:
                    result += f"Energy: {energy_level}\n"

                if context:
                    result += f"Context: {context}\n"

                if estimated_minutes:
                    result += f"Estimate: {estimated_minutes} minutes\n"

                if notes:
                    result += f"\nNotes:\n{notes}\n"

                if is_backlog:
                    result += "📦 In backlog\n"

                return result

    except Exception as e:
        logger.exception("Failed to get task")
        return f"Error getting task: {str(e)}"


@tool
async def update_task(
    task_id: int,
    title: str = "",
    description: str = "",
    priority: int = -1,
    due_date: str = "",
    project: str = "",
    status: str = "",
    notes: str = "",
) -> str:
    """Update an existing task's fields.

    Args:
        task_id: Task ID (required)
        title: New title
        description: New description
        priority: New priority (0-4)
        due_date: New due date
        project: New project
        status: New status
        notes: New notes
    """
    try:
        # Build dynamic UPDATE query
        updates = []
        params = []

        if title:
            updates.append("title = %s")
            params.append(title)

        if description:
            updates.append("description = %s")
            params.append(description)

        if priority >= 0:
            updates.append("priority = %s")
            params.append(priority)

        if due_date:
            parsed_due = _parse_due_date(due_date)
            updates.append("due_date = %s")
            params.append(parsed_due)

        if project:
            updates.append("project = %s")
            params.append(project)

        if status:
            updates.append("status = %s")
            params.append(status)

        if notes:
            updates.append("notes = %s")
            params.append(notes)

        if not updates:
            return "No fields to update."

        # Always update urgency_score and updated_at
        updates.append("urgency_score = %s")
        updates.append("updated_at = NOW()")

        # Get current task to recalculate urgency
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                # Get current values
                await cur.execute(
                    "SELECT priority, status, due_date, is_backlog, defer_until FROM tasks WHERE task_id = %s AND user_id = 'nolan'",
                    (task_id,),
                )
                current = await cur.fetchone()
                if not current:
                    return f"Task {task_id} not found."

                current_priority, current_status, current_due, is_backlog, defer_until = current

                # Use updated values if provided, otherwise keep current
                new_priority = priority if priority >= 0 else current_priority
                new_status = status if status else current_status
                new_due = _parse_due_date(due_date) if due_date else current_due

                # Recalculate urgency score
                new_urgency = _calculate_urgency_score(
                    priority=new_priority,
                    status=new_status,
                    due_date=new_due,
                    is_backlog=is_backlog,
                    defer_until=defer_until,
                )
                params.append(new_urgency)

                # Execute update
                params.extend([task_id, "nolan"])

                await cur.execute(
                    f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = %s AND user_id = %s",
                    params,
                )

                # Log activity
                await log_activity(
                    activity_type="task_updated",
                    entity_type="task",
                    entity_id=str(task_id),
                    description=f"Updated task #{task_id}",
                    metadata={"fields_updated": list(set(u.split("=")[0].strip() for u in updates))},
                )

        return f"✓ Task {task_id} updated."

    except Exception as e:
        logger.exception("Failed to update task")
        return f"Error updating task: {str(e)}"


@tool
async def complete_task(task_id: int, notes: str = "") -> str:
    """Mark a task as completed.

    Args:
        task_id: Task ID
        notes: Optional completion notes
    """
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Get task title for logging
                await cur.execute(
                    "SELECT title FROM tasks WHERE task_id = %s AND user_id = 'nolan'",
                    (task_id,),
                )
                row = await cur.fetchone()
                if not row:
                    return f"Task {task_id} not found."

                task_title = row[0]

                # Update task
                if notes:
                    await cur.execute(
                        """
                        UPDATE tasks
                        SET status = 'done', completed_at = NOW(), notes = notes || %s, updated_at = NOW()
                        WHERE task_id = %s AND user_id = 'nolan'
                        """,
                        (f"\n✓ Completed: {notes}", task_id),
                    )
                else:
                    await cur.execute(
                        """
                        UPDATE tasks
                        SET status = 'done', completed_at = NOW(), updated_at = NOW()
                        WHERE task_id = %s AND user_id = 'nolan'
                        """,
                        (task_id,),
                    )

        # Log activity
        await log_activity(
            activity_type="task_completed",
            entity_type="task",
            entity_id=str(task_id),
            description=f"Completed task: {task_title}",
            metadata={"notes": notes} if notes else {},
        )

        return f"🎉 Task completed: {task_title}"

    except Exception as e:
        logger.exception("Failed to complete task")
        return f"Error completing task: {str(e)}"


@tool
async def defer_task(task_id: int, defer_until: str) -> str:
    """Defer a task until a specific date (hide it from active lists until then).

    Args:
        task_id: Task ID
        defer_until: When to show it again (ISO format or natural language)
    """
    try:
        # Parse defer date
        parsed_defer = _parse_due_date(defer_until)
        if not parsed_defer:
            return f"Could not parse defer date: {defer_until}"

        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Get task for logging
                await cur.execute(
                    "SELECT title FROM tasks WHERE task_id = %s AND user_id = 'nolan'",
                    (task_id,),
                )
                row = await cur.fetchone()
                if not row:
                    return f"Task {task_id} not found."

                task_title = row[0]

                # Update task
                await cur.execute(
                    """
                    UPDATE tasks
                    SET defer_until = %s, updated_at = NOW()
                    WHERE task_id = %s AND user_id = 'nolan'
                    """,
                    (parsed_defer, task_id),
                )

        # Log activity
        await log_activity(
            activity_type="task_deferred",
            entity_type="task",
            entity_id=str(task_id),
            description=f"Deferred task until {parsed_defer.strftime('%Y-%m-%d')}: {task_title}",
        )

        return f"⏰ Task deferred until {parsed_defer.strftime('%A, %B %d')}: {task_title}"

    except Exception as e:
        logger.exception("Failed to defer task")
        return f"Error deferring task: {str(e)}"


@tool
async def promote_task_from_backlog(task_id: int) -> str:
    """Move a backlog item to active inbox (promote it for action).

    Args:
        task_id: Backlog task ID
    """
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Get task for logging
                await cur.execute(
                    "SELECT title, priority, due_date FROM tasks WHERE task_id = %s AND user_id = 'nolan'",
                    (task_id,),
                )
                row = await cur.fetchone()
                if not row:
                    return f"Task {task_id} not found."

                task_title, priority, due_date = row

                # Update task
                new_urgency = _calculate_urgency_score(
                    priority=priority, status="inbox", due_date=due_date, is_backlog=False
                )

                await cur.execute(
                    """
                    UPDATE tasks
                    SET is_backlog = FALSE, status = 'inbox', urgency_score = %s, updated_at = NOW()
                    WHERE task_id = %s AND user_id = 'nolan'
                    """,
                    (new_urgency, task_id),
                )

        # Log activity
        await log_activity(
            activity_type="task_promoted",
            entity_type="task",
            entity_id=str(task_id),
            description=f"Promoted task from backlog: {task_title}",
        )

        return f"⬆️ Task promoted to active: {task_title}"

    except Exception as e:
        logger.exception("Failed to promote task")
        return f"Error promoting task: {str(e)}"


@tool
async def archive_task(task_id: int) -> str:
    """Archive a task (remove from active lists but don't delete).

    Args:
        task_id: Task ID
    """
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Get task for logging
                await cur.execute(
                    "SELECT title FROM tasks WHERE task_id = %s AND user_id = 'nolan'",
                    (task_id,),
                )
                row = await cur.fetchone()
                if not row:
                    return f"Task {task_id} not found."

                task_title = row[0]

                # Update task
                await cur.execute(
                    """
                    UPDATE tasks
                    SET status = 'archived', updated_at = NOW()
                    WHERE task_id = %s AND user_id = 'nolan'
                    """,
                    (task_id,),
                )

        # Log activity
        await log_activity(
            activity_type="task_archived",
            entity_type="task",
            entity_id=str(task_id),
            description=f"Archived task: {task_title}",
        )

        return f"📦 Task archived: {task_title}"

    except Exception as e:
        logger.exception("Failed to archive task")
        return f"Error archiving task: {str(e)}"


@tool
async def what_should_i_do_now(
    energy_level: str = "medium", available_minutes: int = 60, context: str = ""
) -> str:
    """Get smart task recommendations based on current context.

    This calculates urgency scores and suggests the top 3-5 tasks to work on.

    Args:
        energy_level: Your current energy ("low", "medium", "high")
        available_minutes: How much time you have
        context: Where you are (e.g., "@computer", "@home")
    """
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                # Fetch active tasks (not deferred, not backlog, not done/archived)
                where_clause = """
                    WHERE user_id = 'nolan'
                      AND status IN ('inbox', 'next_up', 'in_progress')
                      AND (defer_until IS NULL OR defer_until <= NOW())
                      AND is_backlog = FALSE
                """

                await cur.execute(
                    f"""
                    SELECT task_id, title, status, priority, due_date, estimated_minutes,
                           energy_level, context, urgency_score
                    FROM tasks
                    {where_clause}
                    ORDER BY urgency_score DESC, due_date ASC NULLS LAST
                    LIMIT 10
                    """,
                )
                rows = await cur.fetchall()

                if not rows:
                    return "No active tasks. You're all caught up! 🎉"

                # Filter by constraints
                recommendations = []
                for row in rows:
                    (
                        task_id,
                        title,
                        status,
                        priority,
                        due_date,
                        estimated,
                        task_energy,
                        task_context,
                        urgency,
                    ) = row

                    # Check energy match
                    if energy_level and task_energy:
                        energy_levels = {"low": 1, "medium": 2, "high": 3}
                        if energy_levels.get(energy_level, 2) < energy_levels.get(
                            task_energy, 2
                        ):
                            continue  # Skip if energy too low

                    # Check context match
                    if context and task_context and context.lower() != task_context.lower():
                        continue  # Skip if context doesn't match

                    # Check time estimate
                    if estimated and estimated > available_minutes:
                        continue  # Skip if too time-consuming

                    recommendations.append(row)

                # Format recommendations
                if not recommendations:
                    return "No tasks match your current context and energy level. Consider taking a break!"

                result = "**Top tasks for right now:**\n"
                for i, row in enumerate(recommendations[:5], 1):
                    (
                        task_id,
                        title,
                        status,
                        priority,
                        due_date,
                        estimated,
                        task_energy,
                        task_context,
                        urgency,
                    ) = row

                    priority_str = {0: "", 1: "low", 2: "medium", 3: "high", 4: "urgent"}[
                        priority
                    ]
                    status_emoji = {
                        "inbox": "📥",
                        "next_up": "⚡",
                        "in_progress": "🔄",
                    }.get(status, "•")

                    due_str = ""
                    if due_date:
                        now = datetime.now(tz=ZoneInfo("UTC"))
                        if due_date.tzinfo is None:
                            due_date_obj = due_date.replace(tzinfo=ZoneInfo("UTC"))
                        else:
                            due_date_obj = due_date

                        days_until = (due_date_obj.date() - now.date()).days
                        if days_until < 0:
                            due_str = " 🔴 OVERDUE"
                        elif days_until == 0:
                            due_str = " 🎯 DUE TODAY"

                    time_str = f" ({estimated}min)" if estimated else ""

                    result += f"{i}. {status_emoji} **{title}** {due_str}{time_str}\n"
                    if priority_str:
                        result += f"   Priority: {priority_str}\n"

                return result

    except Exception as e:
        logger.exception("Failed to get recommendations")
        return f"Error getting recommendations: {str(e)}"


@tool
async def move_task_to_next_up(task_id: int) -> str:
    """Move a task to 'next_up' status (prioritize it for immediate action).

    Args:
        task_id: Task ID
    """
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Get task for logging
                await cur.execute(
                    "SELECT title FROM tasks WHERE task_id = %s AND user_id = 'nolan'",
                    (task_id,),
                )
                row = await cur.fetchone()
                if not row:
                    return f"Task {task_id} not found."

                task_title = row[0]

                # Update task - set status and boost urgency
                await cur.execute(
                    """
                    UPDATE tasks
                    SET status = 'next_up', urgency_score = urgency_score + 20, updated_at = NOW()
                    WHERE task_id = %s AND user_id = 'nolan'
                    """,
                    (task_id,),
                )

        # Log activity
        await log_activity(
            activity_type="task_prioritized",
            entity_type="task",
            entity_id=str(task_id),
            description=f"Prioritized task (moved to next_up): {task_title}",
        )

        return f"⚡ Task prioritized (next up): {task_title}"

    except Exception as e:
        logger.exception("Failed to move task to next_up")
        return f"Error prioritizing task: {str(e)}"


@tool
async def search_tasks(query: str, limit: int = 10) -> str:
    """Search tasks by keyword across title, description, notes, and project.

    Args:
        query: Search keyword
        limit: Max results (default: 10)
    """
    try:
        search_term = f"%{query}%"

        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT task_id, title, status, project, priority, due_date
                    FROM tasks
                    WHERE user_id = 'nolan'
                      AND (title ILIKE %s OR description ILIKE %s OR notes ILIKE %s OR project ILIKE %s)
                      AND status NOT IN ('archived')
                    ORDER BY
                        CASE WHEN title ILIKE %s THEN 0 ELSE 1 END,
                        urgency_score DESC,
                        due_date ASC NULLS LAST
                    LIMIT %s
                    """,
                    (search_term, search_term, search_term, search_term, search_term, limit),
                )
                rows = await cur.fetchall()

                if not rows:
                    return f"No tasks found matching '{query}'."

                # Format output
                result_lines = [f"**Search results for '{query}':**"]
                for row in rows:
                    task_id, title, status, project, priority, due_date = row

                    status_emoji = {
                        "inbox": "📥",
                        "next_up": "⚡",
                        "in_progress": "🔄",
                        "blocked": "🚫",
                        "waiting": "⏳",
                        "done": "✓",
                    }.get(status, "•")

                    proj_str = f"[{project}]" if project else ""
                    line = f"[{task_id}] {status_emoji} {title} {proj_str}"
                    result_lines.append(line)

                return "\n".join(result_lines)

    except Exception as e:
        logger.exception("Failed to search tasks")
        return f"Error searching tasks: {str(e)}"


def get_tools() -> list:
    """Return task management tools - always available."""
    return [
        create_task,
        list_tasks,
        get_task,
        update_task,
        complete_task,
        defer_task,
        promote_task_from_backlog,
        archive_task,
        what_should_i_do_now,
        move_task_to_next_up,
        search_tasks,
    ]
