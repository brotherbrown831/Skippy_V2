"""Tests for Gmail tools."""

import base64
import pytest
from tests.conftest import requires_google_oauth

from skippy.tools.gmail import _decode_body, _parse_headers, check_inbox, search_emails


# --- Pure function tests ---


class TestParseHeaders:
    def test_basic(self):
        headers = [
            {"name": "From", "value": "alice@example.com"},
            {"name": "Subject", "value": "Hello"},
            {"name": "Date", "value": "Mon, 15 Feb 2026"},
        ]
        result = _parse_headers(headers, "From", "Subject")
        assert result["From"] == "alice@example.com"
        assert result["Subject"] == "Hello"

    def test_case_insensitive(self):
        headers = [{"name": "FROM", "value": "bob@example.com"}]
        result = _parse_headers(headers, "From")
        assert result["From"] == "bob@example.com"

    def test_missing_header(self):
        headers = [{"name": "From", "value": "alice@example.com"}]
        result = _parse_headers(headers, "Subject")
        assert "Subject" not in result


class TestDecodeBody:
    def test_simple_text(self):
        text = "Hello, world!"
        encoded = base64.urlsafe_b64encode(text.encode()).decode()
        payload = {"mimeType": "text/plain", "body": {"data": encoded}}
        assert _decode_body(payload) == text

    def test_multipart(self):
        text = "Multipart body"
        encoded = base64.urlsafe_b64encode(text.encode()).decode()
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": encoded}},
                {"mimeType": "text/html", "body": {"data": "irrelevant"}},
            ],
        }
        assert _decode_body(payload) == text

    def test_empty_payload(self):
        payload = {"mimeType": "multipart/mixed", "parts": []}
        result = _decode_body(payload)
        assert "Could not extract" in result


# --- Real API tests ---


@requires_google_oauth
def test_check_inbox():
    """Should return a string about inbox contents."""
    result = check_inbox.invoke({"max_results": 3})
    assert isinstance(result, str)
    assert len(result) > 0


@requires_google_oauth
def test_search_emails():
    """Should return search results or 'no results'."""
    result = search_emails.invoke({"query": "is:read", "max_results": 2})
    assert isinstance(result, str)
