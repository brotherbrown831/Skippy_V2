"""Tests for Google Contacts sync tools."""

import pytest

from skippy.tools.contact_sync import _extract_birthday, _extract_notes


# --- Pure function tests ---


class TestExtractBirthday:
    def test_full_date(self):
        bdays = [{"date": {"year": 1990, "month": 6, "day": 15}}]
        assert _extract_birthday(bdays) == "1990-06-15"

    def test_no_year(self):
        bdays = [{"date": {"month": 12, "day": 25}}]
        assert _extract_birthday(bdays) == "12-25"

    def test_empty_list(self):
        assert _extract_birthday([]) == ""

    def test_missing_month(self):
        bdays = [{"date": {"day": 10}}]
        assert _extract_birthday(bdays) == ""

    def test_missing_day(self):
        bdays = [{"date": {"month": 3}}]
        assert _extract_birthday(bdays) == ""


class TestExtractNotes:
    def test_biography_only(self):
        person = {"biographies": [{"value": "Loves hiking"}]}
        assert _extract_notes(person) == "Loves hiking"

    def test_org_with_title(self):
        person = {"organizations": [{"title": "Engineer", "name": "Acme Corp"}]}
        assert _extract_notes(person) == "Engineer at Acme Corp"

    def test_org_without_title(self):
        person = {"organizations": [{"name": "Acme Corp"}]}
        assert _extract_notes(person) == "Acme Corp"

    def test_combined(self):
        person = {
            "biographies": [{"value": "Note 1"}],
            "organizations": [{"title": "CTO", "name": "Startup"}],
        }
        result = _extract_notes(person)
        assert "Note 1" in result
        assert "CTO at Startup" in result

    def test_empty(self):
        assert _extract_notes({}) == ""

    def test_empty_strings_ignored(self):
        person = {"biographies": [{"value": "  "}]}
        assert _extract_notes(person) == ""
