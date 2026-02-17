"""Tests for ICS calendar tools."""

import pytest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from skippy.config import settings
from skippy.tools.ics_calendar import (
    _get_events_in_range,
    _format_event,
    _format_event_with_date,
    get_ics_todays_events,
    get_ics_upcoming_events,
    search_ics_events,
)


# Minimal valid ICS calendar for testing
MINIMAL_ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
UID:event1@example.com
DTSTART:20260217T100000Z
DTEND:20260217T110000Z
SUMMARY:Team Practice
LOCATION:Field A
DESCRIPTION:Weekly team practice
END:VEVENT
BEGIN:VEVENT
UID:event2@example.com
DTSTART:20260218T140000Z
DTEND:20260218T150000Z
SUMMARY:Game vs Rivals
LOCATION:Stadium
DESCRIPTION:Championship game
END:VEVENT
BEGIN:VEVENT
UID:event3@example.com
DTSTART:20260301
DTEND:20260302
SUMMARY:Tournament Day
DESCRIPTION:All-day event
END:VEVENT
END:VCALENDAR"""


class TestGetEventsInRange:
    """Test _get_events_in_range helper function."""

    def test_events_in_range_returned(self):
        """Events within the date range should be returned."""
        start = datetime(2026, 2, 17, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 20, 0, 0, 0, tzinfo=timezone.utc)

        events = _get_events_in_range(MINIMAL_ICS, start, end)

        assert len(events) == 3
        assert events[0]["summary"] == "Team Practice"
        assert events[1]["summary"] == "Game vs Rivals"
        assert events[2]["summary"] == "Tournament Day"

    def test_events_outside_range_excluded(self):
        """Events outside the date range should be excluded."""
        start = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 19, 0, 0, 0, tzinfo=timezone.utc)

        events = _get_events_in_range(MINIMAL_ICS, start, end)

        # Only the Game vs Rivals event (14:00 on 2/18) should match
        assert len(events) == 1
        assert events[0]["summary"] == "Game vs Rivals"

    def test_all_day_event_handled(self):
        """All-day events (date only) should be handled correctly."""
        start = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 3, 0, 0, 0, tzinfo=timezone.utc)

        events = _get_events_in_range(MINIMAL_ICS, start, end)

        assert len(events) == 1
        assert events[0]["summary"] == "Tournament Day"

    def test_events_sorted_by_start_time(self):
        """Events should be sorted by start time."""
        start = datetime(2026, 2, 17, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 19, 0, 0, 0, tzinfo=timezone.utc)

        events = _get_events_in_range(MINIMAL_ICS, start, end)

        assert events[0]["summary"] == "Team Practice"  # 10:00
        assert events[1]["summary"] == "Game vs Rivals"  # 14:00

    def test_invalid_ics_returns_empty_list(self):
        """Invalid ICS content should return empty list without crashing."""
        invalid_ics = b"This is not valid ICS content at all"
        start = datetime(2026, 2, 17, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 2, 20, 0, 0, 0, tzinfo=timezone.utc)

        events = _get_events_in_range(invalid_ics, start, end)

        assert events == []


class TestFormatEvent:
    """Test _format_event helper (same-day view)."""

    def test_timed_event_formatted(self):
        """Timed event should include time range."""
        event = {
            "summary": "Team Practice",
            "location": "Field A",
            "start": datetime(2026, 2, 17, 10, 0, 0, tzinfo=timezone.utc),
            "end": datetime(2026, 2, 17, 11, 0, 0, tzinfo=timezone.utc),
        }

        result = _format_event(event)

        assert "Team Practice" in result
        assert "Field A" in result
        assert ("10:00" in result or "10" in result)  # Time format may vary

    def test_all_day_event_formatted(self):
        """All-day event should show 'All day'."""
        event = {
            "summary": "Tournament Day",
            "location": "",
            "start": datetime(2026, 3, 1).date(),
            "end": datetime(2026, 3, 2).date(),
        }

        result = _format_event(event)

        assert "Tournament Day" in result
        assert "All day" in result

    def test_event_without_location(self):
        """Event without location should not have trailing @."""
        event = {
            "summary": "Practice",
            "location": "",
            "start": datetime(2026, 2, 17, 10, 0, 0, tzinfo=timezone.utc),
            "end": datetime(2026, 2, 17, 11, 0, 0, tzinfo=timezone.utc),
        }

        result = _format_event(event)

        assert " @ " not in result


class TestFormatEventWithDate:
    """Test _format_event_with_date helper (multi-day view)."""

    def test_timed_event_with_date_formatted(self):
        """Timed event should include date and time."""
        event = {
            "summary": "Game vs Rivals",
            "location": "Stadium",
            "start": datetime(2026, 2, 18, 14, 0, 0, tzinfo=timezone.utc),
            "end": datetime(2026, 2, 18, 15, 0, 0, tzinfo=timezone.utc),
        }

        result = _format_event_with_date(event)

        assert "Game vs Rivals" in result
        assert "Stadium" in result
        assert ("Feb" in result or "02" in result)  # Date format may vary

    def test_all_day_event_with_date_formatted(self):
        """All-day event should show date and 'All day'."""
        event = {
            "summary": "Tournament",
            "location": "",
            "start": datetime(2026, 3, 1).date(),
            "end": datetime(2026, 3, 2).date(),
        }

        result = _format_event_with_date(event)

        assert "Tournament" in result
        assert "All day" in result
        assert ("Mar" in result or "03" in result)


# --- Integration Tests (require ICS_CALENDAR_URL configured) ---

requires_ics_configured = pytest.mark.skipif(
    not settings.ics_calendar_url,
    reason="ICS_CALENDAR_URL not configured",
)


@requires_ics_configured
@pytest.mark.asyncio
async def test_get_ics_todays_events_returns_string():
    """get_ics_todays_events should return a string."""
    result = await get_ics_todays_events.ainvoke({})
    assert isinstance(result, str)


@requires_ics_configured
@pytest.mark.asyncio
async def test_get_ics_upcoming_events_returns_string():
    """get_ics_upcoming_events should return a string."""
    result = await get_ics_upcoming_events.ainvoke({"days": 7})
    assert isinstance(result, str)


@requires_ics_configured
@pytest.mark.asyncio
async def test_get_ics_upcoming_events_custom_days():
    """get_ics_upcoming_events should accept custom days parameter."""
    result = await get_ics_upcoming_events.ainvoke({"days": 14})
    assert isinstance(result, str)


@requires_ics_configured
@pytest.mark.asyncio
async def test_search_ics_events_returns_string():
    """search_ics_events should return a string."""
    result = await search_ics_events.ainvoke({"query": "game"})
    assert isinstance(result, str)


@requires_ics_configured
@pytest.mark.asyncio
async def test_search_ics_events_no_matches():
    """search_ics_events should handle no matches gracefully."""
    result = await search_ics_events.ainvoke(
        {"query": "xyzabc123nonexistent"}
    )
    assert isinstance(result, str)
    assert "No" in result or "found" in result.lower()
