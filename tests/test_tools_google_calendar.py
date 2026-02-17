"""Tests for Google Calendar tools."""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from tests.conftest import requires_google_calendar

from skippy.config import settings
from skippy.tools.google_calendar import (
    _build_rrule,
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


class TestBuildRrule:
    def test_daily(self):
        result = _build_rrule("daily")
        assert result == "RRULE:FREQ=DAILY"

    def test_weekly(self):
        result = _build_rrule("weekly")
        assert result == "RRULE:FREQ=WEEKLY"

    def test_monthly(self):
        result = _build_rrule("monthly")
        assert result == "RRULE:FREQ=MONTHLY"

    def test_yearly(self):
        result = _build_rrule("yearly")
        assert result == "RRULE:FREQ=YEARLY"

    def test_case_insensitive(self):
        result = _build_rrule("DAILY")
        assert result == "RRULE:FREQ=DAILY"

    def test_unknown_frequency_raises(self):
        with pytest.raises(ValueError) as exc_info:
            _build_rrule("every_other_day")
        assert "Invalid frequency" in str(exc_info.value)

    def test_with_interval(self):
        result = _build_rrule("weekly", interval=2)
        assert result == "RRULE:FREQ=WEEKLY;INTERVAL=2"

    def test_interval_1_not_included(self):
        result = _build_rrule("weekly", interval=1)
        assert "INTERVAL" not in result

    def test_weekly_with_abbreviated_days(self):
        result = _build_rrule("weekly", days_of_week="MO,WE,FR")
        assert result == "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"

    def test_weekly_with_full_day_names(self):
        result = _build_rrule("weekly", days_of_week="Monday,Wednesday,Friday")
        assert result == "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"

    def test_weekly_with_mixed_day_formats(self):
        result = _build_rrule("weekly", days_of_week="Monday,WE,Friday")
        assert result == "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"

    def test_weekly_with_spaces_in_days(self):
        result = _build_rrule("weekly", days_of_week="Monday, Wednesday, Friday")
        assert result == "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"

    def test_with_count(self):
        result = _build_rrule("monthly", count=12)
        assert result == "RRULE:FREQ=MONTHLY;COUNT=12"

    def test_with_end_date(self):
        result = _build_rrule("daily", end_date="2026-12-31")
        assert result == "RRULE:FREQ=DAILY;UNTIL=20261231"

    def test_count_overrides_end_date(self):
        # If both are provided, count takes precedence
        result = _build_rrule("daily", end_date="2026-12-31", count=10)
        assert result == "RRULE:FREQ=DAILY;COUNT=10"
        assert "UNTIL" not in result

    def test_full_rrule_with_all_params(self):
        result = _build_rrule(
            "weekly",
            interval=2,
            days_of_week="Monday,Friday",
            count=20,
        )
        assert result == "RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,FR;COUNT=20"

    def test_invalid_day_raises(self):
        with pytest.raises(ValueError) as exc_info:
            _build_rrule("weekly", days_of_week="Monday,Funday")
        assert "Unrecognized day" in str(exc_info.value)

    def test_invalid_end_date_format_raises(self):
        with pytest.raises(ValueError) as exc_info:
            _build_rrule("daily", end_date="2026/12/31")
        assert "Invalid end_date format" in str(exc_info.value)


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
