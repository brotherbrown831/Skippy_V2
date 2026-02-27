"""Shared natural-language date/time parsing utility for Skippy."""

import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from skippy.config import settings

logger = logging.getLogger(__name__)


def parse_datetime(
    text: str,
    tz: ZoneInfo | None = None,
) -> datetime | None:
    """Parse a natural-language date/time string into a datetime.

    Handles:
    - Exact keywords: "today", "tomorrow", "tonight"
    - Relative + time: "tomorrow at noon", "today at 3pm", "tonight at 9"
    - Relative duration: "in 10 minutes", "in 2 hours", "in 3 days"
    - Weekdays: "friday", "next monday", "next tuesday at 2pm"
    - ISO format: "2026-02-21T12:00:00"
    - Absolute dates via dateutil: "Feb 25 at 3pm", "March 1"

    Args:
        text: The string to parse.
        tz: Timezone to use. Defaults to settings.timezone.

    Returns:
        A timezone-aware datetime, or None if parsing fails.
    """
    if not text:
        return None

    from dateutil import parser as dateutil_parser

    if tz is None:
        tz = ZoneInfo(settings.timezone)

    original = text.strip()
    lower = original.lower()
    now = datetime.now(tz)

    def _apply_time(time_str: str, base: datetime) -> datetime:
        """Parse a time expression and apply it to base date."""
        # Normalize "noon" / "midnight" before dateutil sees them
        t = time_str.strip().lower()
        if t in ("noon", "midday"):
            return base.replace(hour=12, minute=0, second=0, microsecond=0)
        if t == "midnight":
            return base.replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            parsed = dateutil_parser.parse(t, default=base)
            return base.replace(
                hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0
            )
        except (ValueError, TypeError):
            # Fallback: end of day
            return base.replace(hour=23, minute=59, second=59, microsecond=0)

    # ── Exact relative-day keywords ──────────────────────────────────────────
    if lower == "today":
        return now.replace(hour=23, minute=59, second=59, microsecond=0)
    if lower in ("tomorrow", "tmr", "tmrw"):
        return (now + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
    if lower == "tonight":
        return now.replace(hour=23, minute=59, second=59, microsecond=0)

    # ── "today/tomorrow/tonight [at] <time>" ────────────────────────────────
    m = re.match(r"^(today|tonight|tomorrow|tmr|tmrw)\s+(?:at\s+)?(.+)$", lower)
    if m:
        day_word, time_str = m.group(1), m.group(2)
        base = now if day_word in ("today", "tonight") else now + timedelta(days=1)
        return _apply_time(time_str, base)

    # ── "in X minutes/hours/days/weeks" ─────────────────────────────────────
    m = re.match(
        r"^in\s+(\d+)\s+(minute|minutes|min|mins|hour|hours|hr|hrs|day|days|week|weeks)$",
        lower,
    )
    if m:
        amount, unit = int(m.group(1)), m.group(2)
        if "min" in unit:
            return now + timedelta(minutes=amount)
        if "hour" in unit or unit in ("hr", "hrs"):
            return now + timedelta(hours=amount)
        if "day" in unit:
            return now + timedelta(days=amount)
        if "week" in unit:
            return now + timedelta(weeks=amount)

    # ── "[next] <weekday> [at <time>]" ──────────────────────────────────────
    weekdays = {
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1, "tues": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6,
    }
    m = re.match(r"^(?:next\s+)?(\w+)(?:\s+(?:at\s+)?(.+))?$", lower)
    if m and m.group(1) in weekdays:
        target_wd = weekdays[m.group(1)]
        days_ahead = (target_wd - now.weekday() + 7) % 7
        if days_ahead == 0:
            days_ahead = 7  # "next Monday" when today IS Monday → next week
        base = now + timedelta(days=days_ahead)
        time_str = m.group(2)
        if time_str:
            return _apply_time(time_str, base)
        return base.replace(hour=23, minute=59, second=59, microsecond=0)

    # ── ISO format ───────────────────────────────────────────────────────────
    try:
        dt = datetime.fromisoformat(original.replace("Z", "+00:00").replace("z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt
    except (ValueError, AttributeError):
        pass

    # ── dateutil fallback for absolute dates ("Feb 25 at 3pm", etc.) ────────
    try:
        parsed = dateutil_parser.parse(original, fuzzy=False)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=tz)
        has_time = bool(re.search(r"\d+:\d+|\d+\s*[ap]m|noon|midnight", lower))
        if not has_time:
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=0)
        return parsed
    except (ValueError, TypeError):
        pass

    logger.warning("Could not parse datetime: %r", original)
    return None
