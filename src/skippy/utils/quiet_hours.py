"""Quiet hours utility — suppresses non-critical notifications during sleep hours.

Rules:
  - Weekdays (Mon–Fri): active 07:00–21:30 (quiet before 7am and after 9:30pm)
  - Weekends (Sat–Sun): active 09:00–21:30 (quiet before 9am and after 9:30pm)

Non-critical notifications arriving during quiet hours are stored in the
notification_queue table and delivered when the next active window begins.
"""

import json
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from skippy.config import settings
from skippy.db_utils import get_db_connection

logger = logging.getLogger("skippy")

# Active-window boundaries (all times local)
_WEEKDAY_START = time(7, 0)   # 07:00 AM
_WEEKEND_START = time(9, 0)   # 09:00 AM
_ACTIVE_END = time(21, 30)    # 09:30 PM (every day)


def is_quiet_time(tz: str | None = None) -> bool:
    """Return True if the current local time falls inside quiet hours.

    Quiet hours:
      - Weekdays: before 07:00 or at/after 21:30
      - Weekends: before 09:00 or at/after 21:30
    """
    zone = ZoneInfo(tz or settings.timezone)
    now = datetime.now(zone)
    current = now.time()
    is_weekend = now.weekday() >= 5  # Saturday=5, Sunday=6
    active_start = _WEEKEND_START if is_weekend else _WEEKDAY_START
    return current < active_start or current >= _ACTIVE_END


def get_next_active_start(tz: str | None = None) -> datetime:
    """Return the datetime when the next active (non-quiet) window begins."""
    zone = ZoneInfo(tz or settings.timezone)
    now = datetime.now(zone)
    current = now.time()
    is_weekend = now.weekday() >= 5
    active_start = _WEEKEND_START if is_weekend else _WEEKDAY_START

    if current < active_start:
        # Before today's active window — window starts later today
        return now.replace(
            hour=active_start.hour,
            minute=active_start.minute,
            second=0,
            microsecond=0,
        )

    # After 21:30 — window starts tomorrow morning
    tomorrow = now + timedelta(days=1)
    is_tomorrow_weekend = tomorrow.weekday() >= 5
    tomorrow_start = _WEEKEND_START if is_tomorrow_weekend else _WEEKDAY_START
    return tomorrow.replace(
        hour=tomorrow_start.hour,
        minute=tomorrow_start.minute,
        second=0,
        microsecond=0,
    )


async def queue_notification(tool_name: str, params: dict) -> str:
    """Store a notification in the queue for delivery at the next active window.

    Args:
        tool_name: One of 'telegram', 'telegram_reminder', 'ha_push', 'sms'.
        params: Dict of kwargs to pass to the underlying send function.

    Returns:
        Human-readable confirmation string.
    """
    send_at = get_next_active_start()
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO notification_queue (tool_name, params, send_at)
                    VALUES (%s, %s::jsonb, %s)
                    """,
                    (tool_name, json.dumps(params), send_at),
                )
        logger.info("Queued %s notification for %s", tool_name, send_at.strftime("%H:%M"))
        return f"Quiet hours — queued for delivery at {send_at.strftime('%I:%M %p')}."
    except Exception:
        logger.exception("Failed to queue notification")
        return "Quiet hours and queue write failed — notification suppressed."
