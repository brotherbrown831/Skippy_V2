"""Tests for Google Calendar tools."""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from tests.conftest import requires_google_calendar

from skippy.config import settings
from skippy.tools.google_calendar import (
    _format_event,
    _format_event_with_date,
    _resolve_datetime,
    get_todays_events,
    get_upcoming_events,
)


# --- Pure function tests (no API needed) ---


class TestFormatEvent:
    def test_timed_event(self):
        event = {
            "summary": "Team Meeting",
            "start": {"dateTime": "2026-02-15T10:00:00-06:00"},
            "end": {"dateTime": "2026-02-15T11:00:00-06:00"},
        }
        result = _format_event(event)
        assert "Team Meeting" in result
        assert "10:00 AM" in result
        assert "11:00 AM" in result

    def test_all_day_event(self):
        event = {
            "summary": "Vacation",
            "start": {"date": "2026-02-15"},
            "end": {"date": "2026-02-16"},
        }
        result = _format_event(event)
        assert "Vacation" in result
        assert "All day" in result

    def test_event_with_location(self):
        event = {
            "summary": "Lunch",
            "location": "Cafe",
            "start": {"dateTime": "2026-02-15T12:00:00-06:00"},
            "end": {"dateTime": "2026-02-15T13:00:00-06:00"},
        }
        result = _format_event(event)
        assert "@ Cafe" in result

    def test_no_title(self):
        event = {
            "start": {"dateTime": "2026-02-15T09:00:00-06:00"},
            "end": {"dateTime": "2026-02-15T10:00:00-06:00"},
        }
        result = _format_event(event)
        assert "(no title)" in result


class TestFormatEventWithDate:
    def test_timed_event_includes_date(self):
        event = {
            "summary": "Standup",
            "start": {"dateTime": "2026-02-15T09:00:00-06:00"},
            "end": {"dateTime": "2026-02-15T09:15:00-06:00"},
        }
        result = _format_event_with_date(event)
        assert "Sun Feb 15" in result
        assert "Standup" in result

    def test_all_day_event_includes_date(self):
        event = {
            "summary": "Holiday",
            "start": {"date": "2026-02-16"},
            "end": {"date": "2026-02-17"},
        }
        result = _format_event_with_date(event)
        assert "Mon Feb 16" in result
        assert "All day" in result


class TestResolveDateTime:
    def test_today(self):
        tz = ZoneInfo(settings.timezone)
        result = _resolve_datetime("today", "10:00")
        assert result.date() == datetime.now(tz).date()
        assert result.hour == 10
        assert result.minute == 0

    def test_tomorrow(self):
        tz = ZoneInfo(settings.timezone)
        from datetime import timedelta
        result = _resolve_datetime("tomorrow", "3pm")
        expected_date = (datetime.now(tz) + timedelta(days=1)).date()
        assert result.date() == expected_date
        assert result.hour == 15

    def test_iso_date(self):
        result = _resolve_datetime("2026-03-01", "14:30")
        assert result.month == 3
        assert result.day == 1
        assert result.hour == 14
        assert result.minute == 30

    def test_12hr_with_pm(self):
        result = _resolve_datetime("today", "2:30pm")
        assert result.hour == 14
        assert result.minute == 30

    def test_12hr_with_am(self):
        result = _resolve_datetime("today", "9AM")
        assert result.hour == 9
        assert result.minute == 0

    def test_24hr(self):
        result = _resolve_datetime("today", "22:00")
        assert result.hour == 22

    def test_invalid_time_raises(self):
        with pytest.raises(ValueError):
            _resolve_datetime("today", "not-a-time")

    def test_invalid_date_raises(self):
        with pytest.raises(ValueError):
            _resolve_datetime("not-a-date", "10:00")


# --- Real API tests ---


@requires_google_calendar
def test_get_todays_events():
    """Should return a string (events or 'no events')."""
    result = get_todays_events.invoke({})
    assert isinstance(result, str)
    assert len(result) > 0


@requires_google_calendar
def test_get_upcoming_events():
    """Should return a string with upcoming events or 'no events'."""
    result = get_upcoming_events.invoke({"days": 7})
    assert isinstance(result, str)
    assert len(result) > 0
