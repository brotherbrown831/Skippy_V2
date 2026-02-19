"""ICS Calendar feed tools for Skippy — read-only access to public .ics URLs."""

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from langchain_core.tools import tool
import httpx
import icalendar
import recurring_ical_events

from skippy.config import settings

logger = logging.getLogger("skippy")


async def _fetch_ics_calendar() -> bytes:
    """Fetch the raw ICS bytes from the configured URL."""
    async with httpx.AsyncClient(timeout=10.0, verify=False, follow_redirects=True) as client:
        resp = await client.get(settings.ics_calendar_url)
        resp.raise_for_status()
        return resp.content


def _get_events_in_range(ics_bytes: bytes, start: datetime, end: datetime) -> list[dict]:
    """Parse ICS content and return events in [start, end) as dicts.

    Handles recurring events (RRULE), timezone normalization, and all-day events.
    """
    try:
        cal = icalendar.Calendar.from_ical(ics_bytes)
        raw_events = recurring_ical_events.of(cal).between(start, end)
    except Exception as e:
        logger.error("Failed to parse ICS calendar: %s", e)
        return []

    events = []
    for event in raw_events:
        try:
            dtstart_component = event.get("DTSTART")
            dtend_component = event.get("DTEND")

            if dtstart_component is None:
                continue

            dtstart = dtstart_component.dt
            dtend = dtend_component.dt if dtend_component else dtstart

            # Normalize to datetime if it's a date (all-day event)
            if isinstance(dtstart, type(dtstart)) and not hasattr(dtstart, "hour"):
                # It's a date, not datetime — convert to datetime at midnight
                dtstart = datetime.combine(dtstart, datetime.min.time()).replace(
                    tzinfo=timezone.utc
                )
            if isinstance(dtend, type(dtend)) and not hasattr(dtend, "hour"):
                dtend = datetime.combine(dtend, datetime.min.time()).replace(
                    tzinfo=timezone.utc
                )

            events.append(
                {
                    "summary": str(event.get("SUMMARY", "(no title)")),
                    "location": str(event.get("LOCATION", "") or ""),
                    "description": str(event.get("DESCRIPTION", "") or ""),
                    "start": dtstart,
                    "end": dtend,
                }
            )
        except Exception as e:
            logger.warning("Failed to parse event in ICS calendar: %s", e)
            continue

    events.sort(key=lambda e: e["start"])
    return events


def _format_event(event: dict) -> str:
    """Format an ICS event for today's view (time only)."""
    summary = event.get("summary", "(no title)")
    location = event.get("location", "")

    start = event.get("start")
    end = event.get("end")

    if start and hasattr(start, "hour"):
        # It's a datetime
        start_str = start.strftime("%I:%M %p")
        end_str = end.strftime("%I:%M %p") if end else start_str
        time_str = f"{start_str} - {end_str}"
        iso_hint = f" [start_iso: {start.isoformat()}]"
    else:
        # All-day event or missing time
        time_str = "All day"
        iso_hint = f" [start_iso: {start.isoformat() if start else ''}]"

    result = f"- {summary} ({time_str}){iso_hint}"
    if location:
        result += f" @ {location}"
    return result


def _format_event_with_date(event: dict) -> str:
    """Format an ICS event for multi-day view (date + time)."""
    summary = event.get("summary", "(no title)")
    location = event.get("location", "")

    start = event.get("start")
    end = event.get("end")

    if start and hasattr(start, "hour"):
        # It's a datetime
        date_str = start.strftime("%a %b %d")
        start_str = start.strftime("%I:%M %p")
        end_str = end.strftime("%I:%M %p") if end else start_str
        time_str = f"{date_str}, {start_str} - {end_str}"
        iso_hint = f" [start_iso: {start.isoformat()}]"
    else:
        # All-day event or missing time
        if start:
            # Might be a date or datetime — try to get a date
            if hasattr(start, "date"):
                date_obj = start.date()
            else:
                date_obj = start
            date_str = date_obj.strftime("%a %b %d")
            time_str = f"{date_str} (All day)"
        else:
            time_str = "(no date)"
        iso_hint = f" [start_iso: {start.isoformat() if start else ''}]"

    result = f"- {summary} ({time_str}){iso_hint}"
    if location:
        result += f" @ {location}"
    return result


# --- Read tools ---


@tool
async def get_ics_todays_events() -> str:
    """Get today's events from the ICS calendar feed (e.g., TeamSnap sports schedule).
    Use this when the user asks what's on their schedule today or what sports/activities
    they have scheduled for today."""
    try:
        ics_bytes = await _fetch_ics_calendar()

        tz = ZoneInfo(settings.timezone)
        now = datetime.now(tz)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        events = _get_events_in_range(ics_bytes, start_of_day, end_of_day)

        if not events:
            return f"No events on the {settings.ics_calendar_name} calendar today."

        lines = [_format_event(e) for e in events]
        return f"Today's {settings.ics_calendar_name} events ({len(events)}):\n" + "\n".join(
            lines
        )
    except Exception as e:
        logger.error("Failed to fetch today's ICS events: %s", e)
        return f"Error reading {settings.ics_calendar_name} calendar: {e}"


@tool
async def get_ics_upcoming_events(days: int = 7) -> str:
    """Get upcoming events from the ICS calendar feed for the next N days.
    Use this when asking about upcoming sports games, activities, or events from
    the secondary calendar. The days parameter controls how far ahead to look (defaults to 7)."""
    try:
        ics_bytes = await _fetch_ics_calendar()

        tz = ZoneInfo(settings.timezone)
        now = datetime.now(tz)
        end = now + timedelta(days=days)

        events = _get_events_in_range(ics_bytes, now, end)

        if not events:
            return f"No events on the {settings.ics_calendar_name} calendar in the next {days} days."

        lines = [_format_event_with_date(e) for e in events]
        return f"Upcoming {settings.ics_calendar_name} events (next {days} days, {len(events)} found):\n" + "\n".join(
            lines
        )
    except Exception as e:
        logger.error("Failed to fetch upcoming ICS events: %s", e)
        return f"Error reading {settings.ics_calendar_name} calendar: {e}"


@tool
async def search_ics_events(query: str) -> str:
    """Search events in the ICS calendar feed by keyword. Searches the next 90 days."""
    try:
        ics_bytes = await _fetch_ics_calendar()

        tz = ZoneInfo(settings.timezone)
        now = datetime.now(tz)
        end = now + timedelta(days=90)

        events = _get_events_in_range(ics_bytes, now, end)

        # Filter by query (case-insensitive search in summary and location)
        query_lower = query.lower()
        filtered = [
            e
            for e in events
            if query_lower in e.get("summary", "").lower()
            or query_lower in e.get("location", "").lower()
            or query_lower in e.get("description", "").lower()
        ]

        if not filtered:
            return f'No {settings.ics_calendar_name} events matching "{query}" in the next 90 days.'

        lines = [_format_event_with_date(e) for e in filtered]
        return f'{settings.ics_calendar_name} events matching "{query}" ({len(filtered)} found):\n' + "\n".join(
            lines
        )
    except Exception as e:
        logger.error("Failed to search ICS events: %s", e)
        return f"Error searching {settings.ics_calendar_name} calendar: {e}"


def get_tools() -> list:
    """Return ICS calendar tools if URL is configured."""
    if settings.ics_calendar_url:
        return [get_ics_todays_events, get_ics_upcoming_events, search_ics_events]
    return []
