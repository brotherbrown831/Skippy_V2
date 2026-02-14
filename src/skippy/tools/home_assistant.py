"""Home Assistant tools for Skippy.

Currently implements:
  - send_notification: Push notifications to a mobile device via HA Companion app

Uses the Home Assistant REST API via httpx:
  POST {HA_URL}/api/services/notify/{service}

Auth: Bearer token via settings.ha_token
"""

import logging

import httpx
from langchain_core.tools import tool

from skippy.config import settings

logger = logging.getLogger("skippy")


@tool
def send_notification(message: str, title: str = "Skippy") -> str:
    """Send a push notification to the user's phone. Use this when you need to
    alert the user about something important, deliver a reminder, or when they
    explicitly ask you to send them a notification.

    Args:
        message: The notification body text.
        title: The notification title (defaults to "Skippy").
    """
    try:
        url = f"{settings.ha_url}/api/services/notify/{settings.ha_notify_service}"
        headers = {
            "Authorization": f"Bearer {settings.ha_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "message": message,
            "title": title,
        }

        response = httpx.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()

        logger.info("Notification sent: title='%s', message='%s'", title, message)
        return f"Notification sent successfully: '{title} - {message}'"
    except httpx.HTTPStatusError as e:
        logger.error("HA notification failed (HTTP %s): %s", e.response.status_code, e)
        return f"Failed to send notification (HTTP {e.response.status_code}): {e}"
    except Exception as e:
        logger.error("HA notification failed: %s", e)
        return f"Failed to send notification: {e}"


def get_tools() -> list:
    """Return HA tools if configured."""
    if settings.ha_token and settings.ha_notify_service:
        return [send_notification]
    return []
