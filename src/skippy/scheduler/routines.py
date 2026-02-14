"""Predefined scheduled routines for Skippy."""

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from skippy.config import settings

PREDEFINED_ROUTINES = [
    {
        "task_id": "morning-briefing",
        "name": "Morning Briefing",
        "prompt": (
            "Check today's calendar events and send a push notification to Nolan "
            "with a brief summary of what's on the schedule today. Include event times "
            "and titles. If there are no events, still send a notification saying the "
            "day is clear. Be your usual snarky self in the notification."
        ),
        "trigger": CronTrigger(hour=7, minute=0, timezone=settings.timezone),
    },
    {
        "task_id": "evening-summary",
        "name": "Evening Summary",
        "prompt": (
            "Check tomorrow's calendar events and send a push notification to Nolan "
            "with a brief preview of what's coming up tomorrow. If there's nothing "
            "on the calendar, say so. Keep it short and snarky."
        ),
        "trigger": CronTrigger(hour=22, minute=0, timezone=settings.timezone),
    },
    {
        "task_id": "upcoming-event-check",
        "name": "Upcoming Event Reminder",
        "prompt": (
            "Check if there are any calendar events starting in the next 30 minutes. "
            "If there are, send a push notification reminding Nolan about each one "
            "with the event title and start time. If there are no upcoming events in "
            "the next 30 minutes, do NOT send a notification — just respond with "
            "'No upcoming events.'"
        ),
        "trigger": IntervalTrigger(minutes=30),
    },
]

# Direct-function routines — these call a function directly instead of
# going through the agent graph (no LLM call needed for data sync jobs).
DIRECT_ROUTINES = [
    {
        "task_id": "google-contacts-sync",
        "name": "Google Contacts Sync",
        "func": "skippy.tools.contact_sync:sync_google_contacts_to_people",
        "trigger": CronTrigger(hour=2, minute=0, timezone=settings.timezone),
    },
]
