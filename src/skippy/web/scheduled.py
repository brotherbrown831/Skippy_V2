"""Scheduled tasks page for Skippy."""

import json
import logging
from fastapi import APIRouter, Body
from fastapi.responses import HTMLResponse
import psycopg

from skippy.config import settings

logger = logging.getLogger("skippy")
router = APIRouter()


@router.get("/api/scheduled_tasks")
async def get_scheduled_tasks():
    """Get all scheduled tasks."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT task_id, name, description, schedule_type,
                           schedule_config, enabled, source, created_at
                    FROM scheduled_tasks
                    ORDER BY created_at DESC
                """)
                rows = await cur.fetchall()
                columns = [desc.name for desc in cur.description]
                tasks = []
                for row in rows:
                    task_dict = dict(zip(columns, row))
                    # Parse schedule_config JSON
                    if isinstance(task_dict.get('schedule_config'), str):
                        try:
                            task_dict['schedule_config'] = json.loads(task_dict['schedule_config'])
                        except:
                            pass
                    tasks.append(task_dict)
                return tasks
    except Exception as e:
        logger.error(f"Failed to get scheduled tasks: {e}")
        return []


@router.post("/api/scheduled_tasks")
async def create_scheduled_task_api(data: dict = Body(...)):
    """Create new scheduled task (placeholder)."""
    return {"success": False, "message": "Use create_scheduled_task tool from chat"}


@router.put("/api/scheduled_tasks/{task_id}/toggle")
async def toggle_scheduled_task(task_id: str):
    """Enable/disable scheduled task."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE scheduled_tasks
                    SET enabled = NOT enabled
                    WHERE task_id = %s
                """, (task_id,))
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to toggle task: {e}")
        return {"success": False, "error": str(e)}


@router.delete("/api/scheduled_tasks/{task_id}")
async def delete_scheduled_task_api(task_id: str):
    """Delete scheduled task (placeholder)."""
    return {"success": False, "message": "Use delete_scheduled_task tool from chat"}


@router.get("/scheduled", response_class=HTMLResponse)
async def scheduled_page():
    """Serve the scheduled tasks page."""
    return SCHEDULED_HTML


SCHEDULED_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Scheduled Tasks - Skippy</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: #0a0d17;
            color: #e0e0e0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            padding: 1rem;
        }

        nav {
            background: #1a1d27;
            padding: 1rem 0;
            margin-bottom: 2rem;
            border-bottom: 1px solid #333;
        }

        nav a {
            color: #7eb8ff;
            text-decoration: none;
            margin: 0 1.5rem;
        }

        nav a:hover {
            color: #fff;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
        }

        h1 {
            font-size: 2rem;
            color: #fff;
        }

        .info-box {
            background: #1a1d27;
            border: 1px solid #666;
            border-radius: 6px;
            padding: 1rem;
            margin-bottom: 2rem;
            color: #999;
        }

        table {
            width: 100%;
            background: #1a1d27;
            border: 1px solid #333;
            border-radius: 8px;
            border-collapse: collapse;
            overflow: hidden;
        }

        th {
            background: #0a0d17;
            color: #7eb8ff;
            padding: 1rem;
            text-align: left;
            border-bottom: 1px solid #333;
        }

        td {
            padding: 1rem;
            border-bottom: 1px solid #333;
        }

        tr:hover {
            background: #0a0d17;
        }

        .badge {
            display: inline-block;
            padding: 0.3rem 0.8rem;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: bold;
        }

        .badge-cron {
            background: #4299e1;
            color: white;
        }

        .badge-interval {
            background: #48bb78;
            color: white;
        }

        .badge-date {
            background: #fbbc04;
            color: #000;
        }

        .badge-predefined {
            background: #805ad5;
            color: white;
        }

        .badge-chat {
            background: #ed8936;
            color: white;
        }

        .status-enabled {
            color: #48bb78;
        }

        .status-disabled {
            color: #888;
        }

        .btn {
            padding: 0.5rem 1rem;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9rem;
        }

        .btn-toggle {
            background: #4299e1;
            color: white;
        }

        .btn-delete {
            background: #f56565;
            color: white;
        }

        .btn:hover {
            opacity: 0.8;
        }

        .empty-state {
            text-align: center;
            color: #666;
            padding: 2rem;
        }
    </style>
</head>
<body>
    <nav>
        <a href="/">← Back to Dashboard</a>
        <a href="/memories">Memories</a>
        <a href="/people">People</a>
        <a href="/tasks">Tasks</a>
        <a href="/calendar">Calendar</a>
        <a href="/reminders">Reminders</a>
    </nav>

    <div class="container">
        <div class="header">
            <h1>⏰ Scheduled Tasks</h1>
        </div>

        <div class="info-box">
            <strong>Note:</strong> To create or delete scheduled tasks, use the chat interface with commands like "create a scheduled task" or "delete task [name]".
        </div>

        <table>
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Schedule</th>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody id="tasksTable"></tbody>
        </table>
    </div>

    <script>
        async function loadTasks() {
            try {
                const res = await fetch('/api/scheduled_tasks');
                const tasks = await res.json();
                const tbody = document.getElementById('tasksTable');

                if (!tasks || tasks.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No scheduled tasks</td></tr>';
                    return;
                }

                tbody.innerHTML = tasks.map(t => {
                    const schedule = t.schedule_config ? JSON.stringify(t.schedule_config) : 'N/A';
                    return `
                        <tr>
                            <td><strong>${t.name}</strong></td>
                            <td><span class="badge badge-${t.schedule_type}">${t.schedule_type}</span></td>
                            <td><code>${schedule}</code></td>
                            <td><span class="badge badge-${t.source}">${t.source}</span></td>
                            <td><span class="status-${t.enabled ? 'enabled' : 'disabled'}">
                                ${t.enabled ? '✓ Enabled' : '✗ Disabled'}
                            </span></td>
                            <td>
                                <button class="btn btn-toggle" onclick="toggleTask('${t.task_id}')">
                                    ${t.enabled ? 'Disable' : 'Enable'}
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');
            } catch (err) {
                console.error(err);
                document.getElementById('tasksTable').innerHTML = '<tr><td colspan="6">Failed to load tasks</td></tr>';
            }
        }

        async function toggleTask(taskId) {
            await fetch(`/api/scheduled_tasks/${taskId}/toggle`, { method: 'PUT' });
            loadTasks();
        }

        loadTasks();
        setInterval(loadTasks, 30000);
    </script>
</body>
</html>
"""
