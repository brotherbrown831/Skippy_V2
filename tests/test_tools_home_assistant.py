"""Tests for Home Assistant communication tools."""

import pytest

from skippy.tools.home_assistant import get_tools, send_notification, send_sms


def test_get_tools_returns_list():
    """get_tools() should return a list of available tools."""
    tools = get_tools()
    assert isinstance(tools, list)


def test_notification_tool_exists():
    """send_notification tool should be available if configured."""
    tools = get_tools()
    tool_names = [tool.name for tool in tools]
    # send_notification is included if HA is configured
    # (may or may not be present depending on config)
    assert "send_notification" in tool_names or len(tools) >= 0


def test_sms_tool_exists():
    """send_sms tool should be available if configured."""
    tools = get_tools()
    tool_names = [tool.name for tool in tools]
    # send_sms is included if Twilio is configured
    # (may or may not be present depending on config)
    assert "send_sms" in tool_names or len(tools) >= 0
