"""Google Calendar tools for Skippy — full read/write calendar access."""

import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from skippy.config import settings

logger = logging.getLogger("skippy")

# Module-level calendar service, initialized lazily
_service = None


def _get_calendar_service():
    """Build and cache the Google Calendar API service client."""
    global _service
    if _service is not None:
        return _service

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_file(
        settings.google_service_account_json,
        scopes=["https://www.googleapis.com/auth/calendar"],
    )
    _service = build("calendar", "v3", credentials=credentials)
    return _service


def _format_event(event: dict) -> str:
    """Format a single calendar event into a readable string."""
    summary = event.get("summary", "(no title)")
    location = event.get("location", "")

    start = event.get("start", {})
    end = event.get("end", {})

    if "dateTime" in start:
        start_str = datetime.fromisoformat(start["dateTime"]).strftime("%I:%M %p")
        end_str = datetime.fromisoformat(end["dateTime"]).strftime("%I:%M %p")
        time_str = f"{start_str} - {end_str}"
    else:
        time_str = "All day"

    result = f"- {summary} ({time_str})"
    if location:
        result += f" @ {location}"
    return result


def _format_event_with_date(event: dict) -> str:
    """Format event with its date included (for multi-day queries)."""
    summary = event.get("summary", "(no title)")
    location = event.get("location", "")
    start = event.get("start", {})
    end = event.get("end", {})

    if "dateTime" in start:
        dt = datetime.fromisoformat(start["dateTime"])
        date_str = dt.strftime("%a %b %d")
        start_str = dt.strftime("%I:%M %p")
        end_str = datetime.fromisoformat(end["dateTime"]).strftime("%I:%M %p")
        time_str = f"{date_str}, {start_str} - {end_str}"
    else:
        date_str = datetime.fromisoformat(start["date"]).strftime("%a %b %d")
        time_str = f"{date_str} (All day)"

    result = f"- {summary} ({time_str})"
    if location:
        result += f" @ {location}"
    return result


# --- Read tools ---


@tool
def get_todays_events() -> str:
    """Get all events on today's calendar. Use this when the user asks what's
    on their schedule today, what meetings they have, or what they're doing today."""
    try:
        service = _get_calendar_service()
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        result = service.events().list(
            calendarId=settings.google_calendar_id,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = result.get("items", [])
        if not events:
            return "No events on the calendar today."

        lines = [_format_event(e) for e in events]
        return f"Today's events ({len(events)}):\n" + "\n".join(lines)
    except Exception as e:
        logger.error("Failed to fetch today's events: %s", e)
        return f"Error reading calendar: {e}"


@tool
def get_upcoming_events(days: int = 7) -> str:
    """Get upcoming calendar events for the next N days. Use this when the user
    asks about their upcoming schedule, what's coming up this week, or plans
    for the next few days. The days parameter controls how far ahead to look
    (defaults to 7)."""
    try:
        service = _get_calendar_service()
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days)

        result = service.events().list(
            calendarId=settings.google_calendar_id,
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=25,
        ).execute()

        events = result.get("items", [])
        if not events:
            return f"No events in the next {days} days."

        lines = [_format_event_with_date(e) for e in events]
        return f"Upcoming events (next {days} days, {len(events)} found):\n" + "\n".join(lines)
    except Exception as e:
        logger.error("Failed to fetch upcoming events: %s", e)
        return f"Error reading calendar: {e}"


@tool
def search_events(query: str) -> str:
    """Search calendar events by keyword. Use this when the user asks about a
    specific event, meeting, or appointment by name. Searches the next 30 days."""
    try:
        service = _get_calendar_service()
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=30)

        result = service.events().list(
            calendarId=settings.google_calendar_id,
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            q=query,
            singleEvents=True,
            orderBy="startTime",
            maxResults=10,
        ).execute()

        events = result.get("items", [])
        if not events:
            return f'No events matching "{query}" in the next 30 days.'

        lines = [_format_event_with_date(e) for e in events]
        return f'Events matching "{query}" ({len(events)} found):\n' + "\n".join(lines)
    except Exception as e:
        logger.error("Failed to search events: %s", e)
        return f"Error searching calendar: {e}"


# --- Date/time helpers ---


def _resolve_datetime(date_str: str, time_str: str) -> datetime:
    """Resolve a date and time string into a timezone-aware datetime.

    date_str: 'today', 'tomorrow', or 'YYYY-MM-DD'
    time_str: '10pm', '10:00 PM', '22:00', '14:30', etc.
    """
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)

    # Resolve date
    date_lower = date_str.strip().lower()
    if date_lower == "today":
        date = now.date()
    elif date_lower == "tomorrow":
        date = (now + timedelta(days=1)).date()
    else:
        date = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()

    # Resolve time — handle formats like "10pm", "10:00 PM", "22:00", "2:30pm"
    time_clean = time_str.strip().upper().replace(" ", "")
    try:
        # Try 24-hour format first: "22:00", "14:30"
        if re.match(r"^\d{1,2}:\d{2}$", time_clean):
            t = datetime.strptime(time_clean, "%H:%M").time()
        # "10:00PM", "2:30AM"
        elif re.match(r"^\d{1,2}:\d{2}[AP]M$", time_clean):
            t = datetime.strptime(time_clean, "%I:%M%p").time()
        # "10PM", "2AM"
        elif re.match(r"^\d{1,2}[AP]M$", time_clean):
            t = datetime.strptime(time_clean, "%I%p").time()
        else:
            # Last resort: try parsing as-is
            t = datetime.strptime(time_clean, "%H:%M").time()
    except ValueError:
        raise ValueError(f"Could not parse time: '{time_str}'")

    return datetime.combine(date, t, tzinfo=tz)


def _to_iso(dt: datetime) -> str:
    """Format a datetime as ISO 8601 with timezone offset."""
    return dt.isoformat()


def _build_rrule(
    frequency: str,
    interval: int = 1,
    days_of_week: str = "",
    end_date: str = "",
    count: int = 0,
) -> str:
    """Build an RFC 5545 RRULE string for Google Calendar API.

    Args:
        frequency: "daily", "weekly", "monthly", or "yearly"
        interval: Repeat every N periods (default 1). E.g., interval=2 means every 2 weeks.
        days_of_week: For weekly events, comma-separated days: "Monday,Wednesday,Friday"
                      or already abbreviated: "MO,WE,FR" (normalized either way)
        end_date: End recurrence on this date (YYYY-MM-DD format), converted to UNTIL=YYYYMMDD
        count: Maximum number of occurrences. If set, overrides end_date.

    Returns:
        RRULE string like "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=10"

    Raises:
        ValueError: If frequency is unknown.
    """
    # Normalize frequency to uppercase
    freq_upper = frequency.lower().strip().upper()
    if freq_upper not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        raise ValueError(
            f"Invalid frequency '{frequency}'. Must be: daily, weekly, monthly, or yearly"
        )

    parts = [f"FREQ={freq_upper}"]

    # Add interval if > 1
    if interval > 1:
        parts.append(f"INTERVAL={interval}")

    # Normalize days_of_week if provided (for weekly events)
    if days_of_week:
        days_map = {
            "monday": "MO",
            "tuesday": "TU",
            "wednesday": "WE",
            "thursday": "TH",
            "friday": "FR",
            "saturday": "SA",
            "sunday": "SU",
        }

        # Split by comma and normalize each day
        day_list = [d.strip() for d in days_of_week.split(",")]
        normalized_days = []
        for day in day_list:
            day_lower = day.lower()
            if day_lower in days_map:
                # Full name like "Monday" → "MO"
                normalized_days.append(days_map[day_lower])
            elif day.upper() in ("MO", "TU", "WE", "TH", "FR", "SA", "SU"):
                # Already abbreviated, keep as-is
                normalized_days.append(day.upper())
            else:
                raise ValueError(f"Unrecognized day: '{day}'")

        parts.append(f"BYDAY={','.join(normalized_days)}")

    # Add end date as UNTIL if provided and no count
    if end_date and count == 0:
        try:
            end_dt = datetime.strptime(end_date.strip(), "%Y-%m-%d")
            until_str = end_dt.strftime("%Y%m%d")
            parts.append(f"UNTIL={until_str}")
        except ValueError:
            raise ValueError(f"Invalid end_date format. Use YYYY-MM-DD, got '{end_date}'")

    # Add count if provided (takes precedence over end_date)
    if count > 0:
        parts.append(f"COUNT={count}")

    return "RRULE:" + ";".join(parts)


# --- Write tools ---


@tool
def create_event(
    title: str,
    date: str,
    start_time: str,
    end_time: str = "",
    description: str = "",
    location: str = "",
) -> str:
    """Create a new Google Calendar event. Use this when the user asks to add
    something to their calendar or schedule an event.

    Args:
        title: The event title/summary.
        date: The date for the event. Use 'today', 'tomorrow', or 'YYYY-MM-DD' format.
        start_time: Start time like '10pm', '2:30pm', '14:00', or '10:00 AM'.
        end_time: End time in the same format. If not provided, defaults to 1 hour after start.
        description: Optional event description or notes.
        location: Optional event location.
    """
    try:
        service = _get_calendar_service()

        start_dt = _resolve_datetime(date, start_time)
        if end_time:
            end_dt = _resolve_datetime(date, end_time)
        else:
            end_dt = start_dt + timedelta(hours=1)

        event_body = {
            "summary": title,
            "start": {"dateTime": _to_iso(start_dt)},
            "end": {"dateTime": _to_iso(end_dt)},
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location

        created = service.events().insert(
            calendarId=settings.google_calendar_id,
            body=event_body,
        ).execute()

        event_id = created.get("id", "unknown")
        link = created.get("htmlLink", "")
        formatted_start = start_dt.strftime("%B %d, %Y at %I:%M %p %Z")
        logger.info("Calendar event created: id=%s, title='%s', start=%s", event_id, title, formatted_start)
        return f"Event '{title}' created for {formatted_start} (id: {event_id}). Link: {link}"
    except Exception as e:
        logger.error("Failed to create event: %s", e)
        return f"Error creating event: {e}"


@tool
def create_recurring_event(
    title: str,
    start_date: str,
    start_time: str,
    frequency: str,
    end_time: str = "",
    description: str = "",
    location: str = "",
    interval: int = 1,
    days_of_week: str = "",
    end_date: str = "",
    count: int = 0,
) -> str:
    """Create a recurring Google Calendar event. Use this when the user asks to
    schedule a repeating event like "gym every Monday" or "team meeting every
    other Thursday".

    Args:
        title: The event title/summary.
        start_date: Starting date for the recurrence. Use 'today', 'tomorrow', or 'YYYY-MM-DD'.
        start_time: Start time like '10pm', '2:30pm', '14:00', or '10:00 AM'.
        frequency: Recurrence frequency: "daily", "weekly", "monthly", or "yearly".
        end_time: End time in the same format as start_time. If not provided, defaults to 1 hour after start.
        description: Optional event description or notes.
        location: Optional event location.
        interval: Repeat every N periods. Default 1 (every week, every month, etc).
                  Example: interval=2 with frequency="weekly" means every 2 weeks.
        days_of_week: For weekly events, comma-separated days like "Monday,Wednesday,Friday"
                      or abbreviated "MO,WE,FR". Required for weekly recurrence if you want
                      specific days; otherwise repeats on the starting day.
        end_date: Stop recurrence on this date (YYYY-MM-DD format). If omitted, recurs indefinitely.
        count: Maximum number of occurrences. If set, overrides end_date.
               Example: count=10 creates exactly 10 occurrences.
    """
    try:
        service = _get_calendar_service()

        start_dt = _resolve_datetime(start_date, start_time)
        if end_time:
            end_dt = _resolve_datetime(start_date, end_time)
        else:
            end_dt = start_dt + timedelta(hours=1)

        # Build RRULE
        rrule = _build_rrule(
            frequency=frequency,
            interval=interval,
            days_of_week=days_of_week,
            end_date=end_date,
            count=count,
        )

        event_body = {
            "summary": title,
            "start": {"dateTime": _to_iso(start_dt)},
            "end": {"dateTime": _to_iso(end_dt)},
            "recurrence": [rrule],
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location

        created = service.events().insert(
            calendarId=settings.google_calendar_id,
            body=event_body,
        ).execute()

        event_id = created.get("id", "unknown")
        link = created.get("htmlLink", "")
        formatted_start = start_dt.strftime("%B %d, %Y at %I:%M %p %Z")
        freq_label = frequency.lower()
        suffix = f" (every {interval} {freq_label}s)" if interval > 1 else f" ({freq_label})"
        if count > 0:
            suffix += f", {count} occurrences"
        elif end_date:
            suffix += f", until {end_date}"

        logger.info(
            "Recurring calendar event created: id=%s, title='%s', start=%s, rrule=%s",
            event_id,
            title,
            formatted_start,
            rrule,
        )
        return f"Recurring event '{title}' created{suffix}, starting {formatted_start} (id: {event_id}). Link: {link}"
    except Exception as e:
        logger.error("Failed to create recurring event: %s", e)
        return f"Error creating recurring event: {e}"


@tool
def update_event(
    event_id: str,
    title: str = "",
    date: str = "",
    start_time: str = "",
    end_time: str = "",
    description: str = "",
    location: str = "",
) -> str:
    """Update an existing Google Calendar event. Use this when the user asks to
    change, reschedule, or modify a calendar event. You need the event_id from
    a previous search or listing. Only provide the fields you want to change.

    Args:
        event_id: The Google Calendar event ID (from search or listing results).
        title: New event title (leave empty to keep current).
        date: New date as 'today', 'tomorrow', or 'YYYY-MM-DD' (leave empty to keep current).
        start_time: New start time like '10pm', '2:30pm', '14:00' (leave empty to keep current).
        end_time: New end time in the same format (leave empty to keep current).
        description: New description (leave empty to keep current).
        location: New location (leave empty to keep current).
    """
    try:
        service = _get_calendar_service()

        existing = service.events().get(
            calendarId=settings.google_calendar_id,
            eventId=event_id,
        ).execute()

        if title:
            existing["summary"] = title
        if date and start_time:
            existing["start"] = {"dateTime": _to_iso(_resolve_datetime(date, start_time))}
        if date and end_time:
            existing["end"] = {"dateTime": _to_iso(_resolve_datetime(date, end_time))}
        if description:
            existing["description"] = description
        if location:
            existing["location"] = location

        updated = service.events().update(
            calendarId=settings.google_calendar_id,
            eventId=event_id,
            body=existing,
        ).execute()

        logger.info("Calendar event updated: id=%s", event_id)
        return f"Event '{updated.get('summary', '')}' updated successfully."
    except Exception as e:
        logger.error("Failed to update event: %s", e)
        return f"Error updating event: {e}"


@tool
def delete_event(event_id: str) -> str:
    """Delete a Google Calendar event. Use this when the user asks to remove
    or cancel a calendar event. You need the event_id from a previous search
    or listing.

    Args:
        event_id: The Google Calendar event ID to delete.
    """
    try:
        service = _get_calendar_service()

        # Fetch the event first so we can confirm what was deleted
        existing = service.events().get(
            calendarId=settings.google_calendar_id,
            eventId=event_id,
        ).execute()
        title = existing.get("summary", "(no title)")

        service.events().delete(
            calendarId=settings.google_calendar_id,
            eventId=event_id,
        ).execute()

        logger.info("Calendar event deleted: id=%s, title='%s'", event_id, title)
        return f"Event '{title}' deleted successfully."
    except Exception as e:
        logger.error("Failed to delete event: %s", e)
        return f"Error deleting event: {e}"


def get_tools() -> list:
    """Return Google Calendar tools if credentials are configured."""
    if settings.google_service_account_json and settings.google_calendar_id:
        return [
            get_todays_events,
            get_upcoming_events,
            search_events,
            create_event,
            create_recurring_event,
            update_event,
            delete_event,
        ]
    return []
