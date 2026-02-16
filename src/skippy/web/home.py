"""Dashboard homepage with Phase 1 and Phase 2 features."""
import json
import logging
from datetime import datetime, timezone

import psycopg
from fastapi import APIRouter, Body
from fastapi.responses import HTMLResponse

from skippy.config import settings

logger = logging.getLogger("skippy")

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def homepage():
    """Serve the Skippy dashboard homepage."""
    return HOMEPAGE_HTML


@router.get("/api/dashboard/stats")
async def get_dashboard_stats():
    """Return quick stats for dashboard cards."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Get memory stats
                await cur.execute(
                    "SELECT COUNT(*) FROM semantic_memories WHERE user_id = 'nolan'"
                )
                total_memories = (await cur.fetchone())[0]

                await cur.execute(
                    "SELECT COUNT(*) FROM semantic_memories WHERE user_id = 'nolan' AND created_at >= NOW() - INTERVAL '7 days'"
                )
                recent_memories = (await cur.fetchone())[0]

                # Get people stats
                await cur.execute("SELECT COUNT(*) FROM people WHERE user_id = 'nolan'")
                total_people = (await cur.fetchone())[0]

                await cur.execute(
                    "SELECT COUNT(*) FROM people WHERE user_id = 'nolan' AND importance_score >= 50"
                )
                important_people = (await cur.fetchone())[0]

                # Get task stats
                await cur.execute(
                    "SELECT COUNT(*) FROM tasks WHERE user_id = 'nolan' AND status NOT IN ('done', 'archived')"
                )
                total_tasks = (await cur.fetchone())[0]

                await cur.execute(
                    "SELECT COUNT(*) FROM tasks WHERE user_id = 'nolan' AND due_date::date = CURRENT_DATE AND status NOT IN ('done', 'archived')"
                )
                due_today_tasks = (await cur.fetchone())[0]

                return {
                    "memories": {"total": total_memories, "recent": recent_memories},
                    "people": {"total": total_people, "important": important_people},
                    "tasks": {"total": total_tasks, "due_today": due_today_tasks},
                }
    except Exception:
        logger.exception("Failed to fetch dashboard stats")
        return {
            "memories": {"total": 0, "recent": 0},
            "people": {"total": 0, "important": 0},
        }


@router.get("/api/dashboard/recent_activity")
async def get_recent_activity():
    """Return the last 10 activities across all subsystems."""
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT activity_id, activity_type, entity_type, entity_id,
                           description, metadata, created_at
                    FROM activity_log
                    WHERE user_id = 'nolan'
                    ORDER BY created_at DESC
                    LIMIT 10
                    """
                )
                rows = await cur.fetchall()
                columns = [desc.name for desc in cur.description]

                results = []
                for row in rows:
                    activity = dict(zip(columns, row))
                    if activity.get("created_at"):
                        activity["created_at"] = activity["created_at"].isoformat()
                    results.append(activity)

                return results
    except Exception:
        logger.exception("Failed to fetch recent activity")
        return []


@router.post("/api/memories")
async def create_memory_api(data: dict = Body(...)):
    """Create a new memory directly via API."""
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)

        content = data.get("content", "").strip()
        category = data.get("category", "fact")

        if not content:
            return {"ok": False, "error": "Content is required"}

        # Generate embedding
        embedding_response = await client.embeddings.create(
            model=settings.embedding_model,
            input=content,
        )
        embedding = embedding_response.data[0].embedding
        embedding_str = json.dumps(embedding)

        # Store memory
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO semantic_memories
                        (user_id, content, embedding, confidence_score, status, category)
                    VALUES (%s, %s, (%s)::vector, %s, 'active', %s)
                    RETURNING memory_id, content;
                    """,
                    ("nolan", content, embedding_str, 0.8, category),
                )
                result = await cur.fetchone()
                memory_id = result[0]

        # Log activity
        from skippy.utils.activity_logger import log_activity
        await log_activity(
            activity_type="memory_created",
            entity_type="memory",
            entity_id=str(memory_id),
            description=f"Added memory: {content[:50]}..." if len(content) > 50 else f"Added memory: {content}",
            metadata={"category": category}
        )

        return {"ok": True, "memory_id": memory_id}

    except Exception as e:
        logger.exception("Failed to create memory")
        return {"ok": False, "error": str(e)}


@router.post("/api/people")
async def create_person_api(data: dict = Body(...)):
    """Create a new person directly via API."""
    try:
        name = data.get("name", "").strip()
        relationship = data.get("relationship", "").strip()
        phone = data.get("phone", "").strip()
        email = data.get("email", "").strip()
        notes = data.get("notes", "").strip()

        if not name:
            return {"ok": False, "error": "Name is required"}

        # Create person
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO people (
                        user_id, name, canonical_name, relationship, phone, email, notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING person_id, canonical_name;
                    """,
                    ("nolan", name, name, relationship or None, phone or None, email or None, notes or None),
                )
                result = await cur.fetchone()
                person_id = result[0]
                canonical_name = result[1]

        # Log activity
        from skippy.utils.activity_logger import log_activity
        await log_activity(
            activity_type="person_created",
            entity_type="person",
            entity_id=str(person_id),
            description=f"Added person: {canonical_name}",
            metadata={"relationship": relationship}
        )

        return {"ok": True, "person_id": person_id}

    except Exception as e:
        logger.exception("Failed to create person")
        return {"ok": False, "error": str(e)}


@router.get("/api/dashboard/health")
async def get_system_health():
    """Return system health metrics."""
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                # Database size
                await cur.execute("SELECT pg_database_size(current_database())")
                db_size_bytes = (await cur.fetchone())[0]
                db_size_mb = round(db_size_bytes / (1024 * 1024), 2)

                # Memory stats
                await cur.execute(
                    "SELECT COUNT(*), AVG(confidence_score) FROM semantic_memories WHERE user_id = 'nolan' AND status = 'active'"
                )
                memory_row = await cur.fetchone()
                memory_count = memory_row[0]
                avg_confidence = round(memory_row[1] or 0, 2)

                # People stats
                await cur.execute(
                    "SELECT COUNT(*), AVG(importance_score) FROM people WHERE user_id = 'nolan'"
                )
                people_row = await cur.fetchone()
                people_count = people_row[0]
                avg_importance = round(people_row[1] or 0, 1)

                # Determine overall status
                status = "healthy"
                if db_size_mb > 1000:
                    status = "warning"

                return {
                    "status": status,
                    "database_size_mb": db_size_mb,
                    "memory_count": memory_count,
                    "avg_confidence": avg_confidence,
                    "people_count": people_count,
                    "avg_importance": avg_importance,
                }
    except Exception:
        logger.exception("Failed to fetch system health")
        return {
            "status": "error",
            "database_size_mb": 0,
            "memory_count": 0,
            "avg_confidence": 0,
            "people_count": 0,
            "avg_importance": 0,
        }


@router.post("/api/dashboard/search")
async def global_search(data: dict = Body(...)):
    """Search across memories, people, and entities."""
    query = data.get("query", "").strip()
    if not query:
        return []

    results = []
    pattern = f"%{query}%"

    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                # Search memories
                await cur.execute(
                    """
                    SELECT memory_id, content, category, confidence_score
                    FROM semantic_memories
                    WHERE user_id = 'nolan' AND status = 'active'
                      AND content ILIKE %s
                    ORDER BY confidence_score DESC
                    LIMIT 5
                    """,
                    (pattern,),
                )
                for row in await cur.fetchall():
                    results.append({
                        "type": "memory",
                        "id": row[0],
                        "title": row[1][:60] + ("..." if len(row[1]) > 60 else ""),
                        "subtitle": f"Category: {row[2]}",
                        "relevance": row[3],
                        "link": "/memories"
                    })

                # Search people
                await cur.execute(
                    """
                    SELECT person_id, canonical_name, relationship, importance_score
                    FROM people
                    WHERE user_id = 'nolan'
                      AND (canonical_name ILIKE %s OR relationship ILIKE %s OR notes ILIKE %s)
                    ORDER BY importance_score DESC
                    LIMIT 5
                    """,
                    (pattern, pattern, pattern),
                )
                for row in await cur.fetchall():
                    results.append({
                        "type": "person",
                        "id": row[0],
                        "title": row[1],
                        "subtitle": row[2] or "No relationship",
                        "relevance": (row[3] or 0) / 100,
                        "link": "/people"
                    })

        # Sort by relevance
        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:10]

    except Exception:
        logger.exception("Failed to perform global search")
        return []


@router.get("/api/user/preferences")
async def get_user_preferences():
    """Get user preferences."""
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT theme, default_page, auto_refresh_interval, preferences
                    FROM user_preferences
                    WHERE user_id = 'nolan'
                    """
                )
                row = await cur.fetchone()

                if row:
                    return {
                        "theme": row[0],
                        "default_page": row[1],
                        "auto_refresh_interval": row[2],
                        "preferences": row[3],
                    }
                else:
                    return {
                        "theme": "dark",
                        "default_page": "/",
                        "auto_refresh_interval": 30,
                        "preferences": {},
                    }
    except Exception:
        logger.exception("Failed to fetch user preferences")
        return {
            "theme": "dark",
            "default_page": "/",
            "auto_refresh_interval": 30,
            "preferences": {},
        }


@router.put("/api/user/preferences")
async def update_user_preferences(data: dict = Body(...)):
    """Update user preferences."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                updates = []
                params = []

                if "theme" in data:
                    updates.append("theme = %s")
                    params.append(data["theme"])

                if "default_page" in data:
                    updates.append("default_page = %s")
                    params.append(data["default_page"])

                if "auto_refresh_interval" in data:
                    updates.append("auto_refresh_interval = %s")
                    params.append(data["auto_refresh_interval"])

                if "preferences" in data:
                    updates.append("preferences = %s::jsonb")
                    params.append(json.dumps(data["preferences"]))

                if updates:
                    updates.append("updated_at = NOW()")
                    params.append("nolan")

                    await cur.execute(
                        f"""
                        UPDATE user_preferences
                        SET {", ".join(updates)}
                        WHERE user_id = %s
                        """,
                        params,
                    )

                return {"ok": True}

    except Exception:
        logger.exception("Failed to update user preferences")
        return {"ok": False, "error": "Failed to update preferences"}


@router.get("/api/dashboard/charts")
async def get_chart_data():
    """Return data for dashboard charts."""
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                # Chart 1: Memory growth over last 30 days
                await cur.execute(
                    """
                    SELECT DATE(created_at) as day, COUNT(*) as count
                    FROM semantic_memories
                    WHERE user_id = 'nolan'
                      AND created_at >= NOW() - INTERVAL '30 days'
                    GROUP BY DATE(created_at)
                    ORDER BY day
                    """
                )
                memory_growth_rows = await cur.fetchall()
                memory_growth = {
                    "labels": [row[0].strftime("%Y-%m-%d") for row in memory_growth_rows],
                    "data": [row[1] for row in memory_growth_rows],
                }

                # Chart 2: People importance distribution
                await cur.execute(
                    """
                    SELECT
                        CASE
                            WHEN importance_score < 20 THEN '0-20'
                            WHEN importance_score < 40 THEN '20-40'
                            WHEN importance_score < 60 THEN '40-60'
                            WHEN importance_score < 80 THEN '60-80'
                            ELSE '80-100'
                        END as range,
                        COUNT(*) as count
                    FROM people
                    WHERE user_id = 'nolan'
                    GROUP BY range
                    ORDER BY range
                    """
                )
                importance_rows = await cur.fetchall()
                importance_dist = {
                    "labels": [row[0] for row in importance_rows],
                    "data": [row[1] for row in importance_rows],
                }

                # Chart 3: Entity status breakdown
                await cur.execute(
                    """
                    SELECT
                        CASE WHEN enabled THEN 'Enabled' ELSE 'Disabled' END as status,
                        COUNT(*) as count
                    FROM ha_entities
                    WHERE user_id = 'nolan'
                    GROUP BY status
                    """
                )
                entity_rows = await cur.fetchall()
                entity_status = {
                    "labels": [row[0] for row in entity_rows],
                    "data": [row[1] for row in entity_rows],
                }

                return {
                    "memory_growth": memory_growth,
                    "importance_distribution": importance_dist,
                    "entity_status": entity_status,
                }

    except Exception:
        logger.exception("Failed to fetch chart data")
        return {
            "memory_growth": {"labels": [], "data": []},
            "importance_distribution": {"labels": [], "data": []},
            "entity_status": {"labels": [], "data": []},
        }


# ============================================================================
# TASK MANAGEMENT ENDPOINTS (Phase 2)
# ============================================================================


@router.get("/api/tasks/today")
async def get_tasks_today():
    """Return tasks for Today panel: active tasks not deferred."""
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT task_id, title, project, priority, due_date, status,
                           urgency_score, estimated_minutes
                    FROM tasks
                    WHERE user_id = 'nolan'
                      AND status NOT IN ('done', 'archived')
                      AND is_backlog = FALSE
                      AND (defer_until IS NULL OR defer_until <= NOW())
                    ORDER BY urgency_score DESC, due_date ASC NULLS LAST
                    LIMIT 20
                    """
                )
                rows = await cur.fetchall()
                columns = [desc.name for desc in cur.description]

                tasks = []
                for row in rows:
                    task = dict(zip(columns, row))
                    if task.get("due_date"):
                        task["due_date"] = task["due_date"].isoformat()
                    tasks.append(task)

                return {"tasks": tasks}
    except Exception:
        logger.exception("Failed to fetch today's tasks")
        return {"tasks": []}


@router.get("/api/tasks/backlog")
async def get_tasks_backlog():
    """Return backlog tasks sorted by backlog_rank."""
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT task_id, title, project, priority, tags, backlog_rank,
                           created_at, estimated_minutes
                    FROM tasks
                    WHERE user_id = 'nolan'
                      AND is_backlog = TRUE
                      AND status NOT IN ('done', 'archived')
                    ORDER BY backlog_rank ASC NULLS LAST, created_at DESC
                    LIMIT 50
                    """
                )
                rows = await cur.fetchall()
                columns = [desc.name for desc in cur.description]

                tasks = []
                for row in rows:
                    task = dict(zip(columns, row))
                    if task.get("created_at"):
                        task["created_at"] = task["created_at"].isoformat()
                    tasks.append(task)

                return {"tasks": tasks}
    except Exception:
        logger.exception("Failed to fetch backlog tasks")
        return {"tasks": []}


@router.post("/api/tasks")
async def create_task_api(data: dict = Body(...)):
    """Create a new task via API (for Quick Actions modal)."""
    try:
        from skippy.utils.activity_logger import log_activity

        title = data.get("title", "").strip()
        description = data.get("description", "").strip()
        priority = int(data.get("priority", 0))
        due_date_str = data.get("due_date", "").strip()
        project = data.get("project", "").strip()
        is_backlog = data.get("is_backlog", False)

        if not title:
            return {"ok": False, "error": "Title is required"}

        # Parse due_date using dateutil if available
        due_date = None
        if due_date_str:
            try:
                from dateutil import parser as dateutil_parser
                due_date = dateutil_parser.parse(due_date_str)
            except (ImportError, ValueError, TypeError):
                pass

        # Determine initial status
        status = "backlog" if is_backlog else "inbox"

        # Calculate urgency score
        priority_weights = {0: 0, 1: 10, 2: 25, 3: 50, 4: 100}
        urgency_score = float(priority_weights.get(priority, 0))

        # Insert task
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO tasks (
                        user_id, title, description, priority, due_date, project,
                        is_backlog, status, urgency_score
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING task_id
                    """,
                    (
                        "nolan",
                        title,
                        description or None,
                        priority,
                        due_date,
                        project or None,
                        is_backlog,
                        status,
                        urgency_score,
                    ),
                )
                task_id = (await cur.fetchone())[0]

        # Log activity
        await log_activity(
            activity_type="task_created",
            entity_type="task",
            entity_id=str(task_id),
            description=f"Added task: {title}",
            metadata={"project": project, "priority": priority},
        )

        return {"ok": True, "task_id": task_id}

    except Exception as e:
        logger.exception("Failed to create task")
        return {"ok": False, "error": str(e)}


@router.put("/api/tasks/{task_id}/complete")
async def complete_task_api(task_id: int):
    """Mark a task as completed."""
    try:
        from skippy.utils.activity_logger import log_activity

        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE tasks
                    SET status = 'done', completed_at = NOW(), updated_at = NOW()
                    WHERE task_id = %s AND user_id = 'nolan'
                    RETURNING title
                    """,
                    (task_id,),
                )
                result = await cur.fetchone()

                if not result:
                    return {"ok": False, "error": "Task not found"}

                title = result[0]

        # Log activity
        await log_activity(
            activity_type="task_completed",
            entity_type="task",
            entity_id=str(task_id),
            description=f"Completed task: {title}",
        )

        return {"ok": True}

    except Exception as e:
        logger.exception("Failed to complete task")
        return {"ok": False, "error": str(e)}


@router.put("/api/tasks/{task_id}/promote")
async def promote_task_api(task_id: int):
    """Promote a backlog task to active inbox."""
    try:
        from skippy.utils.activity_logger import log_activity

        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE tasks
                    SET is_backlog = FALSE, status = 'inbox', updated_at = NOW()
                    WHERE task_id = %s AND user_id = 'nolan'
                    RETURNING title
                    """,
                    (task_id,),
                )
                result = await cur.fetchone()

                if not result:
                    return {"ok": False, "error": "Task not found"}

                title = result[0]

        # Log activity
        await log_activity(
            activity_type="task_promoted",
            entity_type="task",
            entity_id=str(task_id),
            description=f"Promoted task to active: {title}",
        )

        return {"ok": True}

    except Exception as e:
        logger.exception("Failed to promote task")
        return {"ok": False, "error": str(e)}


@router.get("/api/tasks/stats")
async def get_task_stats():
    """Return task statistics for System Health modal and cards."""
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                # Total active tasks
                await cur.execute(
                    """
                    SELECT COUNT(*) FROM tasks
                    WHERE user_id = 'nolan' AND status NOT IN ('done', 'archived')
                    """
                )
                total_active = (await cur.fetchone())[0]

                # Overdue count
                await cur.execute(
                    """
                    SELECT COUNT(*) FROM tasks
                    WHERE user_id = 'nolan'
                      AND status NOT IN ('done', 'archived')
                      AND due_date < NOW()
                    """
                )
                overdue = (await cur.fetchone())[0]

                # Due today
                await cur.execute(
                    """
                    SELECT COUNT(*) FROM tasks
                    WHERE user_id = 'nolan'
                      AND status NOT IN ('done', 'archived')
                      AND due_date::date = CURRENT_DATE
                    """
                )
                due_today = (await cur.fetchone())[0]

                # Backlog size
                await cur.execute(
                    """
                    SELECT COUNT(*) FROM tasks
                    WHERE user_id = 'nolan'
                      AND is_backlog = TRUE
                      AND status NOT IN ('done', 'archived')
                    """
                )
                backlog_size = (await cur.fetchone())[0]

                # Completed last 7 days
                await cur.execute(
                    """
                    SELECT COUNT(*) FROM tasks
                    WHERE user_id = 'nolan'
                      AND status = 'done'
                      AND completed_at >= NOW() - INTERVAL '7 days'
                    """
                )
                completed_week = (await cur.fetchone())[0]

                # Completion rate (completed / total over last 30 days)
                await cur.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE status = 'done') as completed,
                        COUNT(*) as total
                    FROM tasks
                    WHERE user_id = 'nolan'
                      AND created_at >= NOW() - INTERVAL '30 days'
                    """
                )
                row = await cur.fetchone()
                completed_month = row[0] if row else 0
                total_month = row[1] if row else 1
                completion_rate = (
                    (completed_month / total_month * 100) if total_month > 0 else 0
                )

                return {
                    "total_active": total_active,
                    "overdue": overdue,
                    "due_today": due_today,
                    "backlog_size": backlog_size,
                    "completed_week": completed_week,
                    "completion_rate": round(completion_rate, 1),
                }

    except Exception:
        logger.exception("Failed to fetch task stats")
        return {
            "total_active": 0,
            "overdue": 0,
            "due_today": 0,
            "backlog_size": 0,
            "completed_week": 0,
            "completion_rate": 0,
        }


@router.get("/api/tasks/chart_data")
async def get_task_chart_data():
    """Return data for task completion chart (last 7 days)."""
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT
                        completed_at::date as day,
                        COUNT(*) as count
                    FROM tasks
                    WHERE user_id = 'nolan'
                      AND status = 'done'
                      AND completed_at >= CURRENT_DATE - INTERVAL '6 days'
                    GROUP BY completed_at::date
                    ORDER BY day
                    """
                )
                rows = await cur.fetchall()

                # Fill in missing days with 0
                from datetime import date, timedelta

                labels = []
                data = []
                for i in range(6, -1, -1):
                    day = date.today() - timedelta(days=i)
                    labels.append(day.strftime("%a"))

                    # Find count for this day
                    count = 0
                    for row in rows:
                        if row[0] == day:
                            count = row[1]
                            break
                    data.append(count)

                return {"labels": labels, "data": data}

    except Exception:
        logger.exception("Failed to fetch task chart data")
        return {"labels": [], "data": []}


@router.put("/api/tasks/{task_id}")
async def update_task_api(task_id: int, data: dict = Body(...)):
    """Update a task's status or other fields."""
    try:
        from skippy.utils.activity_logger import log_activity

        status = data.get("status")
        if not status:
            return {"ok": False, "error": "Status is required"}

        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE tasks
                    SET status = %s, updated_at = NOW()
                    WHERE task_id = %s AND user_id = 'nolan'
                    RETURNING title
                    """,
                    (status, task_id),
                )
                result = await cur.fetchone()

                if not result:
                    return {"ok": False, "error": "Task not found"}

                title = result[0]

        # Log activity
        await log_activity(
            activity_type="task_updated",
            entity_type="task",
            entity_id=str(task_id),
            description=f"Updated task status to {status}: {title}",
        )

        return {"ok": True}

    except Exception as e:
        logger.exception("Failed to update task")
        return {"ok": False, "error": str(e)}


@router.put("/api/tasks/{task_id}/defer")
async def defer_task_api(task_id: int, data: dict = Body(...)):
    """Defer a task until a specific date."""
    try:
        from skippy.utils.activity_logger import log_activity

        defer_until_str = data.get("defer_until", "").strip()
        if not defer_until_str:
            return {"ok": False, "error": "defer_until is required"}

        # Parse defer_until
        try:
            from dateutil import parser as dateutil_parser
            defer_until = dateutil_parser.parse(defer_until_str)
        except (ImportError, ValueError, TypeError):
            return {"ok": False, "error": "Invalid date format"}

        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE tasks
                    SET defer_until = %s, updated_at = NOW()
                    WHERE task_id = %s AND user_id = 'nolan'
                    RETURNING title
                    """,
                    (defer_until, task_id),
                )
                result = await cur.fetchone()

                if not result:
                    return {"ok": False, "error": "Task not found"}

                title = result[0]

        # Log activity
        await log_activity(
            activity_type="task_deferred",
            entity_type="task",
            entity_id=str(task_id),
            description=f"Deferred task until {defer_until_str}: {title}",
        )

        return {"ok": True}

    except Exception as e:
        logger.exception("Failed to defer task")
        return {"ok": False, "error": str(e)}


@router.delete("/api/tasks/{task_id}")
async def delete_task_api(task_id: int):
    """Delete a task."""
    try:
        from skippy.utils.activity_logger import log_activity

        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    DELETE FROM tasks
                    WHERE task_id = %s AND user_id = 'nolan'
                    RETURNING title
                    """,
                    (task_id,),
                )
                result = await cur.fetchone()

                if not result:
                    return {"ok": False, "error": "Task not found"}

                title = result[0]

        # Log activity
        await log_activity(
            activity_type="task_deleted",
            entity_type="task",
            entity_id=str(task_id),
            description=f"Deleted task: {title}",
        )

        return {"ok": True}

    except Exception as e:
        logger.exception("Failed to delete task")
        return {"ok": False, "error": str(e)}


HOMEPAGE_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Skippy Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f1117;
            color: #e0e0e0;
            padding: 24px;
            min-height: 100vh;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        /* Health badge */
        .health-badge {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #1a1d27;
            border: 1px solid #2a2d37;
            border-radius: 20px;
            padding: 8px 16px;
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
            transition: all 0.2s;
            z-index: 100;
        }
        .health-badge:hover {
            background: #222530;
            border-color: #3a3d47;
        }
        .health-icon {
            font-size: 1.2rem;
        }
        .health-text {
            font-size: 0.85rem;
            font-weight: 600;
        }

        /* Search bar */
        .search-container {
            position: relative;
            margin-bottom: 24px;
        }
        #global-search {
            width: 100%;
            background: #1a1d27;
            color: #e0e0e0;
            border: 1px solid #2a2d37;
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 1rem;
        }
        #global-search:focus {
            outline: none;
            border-color: #7eb8ff;
        }
        .search-results {
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: #1a1d27;
            border: 1px solid #2a2d37;
            border-radius: 8px;
            margin-top: 8px;
            max-height: 400px;
            overflow-y: auto;
            z-index: 200;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        .search-result-item {
            padding: 12px 16px;
            border-bottom: 1px solid #2a2d37;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .search-result-item:hover {
            background: #222530;
        }
        .search-result-icon {
            font-size: 1.5rem;
        }
        .search-result-content {
            flex-grow: 1;
        }
        .search-result-title {
            color: #e0e0e0;
            font-weight: 600;
            margin-bottom: 4px;
        }
        .search-result-subtitle {
            color: #777;
            font-size: 0.85rem;
        }

        /* Header */
        .header {
            text-align: center;
            margin-bottom: 32px;
        }
        .header h1 {
            font-size: 2.5rem;
            color: #7eb8ff;
            margin-bottom: 8px;
        }
        .header p {
            color: #888;
            font-size: 1rem;
        }

        /* Quick actions */
        .quick-actions {
            display: flex;
            gap: 12px;
            margin-bottom: 32px;
            flex-wrap: wrap;
        }
        .action-btn {
            padding: 12px 20px;
            border: none;
            border-radius: 6px;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s;
        }
        .action-btn-primary {
            background: #7eb8ff;
            color: #0f1117;
        }
        .action-btn-primary:hover {
            background: #5a9ee0;
        }
        .action-btn-secondary {
            background: #c792ea;
            color: #0f1117;
        }
        .action-btn-secondary:hover {
            background: #b078d0;
        }
        .action-btn-accent {
            background: #89ddff;
            color: #0f1117;
        }
        .action-btn-accent:hover {
            background: #6bc3e5;
        }

        /* Cards Grid */
        .cards-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 24px;
            margin-bottom: 48px;
        }

        .card {
            background: #1a1d27;
            border: 1px solid #2a2d37;
            border-radius: 8px;
            padding: 24px;
            text-decoration: none;
            color: inherit;
            transition: all 0.2s;
            display: flex;
            flex-direction: column;
        }

        .card:hover {
            border-color: var(--accent);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }

        .card-icon {
            font-size: 2.5rem;
            margin-bottom: 16px;
        }

        .card h2 {
            font-size: 1.4rem;
            margin-bottom: 8px;
        }

        .card p {
            color: #888;
            font-size: 0.9rem;
            margin-bottom: 16px;
            flex-grow: 1;
        }

        .card-stats {
            margin: 16px 0;
        }

        .stat {
            display: flex;
            justify-content: space-between;
            margin: 8px 0;
            font-size: 0.85rem;
        }

        .stat-label { color: #777; }
        .stat-value {
            font-weight: 600;
            color: var(--accent);
        }

        .card-button {
            background: transparent;
            border: 1px solid var(--accent);
            color: var(--accent);
            padding: 10px 20px;
            border-radius: 4px;
            text-align: center;
            font-weight: 500;
            margin-top: 8px;
        }

        .card.memories { --accent: #7eb8ff; }
        .card.people { --accent: #c792ea; }
        .card.entities { --accent: #89ddff; }
        .card.tasks { --accent: #82aaff; }
        .card.pgadmin { --accent: #ffc857; }

        /* Modal */
        .modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }
        .modal-content {
            background: #1a1d27;
            border: 1px solid #2a2d37;
            border-radius: 8px;
            max-width: 500px;
            width: 90%;
            max-height: 90vh;
            overflow-y: auto;
        }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px;
            border-bottom: 1px solid #2a2d37;
        }
        .modal-header h3 {
            margin: 0;
            color: #7eb8ff;
        }
        .modal-close {
            background: none;
            border: none;
            color: #888;
            font-size: 2rem;
            cursor: pointer;
            padding: 0;
            line-height: 1;
        }
        .modal-close:hover {
            color: #e0e0e0;
        }
        .modal-body {
            padding: 20px;
        }
        .modal-body label {
            display: block;
            color: #aaa;
            font-size: 0.85rem;
            margin: 16px 0 6px 0;
        }
        .modal-body input,
        .modal-body textarea,
        .modal-body select {
            width: 100%;
            background: #0f1117;
            color: #e0e0e0;
            border: 1px solid #2a2d37;
            padding: 10px;
            border-radius: 4px;
            font-size: 0.9rem;
        }
        .modal-footer {
            display: flex;
            justify-content: flex-end;
            gap: 12px;
            padding: 20px;
            border-top: 1px solid #2a2d37;
        }
        .btn-cancel {
            background: transparent;
            border: 1px solid #444;
            color: #888;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
        }
        .btn-cancel:hover {
            border-color: #666;
            color: #aaa;
        }
        .btn-primary {
            background: #7eb8ff;
            color: #0f1117;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            font-weight: 600;
            cursor: pointer;
        }
        .btn-primary:hover {
            background: #5a9ee0;
        }

        /* Activity timeline */
        .section {
            margin: 48px 0;
        }
        .section-title {
            font-size: 1.4rem;
            color: #7eb8ff;
            margin-bottom: 20px;
        }
        .activity-timeline {
            background: #1a1d27;
            border: 1px solid #2a2d37;
            border-radius: 8px;
            padding: 16px;
            max-height: 400px;
            overflow-y: auto;
        }
        .activity-item {
            display: flex;
            gap: 12px;
            padding: 12px;
            border-bottom: 1px solid #2a2d37;
        }
        .activity-item:last-child {
            border-bottom: none;
        }
        .activity-icon {
            font-size: 1.5rem;
            flex-shrink: 0;
        }
        .activity-content {
            flex-grow: 1;
        }
        .activity-description {
            color: #e0e0e0;
            font-size: 0.9rem;
            margin-bottom: 4px;
        }
        .activity-time {
            color: #777;
            font-size: 0.8rem;
        }
        .activity-empty {
            text-align: center;
            color: #555;
            padding: 20px;
        }

        /* Charts */
        .charts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 24px;
        }
        .chart-container {
            background: #1a1d27;
            border: 1px solid #2a2d37;
            border-radius: 8px;
            padding: 20px;
        }
        .chart-title {
            font-size: 1rem;
            color: #aaa;
            margin-bottom: 16px;
            text-align: center;
        }

        /* Health modal */
        .health-metric {
            display: flex;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid #2a2d37;
        }
        .health-metric:last-child {
            border-bottom: none;
        }
        .metric-label {
            color: #888;
            font-size: 0.9rem;
        }
        .metric-value {
            color: #e0e0e0;
            font-weight: 600;
        }

        /* Settings button */
        .settings-btn {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #1a1d27;
            border: 1px solid #2a2d37;
            color: #7eb8ff;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            font-size: 1.5rem;
            cursor: pointer;
            z-index: 100;
            transition: all 0.2s;
        }
        .settings-btn:hover {
            background: #222530;
            border-color: #7eb8ff;
        }

        /* Responsive */
        @media (max-width: 768px) {
            .cards-grid {
                grid-template-columns: 1fr;
            }
            .header h1 {
                font-size: 1.8rem;
            }
            .quick-actions {
                flex-direction: column;
            }
            .action-btn {
                width: 100%;
                justify-content: center;
            }
        }

        /* Light theme support */
        body.light-theme {
            background: #f5f5f5;
            color: #222;
        }
        body.light-theme .card {
            background: #fff;
            border-color: #ddd;
        }
        body.light-theme .activity-timeline {
            background: #fff;
            border-color: #ddd;
        }
    </style>
</head>
<body>
    <div class="health-badge" id="health-badge" title="System Health">
        <span class="health-icon">⚪</span>
        <span class="health-text">Checking...</span>
    </div>

    <button class="settings-btn" onclick="openSettingsModal()" title="Settings">⚙️</button>

    <div id="health-modal" class="modal" style="display: none;">
        <div class="modal-content">
            <div class="modal-header">
                <h3>System Health</h3>
                <button class="modal-close" onclick="closeHealthModal()">×</button>
            </div>
            <div class="modal-body">
                <div class="health-metric">
                    <span class="metric-label">Overall Status</span>
                    <span class="metric-value" id="health-status">-</span>
                </div>
                <div class="health-metric">
                    <span class="metric-label">Database Size</span>
                    <span class="metric-value" id="health-db-size">-</span>
                </div>
                <div class="health-metric">
                    <span class="metric-label">Last HA Sync</span>
                    <span class="metric-value" id="health-last-sync">-</span>
                </div>
                <div class="health-metric">
                    <span class="metric-label">Avg Memory Confidence</span>
                    <span class="metric-value" id="health-avg-confidence">-</span>
                </div>
                <div class="health-metric">
                    <span class="metric-label">Avg People Importance</span>
                    <span class="metric-value" id="health-avg-importance">-</span>
                </div>
            </div>
        </div>
    </div>

    <div id="add-memory-modal" class="modal" style="display: none;">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Add New Memory</h3>
                <button class="modal-close" onclick="closeAddMemoryModal()">×</button>
            </div>
            <div class="modal-body">
                <label>Content</label>
                <textarea id="memory-content" rows="4" placeholder="Enter memory content..."></textarea>
                <label>Category</label>
                <select id="memory-category">
                    <option value="fact">Fact</option>
                    <option value="preference">Preference</option>
                    <option value="family">Family</option>
                    <option value="person">Person</option>
                    <option value="technical">Technical</option>
                    <option value="project">Project</option>
                </select>
            </div>
            <div class="modal-footer">
                <button class="btn-cancel" onclick="closeAddMemoryModal()">Cancel</button>
                <button class="btn-primary" onclick="submitMemory()">Add Memory</button>
            </div>
        </div>
    </div>

    <div id="add-person-modal" class="modal" style="display: none;">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Add New Person</h3>
                <button class="modal-close" onclick="closeAddPersonModal()">×</button>
            </div>
            <div class="modal-body">
                <label>Name *</label>
                <input type="text" id="person-name" placeholder="Full name" required>
                <label>Relationship</label>
                <input type="text" id="person-relationship" placeholder="e.g., friend, colleague">
                <label>Phone</label>
                <input type="tel" id="person-phone" placeholder="Phone number">
                <label>Email</label>
                <input type="email" id="person-email" placeholder="Email address">
                <label>Notes</label>
                <textarea id="person-notes" rows="3" placeholder="Additional notes..."></textarea>
            </div>
            <div class="modal-footer">
                <button class="btn-cancel" onclick="closeAddPersonModal()">Cancel</button>
                <button class="btn-primary" onclick="submitPerson()">Add Person</button>
            </div>
        </div>
    </div>

    <div id="add-task-modal" class="modal" style="display: none;">
        <div class="modal-content">
            <div class="modal-header">
                <h3>✓ Add Task</h3>
                <button class="modal-close" onclick="closeAddTaskModal()">×</button>
            </div>
            <div class="modal-body">
                <label>Title *</label>
                <input type="text" id="task-title" placeholder="What needs to be done?" required>
                <label>Description</label>
                <textarea id="task-description" rows="3" placeholder="Additional details..."></textarea>
                <label>Priority</label>
                <select id="task-priority">
                    <option value="0">None</option>
                    <option value="1">Low</option>
                    <option value="2" selected>Medium</option>
                    <option value="3">High</option>
                    <option value="4">Urgent</option>
                </select>
                <label>Due Date</label>
                <input type="datetime-local" id="task-due-date">
                <label>Project</label>
                <input type="text" id="task-project" placeholder="e.g., work, home, skippy">
                <label>
                    <input type="checkbox" id="task-is-backlog">
                    Add to backlog (long-term, not urgent)
                </label>
            </div>
            <div class="modal-footer">
                <button class="btn-cancel" onclick="closeAddTaskModal()">Cancel</button>
                <button class="btn-primary" onclick="submitAddTask()">Add Task</button>
            </div>
        </div>
    </div>

    <div id="settings-modal" class="modal" style="display: none;">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Settings</h3>
                <button class="modal-close" onclick="closeSettingsModal()">×</button>
            </div>
            <div class="modal-body">
                <label>Theme</label>
                <select id="pref-theme">
                    <option value="dark">Dark</option>
                    <option value="light">Light</option>
                </select>
                <label>Default Page</label>
                <select id="pref-default-page">
                    <option value="/">Dashboard</option>
                    <option value="/memories">Memories</option>
                    <option value="/people">People</option>
                </select>
                <label>Auto-Refresh Interval (seconds)</label>
                <input type="number" id="pref-refresh-interval" min="10" max="300" step="10">
            </div>
            <div class="modal-footer">
                <button class="btn-cancel" onclick="closeSettingsModal()">Cancel</button>
                <button class="btn-primary" onclick="savePreferences()">Save</button>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="search-container">
            <input type="text" id="global-search" placeholder="Search memories, people, entities...">
            <div id="search-results" class="search-results" style="display: none;"></div>
        </div>

        <div class="header">
            <h1>🤖 Skippy AI Assistant</h1>
            <p>Your personal AI home automation & life management system</p>
        </div>

        <div class="quick-actions">
            <button class="action-btn action-btn-primary" onclick="openAddMemoryModal()">
                <span>🧠</span> Add Memory
            </button>
            <button class="action-btn action-btn-secondary" onclick="openAddPersonModal()">
                <span>👤</span> Add Person
            </button>
            <button class="action-btn action-btn-accent" onclick="openAddTaskModal()">
                <span>✓</span> Add Task
            </button>
        </div>

        <div class="cards-grid">
            <a href="/memories" class="card memories">
                <div class="card-icon">🧠</div>
                <h2>Semantic Memories</h2>
                <p>Long-term memory storage with semantic search</p>
                <div class="card-stats">
                    <div class="stat">
                        <span class="stat-label">Total Memories</span>
                        <span class="stat-value" id="memories-total">-</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">This Week</span>
                        <span class="stat-value" id="memories-recent">-</span>
                    </div>
                </div>
                <div class="card-button">View Memories →</div>
            </a>

            <a href="/people" class="card people">
                <div class="card-icon">👥</div>
                <h2>People</h2>
                <p>Contact management & importance tracking</p>
                <div class="card-stats">
                    <div class="stat">
                        <span class="stat-label">Total People</span>
                        <span class="stat-value" id="people-total">-</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Important</span>
                        <span class="stat-value" id="people-important">-</span>
                    </div>
                </div>
                <div class="card-button">View People →</div>
            </a>

            <a href="/tasks" class="card tasks">
                <div class="card-icon">✓</div>
                <h2>Tasks</h2>
                <p>Track todos, projects, and priorities</p>
                <div class="card-stats">
                    <div class="stat">
                        <span class="stat-label">Active</span>
                        <span class="stat-value" id="tasks-total">-</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Due Today</span>
                        <span class="stat-value" id="tasks-due-today">-</span>
                    </div>
                </div>
                <div class="card-button">View Tasks →</div>
            </a>

            <a href="http://localhost:5050" target="_blank" class="card pgadmin">
                <div class="card-icon">🗄️</div>
                <h2>pgAdmin</h2>
                <p>PostgreSQL database administration & query builder</p>
                <div class="card-stats">
                    <div class="stat">
                        <span class="stat-label">Host</span>
                        <span class="stat-value">localhost:5050</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">User</span>
                        <span class="stat-value">admin@skippy.dev</span>
                    </div>
                </div>
                <div class="card-button">Open pgAdmin →</div>
            </a>
        </div>

        <div class="section">
            <h2 class="section-title">📊 Recent Activity</h2>
            <div class="activity-timeline" id="activity-timeline">
                <div class="activity-empty">Loading...</div>
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">📈 Statistics</h2>
            <div class="charts-grid">
                <div class="chart-container">
                    <h3 class="chart-title">Memory Growth (30 days)</h3>
                    <canvas id="memory-growth-chart"></canvas>
                </div>
                <div class="chart-container">
                    <h3 class="chart-title">People Importance</h3>
                    <canvas id="importance-chart"></canvas>
                </div>
                <div class="chart-container">
                    <h3 class="chart-title">Entity Status</h3>
                    <canvas id="entity-status-chart"></canvas>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script>
        // Utility functions
        function formatTimeAgo(isoString) {
            const now = new Date();
            const past = new Date(isoString);
            const diffMs = now - past;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMs / 3600000);
            const diffDays = Math.floor(diffMs / 86400000);

            if (diffMins < 1) return 'Just now';
            if (diffMins < 60) return diffMins + ' minute' + (diffMins > 1 ? 's' : '') + ' ago';
            if (diffHours < 24) return diffHours + ' hour' + (diffHours > 1 ? 's' : '') + ' ago';
            if (diffDays < 7) return diffDays + ' day' + (diffDays > 1 ? 's' : '') + ' ago';
            return past.toLocaleDateString();
        }

        function getActivityIcon(activityType) {
            const icons = {
                'memory_created': '🧠',
                'memory_reinforced': '💪',
                'person_created': '👤',
                'person_updated': '✏️',
                'person_merged': '🔗',
                'entity_synced': '🔄',
            };
            return icons[activityType] || '📌';
        }

        // Stats loading
        async function loadStats() {
            try {
                const response = await fetch('/api/dashboard/stats');
                const data = await response.json();
                document.getElementById('memories-total').textContent = data.memories.total;
                document.getElementById('memories-recent').textContent = data.memories.recent;
                document.getElementById('people-total').textContent = data.people.total;
                document.getElementById('people-important').textContent = data.people.important;
                if (data.tasks) {
                    document.getElementById('tasks-total').textContent = data.tasks.total;
                    document.getElementById('tasks-due-today').textContent = data.tasks.due_today;
                }
            } catch (error) {
                console.error('Failed to load stats:', error);
            }
        }

        // Recent activity
        async function loadRecentActivity() {
            try {
                const response = await fetch('/api/dashboard/recent_activity');
                const activities = await response.json();
                const timeline = document.getElementById('activity-timeline');

                if (activities.length === 0) {
                    timeline.innerHTML = '<div class="activity-empty">No recent activity</div>';
                    return;
                }

                timeline.innerHTML = activities.map(a => {
                    const icon = getActivityIcon(a.activity_type);
                    const timeAgo = formatTimeAgo(a.created_at);
                    return `
                        <div class="activity-item">
                            <div class="activity-icon">${icon}</div>
                            <div class="activity-content">
                                <div class="activity-description">${a.description}</div>
                                <div class="activity-time">${timeAgo}</div>
                            </div>
                        </div>
                    `;
                }).join('');
            } catch (error) {
                console.error('Failed to load recent activity:', error);
            }
        }

        // System health
        async function loadSystemHealth() {
            try {
                const response = await fetch('/api/dashboard/health');
                const health = await response.json();

                const badge = document.getElementById('health-badge');
                const icon = badge.querySelector('.health-icon');
                const text = badge.querySelector('.health-text');

                if (health.status === 'healthy') {
                    icon.textContent = '🟢';
                    text.textContent = 'Healthy';
                    badge.style.borderColor = '#48bb78';
                } else if (health.status === 'warning') {
                    icon.textContent = '🟡';
                    text.textContent = 'Warning';
                    badge.style.borderColor = '#f6ad55';
                } else {
                    icon.textContent = '🔴';
                    text.textContent = 'Error';
                    badge.style.borderColor = '#fc8181';
                }

                document.getElementById('health-status').textContent = health.status.toUpperCase();
                document.getElementById('health-db-size').textContent = health.database_size_mb + ' MB';
                document.getElementById('health-last-sync').textContent = health.last_sync ? formatTimeAgo(health.last_sync) : 'Never';
                document.getElementById('health-avg-confidence').textContent = health.avg_confidence.toFixed(2);
                document.getElementById('health-avg-importance').textContent = health.avg_importance.toFixed(1);
            } catch (error) {
                console.error('Failed to load system health:', error);
            }
        }

        document.getElementById('health-badge').addEventListener('click', () => {
            document.getElementById('health-modal').style.display = 'flex';
        });

        function closeHealthModal() {
            document.getElementById('health-modal').style.display = 'none';
        }

        // Quick actions
        function openAddMemoryModal() {
            document.getElementById('add-memory-modal').style.display = 'flex';
        }

        function closeAddMemoryModal() {
            document.getElementById('add-memory-modal').style.display = 'none';
            document.getElementById('memory-content').value = '';
            document.getElementById('memory-category').value = 'fact';
        }

        async function submitMemory() {
            const content = document.getElementById('memory-content').value.trim();
            const category = document.getElementById('memory-category').value;

            if (!content) {
                alert('Please enter memory content');
                return;
            }

            try {
                const response = await fetch('/api/memories', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content, category })
                });
                const result = await response.json();

                if (result.ok) {
                    closeAddMemoryModal();
                    loadStats();
                    loadRecentActivity();
                    alert('Memory added successfully!');
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Failed to add memory: ' + error);
            }
        }

        function openAddPersonModal() {
            document.getElementById('add-person-modal').style.display = 'flex';
        }

        function closeAddPersonModal() {
            document.getElementById('add-person-modal').style.display = 'none';
            document.getElementById('person-name').value = '';
            document.getElementById('person-relationship').value = '';
            document.getElementById('person-phone').value = '';
            document.getElementById('person-email').value = '';
            document.getElementById('person-notes').value = '';
        }

        async function submitPerson() {
            const name = document.getElementById('person-name').value.trim();
            const relationship = document.getElementById('person-relationship').value.trim();
            const phone = document.getElementById('person-phone').value.trim();
            const email = document.getElementById('person-email').value.trim();
            const notes = document.getElementById('person-notes').value.trim();

            if (!name) {
                alert('Please enter a name');
                return;
            }

            try {
                const response = await fetch('/api/people', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, relationship, phone, email, notes })
                });
                const result = await response.json();

                if (result.ok) {
                    closeAddPersonModal();
                    loadStats();
                    loadRecentActivity();
                    alert('Person added successfully!');
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Failed to add person: ' + error);
            }
        }

        // Task Management
        function openAddTaskModal() {
            document.getElementById('add-task-modal').style.display = 'flex';
        }

        function closeAddTaskModal() {
            document.getElementById('add-task-modal').style.display = 'none';
            // Clear form
            document.getElementById('task-title').value = '';
            document.getElementById('task-description').value = '';
            document.getElementById('task-priority').value = '2';
            document.getElementById('task-due-date').value = '';
            document.getElementById('task-project').value = '';
            document.getElementById('task-is-backlog').checked = false;
        }

        async function submitAddTask() {
            const title = document.getElementById('task-title').value.trim();
            const description = document.getElementById('task-description').value.trim();
            const priority = parseInt(document.getElementById('task-priority').value);
            const dueDate = document.getElementById('task-due-date').value;
            const project = document.getElementById('task-project').value.trim();
            const isBacklog = document.getElementById('task-is-backlog').checked;

            if (!title) {
                alert('Title is required');
                return;
            }

            try {
                const response = await fetch('/api/tasks', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title, description, priority, due_date: dueDate, project, is_backlog: isBacklog
                    })
                });
                const result = await response.json();

                if (result.ok) {
                    closeAddTaskModal();
                    loadStats();
                    loadRecentActivity();
                    alert('Task added successfully!');
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Failed to add task: ' + error);
            }
        }

        async function loadTaskStats() {
            try {
                const response = await fetch('/api/tasks/stats');
                const stats = await response.json();
                document.getElementById('tasks-total').textContent = stats.total_active;
                document.getElementById('tasks-due-today').textContent = stats.due_today;
            } catch (error) {
                console.error('Failed to load task stats:', error);
            }
        }

        // Search
        let searchTimeout = null;

        document.getElementById('global-search').addEventListener('input', (e) => {
            const query = e.target.value.trim();
            clearTimeout(searchTimeout);

            if (query.length < 2) {
                document.getElementById('search-results').style.display = 'none';
                return;
            }

            searchTimeout = setTimeout(async () => {
                await performSearch(query);
            }, 300);
        });

        async function performSearch(query) {
            try {
                const response = await fetch('/api/dashboard/search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query })
                });
                const results = await response.json();
                const resultsDiv = document.getElementById('search-results');

                if (results.length === 0) {
                    resultsDiv.innerHTML = '<div style="padding:20px;text-align:center;color:#555;">No results found</div>';
                    resultsDiv.style.display = 'block';
                    return;
                }

                resultsDiv.innerHTML = results.map(r => {
                    const icon = r.type === 'memory' ? '🧠' : r.type === 'person' ? '👤' : '🏠';
                    return `
                        <div class="search-result-item" onclick="window.location.href='${r.link}'">
                            <div class="search-result-icon">${icon}</div>
                            <div class="search-result-content">
                                <div class="search-result-title">${r.title}</div>
                                <div class="search-result-subtitle">${r.subtitle}</div>
                            </div>
                        </div>
                    `;
                }).join('');

                resultsDiv.style.display = 'block';
            } catch (error) {
                console.error('Search failed:', error);
            }
        }

        document.addEventListener('click', (e) => {
            if (!e.target.closest('.search-container')) {
                document.getElementById('search-results').style.display = 'none';
            }
        });

        // Settings
        async function loadPreferences() {
            try {
                const response = await fetch('/api/user/preferences');
                const prefs = await response.json();

                if (prefs.theme === 'light') {
                    document.body.classList.add('light-theme');
                } else {
                    document.body.classList.remove('light-theme');
                }

                window.userPreferences = prefs;

                if (window.statsInterval) {
                    clearInterval(window.statsInterval);
                }
                const intervalMs = prefs.auto_refresh_interval * 1000;
                window.statsInterval = setInterval(() => {
                    loadStats();
                    loadRecentActivity();
                    loadSystemHealth();
                }, intervalMs);

            } catch (error) {
                console.error('Failed to load preferences:', error);
            }
        }

        function openSettingsModal() {
            const prefs = window.userPreferences || {};
            document.getElementById('pref-theme').value = prefs.theme || 'dark';
            document.getElementById('pref-default-page').value = prefs.default_page || '/';
            document.getElementById('pref-refresh-interval').value = prefs.auto_refresh_interval || 30;
            document.getElementById('settings-modal').style.display = 'flex';
        }

        function closeSettingsModal() {
            document.getElementById('settings-modal').style.display = 'none';
        }

        async function savePreferences() {
            const theme = document.getElementById('pref-theme').value;
            const defaultPage = document.getElementById('pref-default-page').value;
            const refreshInterval = parseInt(document.getElementById('pref-refresh-interval').value);

            try {
                const response = await fetch('/api/user/preferences', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        theme,
                        default_page: defaultPage,
                        auto_refresh_interval: refreshInterval
                    })
                });
                const result = await response.json();

                if (result.ok) {
                    closeSettingsModal();
                    alert('Preferences saved! Reloading...');
                    window.location.reload();
                } else {
                    alert('Error saving preferences');
                }
            } catch (error) {
                alert('Failed to save preferences: ' + error);
            }
        }

        // Charts
        let memoryGrowthChart = null;
        let importanceChart = null;
        let entityStatusChart = null;

        async function loadCharts() {
            try {
                const response = await fetch('/api/dashboard/charts');
                const data = await response.json();

                // Memory Growth Line Chart
                const memoryCtx = document.getElementById('memory-growth-chart').getContext('2d');
                if (memoryGrowthChart) memoryGrowthChart.destroy();
                memoryGrowthChart = new Chart(memoryCtx, {
                    type: 'line',
                    data: {
                        labels: data.memory_growth.labels,
                        datasets: [{
                            label: 'Memories Created',
                            data: data.memory_growth.data,
                            borderColor: '#7eb8ff',
                            backgroundColor: 'rgba(126, 184, 255, 0.1)',
                            tension: 0.3,
                            fill: true
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: { color: '#888' },
                                grid: { color: '#2a2d37' }
                            },
                            x: {
                                ticks: { color: '#888' },
                                grid: { color: '#2a2d37' }
                            }
                        }
                    }
                });

                // People Importance Bar Chart
                const importanceCtx = document.getElementById('importance-chart').getContext('2d');
                if (importanceChart) importanceChart.destroy();
                importanceChart = new Chart(importanceCtx, {
                    type: 'bar',
                    data: {
                        labels: data.importance_distribution.labels,
                        datasets: [{
                            label: 'People Count',
                            data: data.importance_distribution.data,
                            backgroundColor: '#c792ea'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: { color: '#888' },
                                grid: { color: '#2a2d37' }
                            },
                            x: {
                                ticks: { color: '#888' },
                                grid: { color: '#2a2d37' }
                            }
                        }
                    }
                });

                // Entity Status Pie Chart
                const entityCtx = document.getElementById('entity-status-chart').getContext('2d');
                if (entityStatusChart) entityStatusChart.destroy();
                entityStatusChart = new Chart(entityCtx, {
                    type: 'pie',
                    data: {
                        labels: data.entity_status.labels,
                        datasets: [{
                            data: data.entity_status.data,
                            backgroundColor: ['#89ddff', '#444']
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true,
                        plugins: {
                            legend: {
                                position: 'bottom',
                                labels: { color: '#888' }
                            }
                        }
                    }
                });

            } catch (error) {
                console.error('Failed to load charts:', error);
            }
        }

        // Initialize
        loadPreferences();
        loadStats();
        loadRecentActivity();
        loadSystemHealth();
        loadCharts();

        // Auto-refresh will be set by loadPreferences based on user settings
    </script>
</body>
</html>
"""
