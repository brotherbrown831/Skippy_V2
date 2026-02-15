"""Predefined scheduled routines for Skippy."""

import logging
import math
from datetime import datetime, timezone

import psycopg
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from skippy.config import settings

logger = logging.getLogger("skippy")


async def recalculate_people_importance() -> None:
    """Recalculate importance scores for all people to apply time decay.

    This job runs daily and recalculates importance_score using the exponential
    decay formula to ensure inactive people gradually drop in ranking.

    Formula:
    - base_score = min(mention_count * 2, 50)
    - days_since = days since last_mentioned
    - recency_bonus = 50 * exp(-days_since / 30)
    - importance_score = base_score + recency_bonus
    """
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Fetch all people with mention_count > 0
                await cur.execute(
                    """
                    SELECT person_id, mention_count, last_mentioned
                    FROM people
                    WHERE user_id = %s AND mention_count > 0
                    """,
                    ("nolan",),
                )
                rows = await cur.fetchall()

                now = datetime.now(timezone.utc)
                updated_count = 0

                for person_id, mention_count, last_mentioned in rows:
                    # Calculate base score
                    base_score = min(mention_count * 2, 50)

                    # Calculate recency bonus
                    if last_mentioned:
                        # If timezone-naive, assume UTC
                        if last_mentioned.tzinfo is None:
                            last_mentioned = last_mentioned.replace(tzinfo=timezone.utc)
                        days_since = (now - last_mentioned).days
                        recency_bonus = 50 * math.exp(-days_since / 30)
                    else:
                        recency_bonus = 0

                    importance_score = base_score + recency_bonus

                    # Update
                    await cur.execute(
                        """
                        UPDATE people
                        SET importance_score = %s, updated_at = NOW()
                        WHERE person_id = %s
                        """,
                        (importance_score, person_id),
                    )
                    updated_count += 1

                logger.info(
                    "Recalculated importance for %d people", updated_count
                )

    except Exception as e:
        logger.error("Failed to recalculate people importance: %s", e)


PREDEFINED_ROUTINES = [
    {
        "task_id": "morning-briefing",
        "name": "Morning Briefing",
        "prompt": (
            "Check today's calendar events and send a Telegram message to Nolan "
            "with a brief summary of what's on the schedule today. Include event times "
            "and titles. If there are no events, still send a message saying the "
            "day is clear. Be your usual snarky self in the message. "
            "Use the send_telegram_message tool."
        ),
        "trigger": CronTrigger(hour=7, minute=0, timezone=settings.timezone),
    },
    {
        "task_id": "evening-summary",
        "name": "Evening Summary",
        "prompt": (
            "Check tomorrow's calendar events and send a Telegram message to Nolan "
            "with a brief preview of what's coming up tomorrow. If there's nothing "
            "on the calendar, say so. Keep it short and snarky. "
            "Use the send_telegram_message tool."
        ),
        "trigger": CronTrigger(hour=22, minute=0, timezone=settings.timezone),
    },
    {
        "task_id": "upcoming-event-check",
        "name": "Upcoming Event Reminder",
        "prompt": (
            "Check if there are any calendar events starting in the next 30 minutes. "
            "For each upcoming event, check the reminder_acknowledgments table to see if "
            "a reminder has already been sent and acknowledged. Only send reminders for events that: "
            "1) Have never been reminded about (no row in reminder_acknowledgments), OR "
            "2) Were snoozed and the snooze time has passed (status='snoozed' AND snoozed_until < NOW()), OR "
            "3) Are pending but never acknowledged after 30 minutes (status='pending' AND reminded_at < NOW() - INTERVAL '30 minutes'). "
            "When sending a reminder, use send_telegram_message_with_reminder_buttons and pass the event_id, "
            "event_summary, and event_start so a reminder record can be created. "
            "If there are no events needing reminders, do NOT send a message — just respond with 'No upcoming events.'"
        ),
        "trigger": IntervalTrigger(minutes=settings.calendar_check_interval_minutes),
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
    {
        "task_id": "ha-entities-sync",
        "name": "Home Assistant Entities Sync",
        "func": "skippy.tools.ha_entity_sync:sync_ha_entities_to_db",
        "trigger": IntervalTrigger(minutes=30),
    },
    {
        "task_id": "recalc-people-importance",
        "name": "Recalculate People Importance",
        "func": "skippy.scheduler.routines:recalculate_people_importance",
        "trigger": CronTrigger(hour=3, minute=0, timezone=settings.timezone),
    },
]
