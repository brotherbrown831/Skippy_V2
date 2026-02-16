"""Reminders page for Skippy."""

import logging
from fastapi import APIRouter, Body
from fastapi.responses import HTMLResponse
import psycopg

from skippy.config import settings

logger = logging.getLogger("skippy")
router = APIRouter()


@router.get("/api/reminders")
async def get_reminders():
    """Get all reminders."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT reminder_id, event_id, event_summary, event_start,
                           reminded_at, acknowledged_at, snoozed_until, status,
                           created_at
                    FROM reminder_acknowledgments
                    WHERE user_id = %s
                    ORDER BY event_start DESC
                    LIMIT 100
                """, ("nolan",))
                rows = await cur.fetchall()
                columns = [desc.name for desc in cur.description]
                return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get reminders: {e}")
        return []


@router.get("/api/reminders/pending")
async def get_pending_reminders():
    """Get pending reminders."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT reminder_id, event_id, event_summary, event_start,
                           reminded_at, acknowledged_at, snoozed_until, status
                    FROM reminder_acknowledgments
                    WHERE user_id = %s
                      AND status = 'pending'
                      AND (snoozed_until IS NULL OR snoozed_until < NOW())
                    ORDER BY event_start
                """, ("nolan",))
                rows = await cur.fetchall()
                columns = [desc.name for desc in cur.description]
                return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get pending reminders: {e}")
        return []


@router.put("/api/reminders/{reminder_id}/acknowledge")
async def acknowledge_reminder(reminder_id: int):
    """Mark reminder as acknowledged."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE reminder_acknowledgments
                    SET status = 'acknowledged',
                        acknowledged_at = NOW(),
                        updated_at = NOW()
                    WHERE reminder_id = %s
                """, (reminder_id,))
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to acknowledge reminder: {e}")
        return {"success": False, "error": str(e)}


@router.put("/api/reminders/{reminder_id}/snooze")
async def snooze_reminder(reminder_id: int, data: dict = Body(...)):
    """Snooze reminder for X minutes."""
    minutes = data.get("minutes", 15)
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE reminder_acknowledgments
                    SET status = 'snoozed',
                        snoozed_until = NOW() + INTERVAL '%s minutes',
                        updated_at = NOW()
                    WHERE reminder_id = %s
                """, (minutes, reminder_id))
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to snooze reminder: {e}")
        return {"success": False, "error": str(e)}


@router.delete("/api/reminders/{reminder_id}")
async def delete_reminder(reminder_id: int):
    """Delete reminder."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM reminder_acknowledgments WHERE reminder_id = %s",
                    (reminder_id,)
                )
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to delete reminder: {e}")
        return {"success": False, "error": str(e)}


@router.get("/reminders", response_class=HTMLResponse)
async def reminders_page():
    """Serve the reminders page."""
    return REMINDERS_HTML


REMINDERS_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reminders - Skippy</title>
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

        h1 {
            font-size: 2rem;
            color: #fff;
            margin-bottom: 2rem;
        }

        h2 {
            color: #fbbc04;
            margin: 2rem 0 1rem 0;
            font-size: 1.3rem;
        }

        .section {
            background: #1a1d27;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }

        .reminder-card {
            background: #0a0d17;
            border: 1px solid #333;
            border-radius: 6px;
            padding: 1rem;
            margin-bottom: 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .reminder-info {
            flex: 1;
        }

        .reminder-event {
            font-weight: bold;
            color: #fff;
            margin-bottom: 0.5rem;
        }

        .reminder-time {
            color: #7eb8ff;
            font-size: 0.9rem;
        }

        .reminder-actions {
            display: flex;
            gap: 0.5rem;
        }

        .btn {
            padding: 0.5rem 1rem;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9rem;
        }

        .btn-acknowledge {
            background: #48bb78;
            color: white;
        }

        .btn-snooze {
            background: #fbbc04;
            color: #000;
        }

        .btn-delete {
            background: #f56565;
            color: white;
        }

        .btn:hover {
            opacity: 0.8;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
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

        .status-pending {
            color: #fbbc04;
        }

        .status-acknowledged {
            color: #48bb78;
        }

        .status-snoozed {
            color: #4299e1;
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
        <a href="/scheduled">Scheduled</a>
    </nav>

    <div class="container">
        <h1>🔔 Event Reminders</h1>

        <div class="section">
            <h2>⚡ Pending Reminders</h2>
            <div id="pendingReminders"></div>
        </div>

        <div class="section">
            <h2>📋 All Reminders</h2>
            <table>
                <thead>
                    <tr>
                        <th>Event</th>
                        <th>Event Time</th>
                        <th>Reminded At</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="remindersTable"></tbody>
            </table>
        </div>
    </div>

    <script>
        function formatDate(dateStr) {
            if (!dateStr) return '';
            const d = new Date(dateStr);
            return d.toLocaleString();
        }

        async function loadPendingReminders() {
            try {
                const res = await fetch('/api/reminders/pending');
                const reminders = await res.json();
                const container = document.getElementById('pendingReminders');

                if (!reminders || reminders.length === 0) {
                    container.innerHTML = '<div class="empty-state">No pending reminders</div>';
                    return;
                }

                container.innerHTML = reminders.map(r => `
                    <div class="reminder-card">
                        <div class="reminder-info">
                            <div class="reminder-event">${r.event_summary}</div>
                            <div class="reminder-time">Event: ${formatDate(r.event_start)}</div>
                        </div>
                        <div class="reminder-actions">
                            <button class="btn btn-acknowledge" onclick="acknowledgeReminder(${r.reminder_id})">✓ Acknowledge</button>
                            <button class="btn btn-snooze" onclick="snoozeReminder(${r.reminder_id}, 15)">⏱ Snooze 15m</button>
                        </div>
                    </div>
                `).join('');
            } catch (err) {
                console.error(err);
            }
        }

        async function loadAllReminders() {
            try {
                const res = await fetch('/api/reminders');
                const reminders = await res.json();
                const tbody = document.getElementById('remindersTable');

                if (!reminders || reminders.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No reminders</td></tr>';
                    return;
                }

                tbody.innerHTML = reminders.map(r => `
                    <tr>
                        <td>${r.event_summary}</td>
                        <td>${formatDate(r.event_start)}</td>
                        <td>${formatDate(r.reminded_at)}</td>
                        <td><span class="status-${r.status}">${r.status}</span></td>
                        <td>
                            ${r.status === 'pending' ? `<button class="btn btn-acknowledge" onclick="acknowledgeReminder(${r.reminder_id})">Acknowledge</button>` : ''}
                            <button class="btn btn-delete" onclick="deleteReminder(${r.reminder_id})">Delete</button>
                        </td>
                    </tr>
                `).join('');
            } catch (err) {
                console.error(err);
            }
        }

        async function acknowledgeReminder(id) {
            await fetch(`/api/reminders/${id}/acknowledge`, { method: 'PUT' });
            loadPendingReminders();
            loadAllReminders();
        }

        async function snoozeReminder(id, minutes) {
            await fetch(`/api/reminders/${id}/snooze`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ minutes }),
            });
            loadPendingReminders();
            loadAllReminders();
        }

        async function deleteReminder(id) {
            if (!confirm('Delete this reminder?')) return;
            await fetch(`/api/reminders/${id}`, { method: 'DELETE' });
            loadAllReminders();
        }

        loadPendingReminders();
        loadAllReminders();
    </script>
</body>
</html>
"""
