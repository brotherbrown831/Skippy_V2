"""Calendar events page for Skippy."""

import json
import logging
from fastapi import APIRouter, Body
from fastapi.responses import HTMLResponse

from skippy.tools.google_calendar import (
    get_todays_events,
    get_upcoming_events,
)

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


CALENDAR_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Calendar - Skippy</title>
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
            max-width: 1400px;
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

        button {
            background: #4285f4;
            color: white;
            border: none;
            padding: 0.75rem 1.5rem;
            border-radius: 4px;
            cursor: pointer;
            font-size: 1rem;
        }

        button:hover {
            background: #357ae8;
        }

        .two-column {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 2rem;
            margin-bottom: 2rem;
        }

        @media (max-width: 1024px) {
            .two-column {
                grid-template-columns: 1fr;
            }
        }

        .panel {
            background: #1a1d27;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 1.5rem;
        }

        .panel h2 {
            margin-bottom: 1rem;
            color: #4285f4;
            font-size: 1.3rem;
        }

        .event-card {
            background: #0a0d17;
            border: 1px solid #333;
            border-radius: 6px;
            padding: 1rem;
            margin-bottom: 1rem;
        }

        .event-card:hover {
            border-color: #4285f4;
        }

        .event-title {
            font-weight: bold;
            color: #fff;
            margin-bottom: 0.5rem;
        }

        .event-time {
            color: #7eb8ff;
            font-size: 0.9rem;
            margin-bottom: 0.5rem;
        }

        .event-location {
            color: #999;
            font-size: 0.85rem;
        }

        .empty-state {
            text-align: center;
            color: #666;
            padding: 2rem;
        }

        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }

        .modal.active {
            display: flex;
        }

        .modal-content {
            background: #1a1d27;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 2rem;
            max-width: 500px;
            width: 90%;
        }

        .modal-content h2 {
            margin-bottom: 1.5rem;
            color: #fff;
        }

        .form-group {
            margin-bottom: 1rem;
        }

        .form-group label {
            display: block;
            margin-bottom: 0.5rem;
            color: #7eb8ff;
        }

        .form-group input,
        .form-group textarea {
            width: 100%;
            padding: 0.75rem;
            background: #0a0d17;
            border: 1px solid #333;
            color: #e0e0e0;
            border-radius: 4px;
            font-family: inherit;
        }

        .form-group textarea {
            resize: vertical;
            min-height: 80px;
        }

        .modal-buttons {
            display: flex;
            gap: 1rem;
            justify-content: flex-end;
            margin-top: 1.5rem;
        }

        .btn-cancel {
            background: #666;
        }

        .btn-cancel:hover {
            background: #777;
        }
    </style>
</head>
<body>
    <nav>
        <a href="/">← Back to Dashboard</a>
        <a href="/memories">Memories</a>
        <a href="/people">People</a>
        <a href="/tasks">Tasks</a>
        <a href="/reminders">Reminders</a>
        <a href="/scheduled">Scheduled</a>
    </nav>

    <div class="container">
        <div class="header">
            <h1>📅 Calendar Events</h1>
            <button onclick="showCreateModal()">+ New Event</button>
        </div>

        <div class="two-column">
            <div class="panel">
                <h2>Today</h2>
                <div id="todayEvents"></div>
            </div>

            <div class="panel">
                <h2>Upcoming (7 Days)</h2>
                <div id="upcomingEvents"></div>
            </div>
        </div>
    </div>

    <div id="eventModal" class="modal">
        <div class="modal-content">
            <h2>New Event</h2>
            <form id="eventForm">
                <div class="form-group">
                    <label>Title</label>
                    <input type="text" name="title" required>
                </div>
                <div class="form-group">
                    <label>Date</label>
                    <input type="date" name="date" required>
                </div>
                <div class="form-group">
                    <label>Start Time</label>
                    <input type="time" name="start_time">
                </div>
                <div class="form-group">
                    <label>End Time</label>
                    <input type="time" name="end_time">
                </div>
                <div class="form-group">
                    <label>Location</label>
                    <input type="text" name="location">
                </div>
                <div class="form-group">
                    <label>Description</label>
                    <textarea name="description"></textarea>
                </div>
                <div class="modal-buttons">
                    <button type="button" class="btn-cancel" onclick="closeModal()">Cancel</button>
                    <button type="submit">Create Event</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        async function loadTodayEvents() {
            try {
                const res = await fetch('/api/calendar/today');
                const events = await res.json();
                const container = document.getElementById('todayEvents');

                if (!events || events.length === 0) {
                    container.innerHTML = '<div class="empty-state">No events today</div>';
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
                document.getElementById('todayEvents').innerHTML = '<div class="empty-state">Failed to load events</div>';
            }
        }

        async function loadUpcomingEvents() {
            try {
                const res = await fetch('/api/calendar/upcoming');
                const events = await res.json();
                const container = document.getElementById('upcomingEvents');

                if (!events || events.length === 0) {
                    container.innerHTML = '<div class="empty-state">No upcoming events</div>';
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
                document.getElementById('upcomingEvents').innerHTML = '<div class="empty-state">Failed to load events</div>';
            }
        }

        function showCreateModal() {
            document.getElementById('eventModal').classList.add('active');
        }

        function closeModal() {
            document.getElementById('eventModal').classList.remove('active');
        }

        document.getElementById('eventForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            // Form submission would be implemented with create_event tool
            alert('Event creation not yet implemented');
            closeModal();
        });

        // Initialize
        loadTodayEvents();
        loadUpcomingEvents();
    </script>
</body>
</html>
"""
