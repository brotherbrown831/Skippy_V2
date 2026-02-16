"""Home Assistant communication tools for Skippy.

Implements:
  - send_notification: Push notifications via HA Companion app
  - send_sms: SMS text messages via Twilio

Note: Device control functionality has been moved to Jarvis AI.
This module now focuses exclusively on communication/notification delivery.
"""

import logging

import httpx
from langchain_core.tools import tool

from skippy.config import settings
from skippy.utils.activity_logger import log_activity

logger = logging.getLogger("skippy")


# ============================================================================
# Helper Functions (Internal, not exposed as tools)
# ============================================================================


def _get_ha_headers() -> dict:
    """Build HA API headers with auth token."""
    return {
        "Authorization": f"Bearer {settings.ha_token}",
        "Content-Type": "application/json"
    }


# ============================================================================
# Communication Tools
# ============================================================================


@tool
async def send_notification(message: str, title: str = "Skippy") -> str:
    """Send a push notification to the user's phone. Use this when you need to
    alert the user about something important, deliver a reminder, or when they
    explicitly ask you to send them a notification.

    Args:
        message: The notification body text.
        title: The notification title (defaults to "Skippy").
    """
    try:
        url = f"{settings.ha_url}/api/services/notify/{settings.ha_notify_service}"
        headers = _get_ha_headers()
        payload = {
            "message": message,
            "title": title,
        }

        response = httpx.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()

        logger.info("Notification sent: title='%s', message='%s'", title, message)
        msg = f"Notification sent successfully: '{title} - {message}'"
        await log_activity(
            activity_type="notification_sent",
            entity_type="system",
            entity_id="notification",
            description=f"Sent notification: {title}",
            metadata={"title": title, "message": message},
            user_id="nolan",
        )
        return msg
    except httpx.HTTPStatusError as e:
        logger.error("HA notification failed (HTTP %s): %s", e.response.status_code, e)
        return f"Failed to send notification (HTTP {e.response.status_code}): {e}"
    except Exception as e:
        logger.error("HA notification failed: %s", e)
        return f"Failed to send notification: {e}"


@tool
async def send_sms(message: str) -> str:
    """Send an SMS text message to the user's phone via Twilio. Use this for
    important or urgent messages, or when push notifications aren't reliable.
    Prefer send_notification for routine alerts and send_sms for higher-priority items.

    Args:
        message: The text message to send.
    """
    try:
        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        sms = client.messages.create(
            body=message,
            from_=settings.twilio_from_number,
            to=settings.twilio_to_number,
        )

        logger.info("SMS sent: sid=%s to=%s", sms.sid, settings.twilio_to_number)
        msg = f"SMS sent successfully to {settings.twilio_to_number}: '{message}'"
        await log_activity(
            activity_type="sms_sent",
            entity_type="system",
            entity_id="sms",
            description=f"Sent SMS message",
            metadata={"to": settings.twilio_to_number, "message": message},
            user_id="nolan",
        )
        return msg
    except Exception as e:
        logger.error("SMS failed: %s", e)
        return f"Failed to send SMS: {e}"


# ============================================================================
# Tool Registration
# ============================================================================


def get_tools() -> list:
    """Return HA communication tools based on configuration."""
    tools = []

    # Notifications if configured
    if settings.ha_token and settings.ha_notify_service:
        tools.append(send_notification)

    # SMS if configured
    if settings.twilio_account_sid and settings.twilio_auth_token:
        tools.append(send_sms)

    return tools
