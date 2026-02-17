"""Calendar events page for Skippy."""

import json
import logging
from fastapi import APIRouter, Body
from fastapi.responses import HTMLResponse

from skippy.tools.google_calendar import (
    get_todays_events,
    get_upcoming_events,
)
from .shared_ui import render_html_page, render_page_header, render_section

logger = logging.getLogger("skippy")
router = APIRouter()


@router.get("/api/calendar/today")
async def get_calendar_today():
    """Get today's calendar events."""
    try:
        result = await get_todays_events.ainvoke({})
        # Tool returns formatted string, parse it
        if isinstance(result, str):
            # Try to extract JSON from the string if present
            return parse_calendar_result(result)
        return result
    except Exception as e:
        logger.error(f"Failed to get today's events: {e}")
        return []


@router.get("/api/calendar/upcoming")
async def get_calendar_upcoming():
    """Get upcoming calendar events (next 7 days)."""
    try:
        result = await get_upcoming_events.ainvoke({"days": 7})
        if isinstance(result, str):
            return parse_calendar_result(result)
        return result
    except Exception as e:
        logger.error(f"Failed to get upcoming events: {e}")
        return []


def parse_calendar_result(result: str):
    """Parse calendar tool result into JSON."""
    events = []
    lines = result.split("\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("No events") or ":" not in line:
            continue
        # Try to extract event info
        events.append({"summary": line})
    return events


@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page():
    """Serve the calendar events page."""
    return CALENDAR_HTML


def get_calendar_html() -> str:
    """Generate calendar page using shared design system."""

    page_content = render_page_header(
        "📅 Calendar",
        "View and manage your Google Calendar events"
    )

    # Navigation controls
    controls_html = '''
        <div class="page-controls">
            <a href="/" class="btn btn-ghost">← Back to Dashboard</a>
        </div>'''

    # Today's events panel
    today_html = '''
        <div class="page-controls">
            <span class="text-muted">Today's Schedule</span>
        </div>
        <div id="todayEvents" class="event-list">
            <div class="text-center text-muted" style="padding: 20px;">Loading today's events...</div>
        </div>'''

    # Upcoming events panel
    upcoming_html = '''
        <div class="page-controls">
            <span class="text-muted">Next 7 Days</span>
        </div>
        <div id="upcomingEvents" class="event-list">
            <div class="text-center text-muted" style="padding: 20px;">Loading upcoming events...</div>
        </div>'''

    # Combine into sections
    page_content += controls_html
    page_content += render_section("Today", today_html)
    page_content += render_section("Upcoming Events", upcoming_html)

    scripts = '''
    <script>
        async function loadTodayEvents() {
            try {
                const res = await fetch('/api/calendar/today');
                const events = await res.json();
                const container = document.getElementById('todayEvents');

                if (!events || events.length === 0) {
                    container.innerHTML = '<div class="text-center text-muted" style="padding: 20px;">No events today</div>';
                    return;
                }

                container.innerHTML = events.map(e => `
                    <div class="event-card">
                        <div class="event-title">${e.summary || 'Untitled'}</div>
                        ${e.start ? `<div class="event-time">${e.start}</div>` : ''}
                        ${e.location ? `<div class="event-location">📍 ${e.location}</div>` : ''}
                    </div>
                `).join('');
            } catch (err) {
                console.error(err);
                document.getElementById('todayEvents').innerHTML = '<div class="text-center text-muted" style="padding: 20px;">Failed to load events</div>';
            }
        }

        async function loadUpcomingEvents() {
            try {
                const res = await fetch('/api/calendar/upcoming');
                const events = await res.json();
                const container = document.getElementById('upcomingEvents');

                if (!events || events.length === 0) {
                    container.innerHTML = '<div class="text-center text-muted" style="padding: 20px;">No upcoming events</div>';
                    return;
                }

                container.innerHTML = events.map(e => `
                    <div class="event-card">
                        <div class="event-title">${e.summary || 'Untitled'}</div>
                        ${e.start ? `<div class="event-time">${e.start}</div>` : ''}
                        ${e.location ? `<div class="event-location">📍 ${e.location}</div>` : ''}
                    </div>
                `).join('');
            } catch (err) {
                console.error(err);
                document.getElementById('upcomingEvents').innerHTML = '<div class="text-center text-muted" style="padding: 20px;">Failed to load events</div>';
            }
        }

        loadTodayEvents();
        loadUpcomingEvents();
    </script>

    <style>
        .event-list {
            display: flex;
            flex-direction: column;
            gap: var(--spacing-8);
        }

        .event-card {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            padding: var(--spacing-8);
            transition: all 0.2s ease;
        }

        .event-card:hover {
            border-color: var(--accent-blue);
            box-shadow: var(--shadow-md);
        }

        .event-title {
            font-weight: 600;
            color: var(--text-main);
            margin-bottom: var(--spacing-4);
        }

        .event-time {
            color: var(--accent-blue);
            font-size: 0.9rem;
            margin-bottom: var(--spacing-2);
        }

        .event-location {
            color: var(--text-muted);
            font-size: 0.85rem;
        }
    </style>
    '''

    return render_html_page("Calendar", page_content, extra_scripts=scripts)


CALENDAR_HTML = get_calendar_html()

