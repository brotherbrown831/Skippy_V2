"""Tests for Telegram tools."""

import pytest
from tests.conftest import requires_telegram

from skippy.tools.telegram import _parse_chat_ids, send_telegram_message


# --- Pure function tests ---


class TestParseChatIds:
    def test_single(self):
        assert _parse_chat_ids("12345") == [12345]

    def test_multiple(self):
        assert _parse_chat_ids("111,222,333") == [111, 222, 333]

    def test_whitespace(self):
        assert _parse_chat_ids("  111 , 222 ") == [111, 222]

    def test_empty(self):
        assert _parse_chat_ids("") == []

    def test_invalid_skipped(self):
        result = _parse_chat_ids("111,abc,333")
        assert result == [111, 333]


# --- Real API test ---


@requires_telegram
def test_send_telegram_message():
    """Send a real test message to the configured chat."""
    result = send_telegram_message.invoke({"message": "[pytest] Test message — ignore this."})
    assert isinstance(result, str)
    assert "sent" in result.lower() or "success" in result.lower() or "chat" in result.lower()
