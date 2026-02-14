"""Google Calendar tools for Skippy — full read/write calendar access."""

import logging
from datetime import datetime, timedelta, timezone

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


# --- Write tools ---


@tool
def create_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
) -> str:
    """Create a new Google Calendar event. Use this when the user asks to add
    something to their calendar or schedule an event.

    Args:
        title: The event title/summary.
        start_time: Start time in ISO 8601 format (e.g. '2026-02-15T14:00:00-06:00').
        end_time: End time in ISO 8601 format (e.g. '2026-02-15T15:00:00-06:00').
        description: Optional event description or notes.
        location: Optional event location.
    """
    try:
        service = _get_calendar_service()

        event_body = {
            "summary": title,
            "start": {"dateTime": start_time},
            "end": {"dateTime": end_time},
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
        logger.info("Calendar event created: id=%s, title='%s'", event_id, title)
        return f"Event '{title}' created successfully (id: {event_id}). Link: {link}"
    except Exception as e:
        logger.error("Failed to create event: %s", e)
        return f"Error creating event: {e}"


@tool
def update_event(
    event_id: str,
    title: str = "",
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
        start_time: New start time in ISO 8601 format (leave empty to keep current).
        end_time: New end time in ISO 8601 format (leave empty to keep current).
        description: New description (leave empty to keep current).
        location: New location (leave empty to keep current).
    """
    try:
        service = _get_calendar_service()

        # Fetch current event first
        existing = service.events().get(
            calendarId=settings.google_calendar_id,
            eventId=event_id,
        ).execute()

        if title:
            existing["summary"] = title
        if start_time:
            existing["start"] = {"dateTime": start_time}
        if end_time:
            existing["end"] = {"dateTime": end_time}
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
            update_event,
            delete_event,
        ]
    return []
