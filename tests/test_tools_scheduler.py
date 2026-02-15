"""Tests for scheduler tools and helpers."""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from skippy.config import settings
from skippy.tools.scheduler import _parse_time
from skippy.scheduler.engine import _build_trigger


# --- Pure function tests ---


class TestParseTime:
    def test_3pm(self):
        result = _parse_time("3pm")
        assert result.hour == 15
        assert result.minute == 0

    def test_2_30pm(self):
        result = _parse_time("2:30pm")
        assert result.hour == 14
        assert result.minute == 30

    def test_24hr(self):
        result = _parse_time("15:00")
        assert result.hour == 15

    def test_9am(self):
        result = _parse_time("9AM")
        assert result.hour == 9

    def test_midnight(self):
        result = _parse_time("12:00AM")
        assert result.hour == 0

    def test_noon(self):
        result = _parse_time("12:00PM")
        assert result.hour == 12

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_time("not-a-time")

    def test_timezone_aware(self):
        result = _parse_time("3pm")
        assert result.tzinfo is not None


class TestBuildTrigger:
    def test_cron_trigger(self):
        trigger = _build_trigger("cron", {"hour": 8, "minute": 30})
        assert trigger is not None

    def test_interval_trigger(self):
        trigger = _build_trigger("interval", {"minutes": 60})
        assert trigger is not None

    def test_date_trigger(self):
        trigger = _build_trigger("date", {"run_date": "2026-12-31T23:59:00"})
        assert trigger is not None

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError):
            _build_trigger("bogus", {})
