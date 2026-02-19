"""Predefined scheduled routines for Skippy."""

import logging
import math
from datetime import datetime, timezone

from skippy.db_utils import get_db_connection
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from skippy.config import settings
from skippy.utils.quiet_hours import is_quiet_time

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
        async with get_db_connection() as conn:
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


def _create_cron_trigger_from_time(time_str: str) -> CronTrigger | None:
    """Create CronTrigger from time string, or None if disabled.

    Args:
        time_str: "HH:MM" format or "disabled"

    Returns:
        CronTrigger if enabled, None if disabled
    """
    if time_str.lower() == "disabled":
        logger.info("Schedule disabled: %s", time_str)
        return None

    hour, minute = time_str.split(":")
    return CronTrigger(hour=int(hour), minute=int(minute), timezone=settings.timezone)


def _build_predefined_routines() -> list:
    """Build PREDEFINED_ROUTINES list based on config settings."""
    routines = []

    # Morning briefing
    morning_trigger = _create_cron_trigger_from_time(settings.morning_briefing_time)
    if morning_trigger:
        routines.append(
            {
                "task_id": "morning-briefing",
                "name": "Morning Briefing",
                "prompt": (
                    "Check today's calendar events and tasks, then send a Telegram message to Nolan "
                    "with a brief summary. Include: "
                    "1. Calendar events for today (times and titles) — check BOTH get_todays_events (Google Calendar) "
                    "   AND get_ics_todays_events (TeamSnap sports schedule) for a complete view. "
                    "2. Top 3 priority tasks for today (from tasks with high urgency_score or due today). "
                    "3. Number of overdue tasks (if any - nag about them). "
                    "4. One backlog item worth considering (highest backlog_rank if available). "
                    "If there are no events or tasks, still send a message saying the day is clear. "
                    "Be your usual snarky self. Use the send_telegram_message tool."
                ),
                "trigger": morning_trigger,
            }
        )

    # Evening summary
    evening_trigger = _create_cron_trigger_from_time(settings.evening_summary_time)
    if evening_trigger:
        routines.append(
            {
                "task_id": "evening-summary",
                "name": "Evening Summary",
                "prompt": (
                    "Check tomorrow's calendar and tasks, then send a Telegram message to Nolan "
                    "with a brief preview. Include: "
                    "1. Tomorrow's calendar events. "
                    "2. Tasks due tomorrow or marked as 'next_up' for tomorrow. "
                    "3. Completed tasks today (count and celebrate if any). "
                    "Keep it short and snarky. Use the send_telegram_message tool."
                ),
                "trigger": evening_trigger,
            }
        )

    # Upcoming event check (always enabled, uses interval from config)
    routines.append(
        {
            "task_id": "upcoming-event-check",
            "name": "Upcoming Event Reminder",
            "prompt": (
                "Ping: Check for calendar events in next 30 min using BOTH get_todays_events (Google Calendar) "
                "AND get_ics_upcoming_events(days=1) (TeamSnap sports schedule). Send Telegram reminders via "
                "send_telegram_message_with_reminder_buttons for events not in reminder_acknowledgments, "
                "or with snoozed_until < NOW(), or pending > 30 min. Include event_id, summary, start time. "
                "Silence if none."
            ),
            "trigger": IntervalTrigger(minutes=settings.calendar_check_interval_minutes),
        }
    )

    return routines


PREDEFINED_ROUTINES = _build_predefined_routines()


async def drain_notification_queue() -> None:
    """Send any queued notifications whose send_at time has passed.

    Runs every 5 minutes. Only processes items when not in quiet hours so that
    a notification queued for 07:00 is not sent at 06:59 due to scheduler drift.
    """
    if is_quiet_time():
        logger.debug("Quiet hours active — skipping notification queue drain")
        return

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT queue_id, tool_name, params
                    FROM notification_queue
                    WHERE status = 'pending' AND send_at <= NOW()
                    ORDER BY send_at ASC
                    LIMIT 20
                    """
                )
                rows = await cur.fetchall()

                if not rows:
                    return

                logger.info("Draining %d queued notification(s)", len(rows))

                for queue_id, tool_name, params in rows:
                    try:
                        if tool_name == "telegram":
                            from skippy.tools.telegram import _deliver_telegram
                            await _deliver_telegram(**params)

                        elif tool_name == "telegram_reminder":
                            # Re-invoke the full tool with is_critical=True to bypass quiet check
                            from skippy.tools.telegram import send_telegram_message_with_reminder_buttons
                            send_telegram_message_with_reminder_buttons.invoke(
                                {**params, "is_critical": True}
                            )

                        elif tool_name == "ha_push":
                            from skippy.tools.home_assistant import _deliver_ha_push
                            await _deliver_ha_push(**params)

                        elif tool_name == "sms":
                            from skippy.tools.home_assistant import _deliver_sms
                            await _deliver_sms(**params)

                        else:
                            logger.warning("Unknown queued tool: %s", tool_name)

                        await cur.execute(
                            "UPDATE notification_queue SET status = 'sent', sent_at = NOW() WHERE queue_id = %s",
                            (queue_id,),
                        )
                    except Exception as e:
                        logger.error("Failed to drain queued notification %d: %s", queue_id, e)
                        await cur.execute(
                            "UPDATE notification_queue SET status = 'failed', error_msg = %s WHERE queue_id = %s",
                            (str(e)[:500], queue_id),
                        )

    except Exception:
        logger.exception("Error in drain_notification_queue")


async def check_and_notify_snoozed_reminders() -> None:
    """Check for snoozed reminders that are due and send notifications.

    This job runs every 5 minutes to catch reminder snoozes when they expire.
    If a reminder's snoozed_until time has passed, it sends a Telegram message
    to remind the user and updates the status back to 'pending'.
    Skips processing entirely during quiet hours — the next run after quiet
    hours end will pick up any expired snoozes.
    """
    if is_quiet_time():
        logger.debug("Quiet hours active — skipping snoozed reminder check")
        return

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Find snoozed reminders that are due to wake up
                await cur.execute("""
                    SELECT reminder_id, event_id, event_summary, event_start
                    FROM reminder_acknowledgments
                    WHERE user_id = %s
                      AND status = 'snoozed'
                      AND snoozed_until <= NOW()
                    ORDER BY event_start
                """, ("nolan",))

                expired_snoozes = await cur.fetchall()

                if not expired_snoozes:
                    logger.debug("No snoozed reminders to wake up")
                    return

                # Update status back to pending
                reminder_ids = [r[0] for r in expired_snoozes]
                for reminder_id in reminder_ids:
                    await cur.execute("""
                        UPDATE reminder_acknowledgments
                        SET status = 'pending',
                            updated_at = NOW()
                        WHERE reminder_id = %s
                    """, (reminder_id,))

                logger.info(f"Woke up {len(expired_snoozes)} snoozed reminders")

                # Send Telegram notification for each
                for reminder_id, event_id, event_summary, event_start in expired_snoozes:
                    try:
                        # Import here to avoid circular imports
                        from skippy.tools.telegram import send_telegram_message

                        # Format event start time
                        if event_start:
                            event_time = event_start.strftime("%I:%M %p") if hasattr(event_start, 'strftime') else str(event_start)
                        else:
                            event_time = "Unknown"

                        message = f"⏰ Snooze expired: {event_summary} at {event_time}"
                        await send_telegram_message.ainvoke({
                            "message": message,
                            "thread_title": "Snooze Expiration"
                        })
                    except Exception as e:
                        logger.error(f"Failed to send snooze reminder for {event_summary}: {e}")

    except Exception as e:
        logger.error(f"Error in check_and_notify_snoozed_reminders: {e}")


def _build_direct_routines() -> list:
    """Build DIRECT_ROUTINES list based on config settings."""
    routines = []

    # Google Contacts sync
    sync_trigger = _create_cron_trigger_from_time(settings.google_contacts_sync_time)
    if sync_trigger:
        routines.append(
            {
                "task_id": "google-contacts-sync",
                "name": "Google Contacts Sync",
                "func": "skippy.tools.contact_sync:sync_google_contacts_to_people",
                "trigger": sync_trigger,
            }
        )

    # People importance recalculation
    recalc_trigger = _create_cron_trigger_from_time(
        settings.people_importance_recalc_time
    )
    if recalc_trigger:
        routines.append(
            {
                "task_id": "recalc-people-importance",
                "name": "Recalculate People Importance",
                "func": "skippy.scheduler.routines:recalculate_people_importance",
                "trigger": recalc_trigger,
            }
        )

    # Snooze check (runs every 5 minutes to catch reminder snooze expirations)
    routines.append(
        {
            "task_id": "check-snoozed-reminders",
            "name": "Snooze Reminder Check",
            "func": "skippy.scheduler.routines:check_and_notify_snoozed_reminders",
            "trigger": IntervalTrigger(minutes=5),
        }
    )

    # Notification queue drain (runs every 5 minutes to deliver quiet-hour deferred messages)
    routines.append(
        {
            "task_id": "drain-notification-queue",
            "name": "Notification Queue Drain",
            "func": "skippy.scheduler.routines:drain_notification_queue",
            "trigger": IntervalTrigger(minutes=5),
        }
    )

    return routines


# Direct-function routines — these call a function directly instead of
# going through the agent graph (no LLM call needed for data sync jobs).
DIRECT_ROUTINES = _build_direct_routines()
