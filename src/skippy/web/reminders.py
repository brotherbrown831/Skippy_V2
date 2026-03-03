"""Reminders page for Skippy."""

import logging
from fastapi import APIRouter, Body
from fastapi.responses import HTMLResponse
from skippy.db_utils import get_db_connection

from skippy.config import settings
from .shared_ui import render_html_page, render_page_header, render_section

logger = logging.getLogger("skippy")
router = APIRouter()


@router.get("/api/reminders")
async def get_reminders():
    """Get all reminders."""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT reminder_id, event_id, event_summary, event_start,
                           reminded_at, acknowledged_at, snoozed_until, status,
                           last_sent_at, retry_count, created_at
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
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT reminder_id, event_id, event_summary, event_start,
                           reminded_at, acknowledged_at, snoozed_until, status,
                           last_sent_at, retry_count
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
        async with get_db_connection() as conn:
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
        async with get_db_connection() as conn:
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
        async with get_db_connection() as conn:
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


def get_reminders_html() -> str:
    """Generate reminders page using shared design system."""

    page_content = render_page_header(
        "🔔 Event Reminders",
        "Manage upcoming event reminders and notifications"
    )

    # Navigation controls
    controls_html = '''
        <div class="page-controls">
            <a href="/" class="btn btn-ghost">← Back to Dashboard</a>
        </div>'''

    # Pending reminders section
    pending_html = '''
        <div id="pendingReminders"></div>'''

    # All reminders section
    all_reminders_html = '''
        <table style="width: 100%; border-collapse: collapse; margin-top: var(--spacing-12);">
            <thead>
                <tr>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color);">Event</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color);">Event Time</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color);">Reminded At</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color);">Status</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color);">Follow-ups</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color);">Actions</th>
                </tr>
            </thead>
            <tbody id="remindersTable"></tbody>
        </table>'''

    # Combine into sections
    page_content += controls_html
    page_content += render_section("⚡ Pending Reminders", pending_html)
    page_content += render_section("📋 All Reminders", all_reminders_html)

    scripts = '''
    <script>
        const MAX_RETRIES = 3;

        function formatDate(dateStr) {
            if (!dateStr) return '';
            const d = new Date(dateStr);
            return d.toLocaleString();
        }

        function formatRelative(dateStr) {
            if (!dateStr) return '—';
            const diff = Math.round((Date.now() - new Date(dateStr)) / 60000);
            if (diff < 1) return 'just now';
            if (diff < 60) return `${diff}m ago`;
            const h = Math.floor(diff / 60);
            return `${h}h ${diff % 60}m ago`;
        }

        function retryBadge(retryCount) {
            if (retryCount === 0) return '<span style="color: var(--text-muted);">none</span>';
            const color = retryCount >= MAX_RETRIES ? '#f56565' : retryCount >= 2 ? '#ed8936' : 'var(--accent-blue)';
            return `<span style="color: ${color}; font-weight: 600;">${retryCount} / ${MAX_RETRIES}</span>`;
        }

        async function loadPendingReminders() {
            try {
                const res = await fetch('/api/reminders/pending');
                const reminders = await res.json();
                const container = document.getElementById('pendingReminders');

                if (!reminders || reminders.length === 0) {
                    container.innerHTML = '<div class="text-center text-muted" style="padding: var(--spacing-12);">No pending reminders</div>';
                    return;
                }

                container.innerHTML = reminders.map(r => {
                    const retried = r.retry_count > 0;
                    const maxed = r.retry_count >= MAX_RETRIES;
                    const followUpLine = retried
                        ? `<div style="color: ${maxed ? '#f56565' : '#ed8936'}; font-size: 0.85rem; margin-top: var(--spacing-4);">
                               ${maxed ? '⚠️ Max follow-ups reached' : `🔁 Followed up ${r.retry_count}/${MAX_RETRIES} times`}
                               · last sent ${formatRelative(r.last_sent_at)}
                           </div>`
                        : '';
                    return `
                    <div style="background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: var(--spacing-8); margin-bottom: var(--spacing-8); display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <div style="font-weight: 600; color: var(--text-main); margin-bottom: var(--spacing-4);">${r.event_summary}</div>
                            <div style="color: var(--accent-blue); font-size: 0.9rem;">Event: ${formatDate(r.event_start)}</div>
                            ${followUpLine}
                        </div>
                        <div style="display: flex; gap: var(--spacing-4);">
                            <button class="btn btn-primary" onclick="acknowledgeReminder(${r.reminder_id})">✓ Acknowledge</button>
                            <button class="btn btn-secondary" onclick="snoozeReminder(${r.reminder_id}, 15)">⏱ Snooze 15m</button>
                        </div>
                    </div>`;
                }).join('');
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
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: var(--spacing-12);">No reminders</td></tr>';
                    return;
                }

                tbody.innerHTML = reminders.map(r => {
                    const statusColor = r.status === 'pending' ? 'var(--accent-blue)' : r.status === 'acknowledged' ? '#48bb78' : '#4299e1';
                    const followUp = r.retry_count > 0
                        ? `${retryBadge(r.retry_count)}<br><span style="color: var(--text-muted); font-size: 0.8rem;">${formatRelative(r.last_sent_at)}</span>`
                        : retryBadge(0);
                    return `
                    <tr style="border-bottom: 1px solid var(--border-color);">
                        <td style="padding: var(--spacing-8); color: var(--text-main);">${r.event_summary}</td>
                        <td style="padding: var(--spacing-8); color: var(--text-main);">${formatDate(r.event_start)}</td>
                        <td style="padding: var(--spacing-8); color: var(--text-main);">${formatDate(r.reminded_at)}</td>
                        <td style="padding: var(--spacing-8);"><span style="color: ${statusColor};">${r.status}</span></td>
                        <td style="padding: var(--spacing-8);">${followUp}</td>
                        <td style="padding: var(--spacing-8);">
                            ${r.status === 'pending' ? `<button class="btn btn-primary" onclick="acknowledgeReminder(${r.reminder_id})" style="margin-right: var(--spacing-4);">Acknowledge</button>` : ''}
                            <button class="btn btn-danger" onclick="deleteReminder(${r.reminder_id})">Delete</button>
                        </td>
                    </tr>`;
                }).join('');
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
    '''

    return render_html_page("Event Reminders", page_content, extra_scripts=scripts)


REMINDERS_HTML = get_reminders_html()
