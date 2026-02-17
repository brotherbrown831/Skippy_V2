"""Scheduled tasks page for Skippy."""

import json
import logging
from fastapi import APIRouter, Body
from fastapi.responses import HTMLResponse
from skippy.db_utils import get_db_connection

from skippy.config import settings
from .shared_ui import render_html_page, render_page_header, render_section

logger = logging.getLogger("skippy")
router = APIRouter()


@router.get("/api/scheduled_tasks")
async def get_scheduled_tasks():
    """Get all scheduled tasks."""
    try:
        async with get_db_connection() as conn:
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
        async with get_db_connection() as conn:
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


def get_scheduled_html() -> str:
    """Generate scheduled tasks page using shared design system."""

    page_content = render_page_header(
        "⏰ Scheduled Tasks",
        "View and manage your scheduled automation tasks"
    )

    # Info box
    info_html = '''
        <div style="background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: var(--spacing-8); color: var(--text-muted); font-size: 0.9rem;">
            <strong>Note:</strong> To create or delete scheduled tasks, use the chat interface with commands like "create a scheduled task" or "delete task [name]".
        </div>'''

    # Tasks table
    tasks_html = '''
        <table style="width: 100%; border-collapse: collapse;">
            <thead>
                <tr>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color);">Name</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color);">Type</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color);">Schedule</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color);">Source</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color);">Status</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color);">Actions</th>
                </tr>
            </thead>
            <tbody id="tasksTable"></tbody>
        </table>'''

    page_content += render_section("", info_html)
    page_content += render_section("", tasks_html)

    scripts = '''
    <script>
        async function loadTasks() {
            try {
                const res = await fetch('/api/scheduled_tasks');
                const tasks = await res.json();
                const tbody = document.getElementById('tasksTable');

                if (!tasks || tasks.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: var(--spacing-12);">No scheduled tasks</td></tr>';
                    return;
                }

                tbody.innerHTML = tasks.map(t => {
                    const schedule = t.schedule_config ? JSON.stringify(t.schedule_config) : 'N/A';
                    const typeColors = {
                        'cron': 'var(--accent-blue)',
                        'interval': '#48bb78',
                        'date': '#fbbc04',
                        'predefined': '#805ad5',
                        'chat': '#ed8936'
                    };
                    const typeColor = typeColors[t.schedule_type] || 'var(--accent-blue)';
                    const sourceColor = typeColors[t.source] || 'var(--accent-blue)';

                    return `
                        <tr style="border-bottom: 1px solid var(--border-color);">
                            <td style="padding: var(--spacing-8); color: var(--text-main); font-weight: 600;">${t.name}</td>
                            <td style="padding: var(--spacing-8);"><span style="color: ${typeColor}; font-size: 0.85rem; font-weight: 600;">${t.schedule_type}</span></td>
                            <td style="padding: var(--spacing-8); color: var(--text-muted); font-size: 0.85rem; font-family: monospace;">${schedule}</td>
                            <td style="padding: var(--spacing-8);"><span style="color: ${sourceColor}; font-size: 0.85rem; font-weight: 600;">${t.source}</span></td>
                            <td style="padding: var(--spacing-8); color: ${t.enabled ? '#48bb78' : 'var(--text-muted)'}">${t.enabled ? '✓ Enabled' : '✗ Disabled'}</td>
                            <td style="padding: var(--spacing-8);">
                                <button class="btn btn-secondary" onclick="toggleTask('${t.task_id}')" style="margin-right: var(--spacing-4);">
                                    ${t.enabled ? 'Disable' : 'Enable'}
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');
            } catch (err) {
                console.error(err);
                document.getElementById('tasksTable').innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: var(--spacing-12);">Failed to load tasks</td></tr>';
            }
        }

        async function toggleTask(taskId) {
            await fetch(`/api/scheduled_tasks/${taskId}/toggle`, { method: 'PUT' });
            loadTasks();
        }

        loadTasks();
        setInterval(loadTasks, 30000);
    </script>
    '''

    return render_html_page("Scheduled Tasks", page_content, extra_scripts=scripts)


SCHEDULED_HTML = get_scheduled_html()
