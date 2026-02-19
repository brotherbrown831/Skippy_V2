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
from skippy.utils.quiet_hours import is_quiet_time, queue_notification

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


async def _deliver_ha_push(message: str, title: str = "Skippy") -> str:
    """Send an HA push notification immediately (no quiet-hours check)."""
    try:
        url = f"{settings.ha_url}/api/services/notify/{settings.ha_notify_service}"
        headers = _get_ha_headers()
        payload = {"message": message, "title": title}

        response = httpx.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()

        logger.info("Notification sent: title='%s', message='%s'", title, message)
        await log_activity(
            activity_type="notification_sent",
            entity_type="system",
            entity_id="notification",
            description=f"Sent notification: {title}",
            metadata={"title": title, "message": message},
            user_id="nolan",
        )
        return f"Notification sent successfully: '{title} - {message}'"
    except httpx.HTTPStatusError as e:
        logger.error("HA notification failed (HTTP %s): %s", e.response.status_code, e)
        return f"Failed to send notification (HTTP {e.response.status_code}): {e}"
    except Exception as e:
        logger.error("HA notification failed: %s", e)
        return f"Failed to send notification: {e}"


async def _deliver_sms(message: str) -> str:
    """Send an SMS immediately (no quiet-hours check)."""
    try:
        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        sms = client.messages.create(
            body=message,
            from_=settings.twilio_from_number,
            to=settings.twilio_to_number,
        )

        logger.info("SMS sent: sid=%s to=%s", sms.sid, settings.twilio_to_number)
        await log_activity(
            activity_type="sms_sent",
            entity_type="system",
            entity_id="sms",
            description="Sent SMS message",
            metadata={"to": settings.twilio_to_number, "message": message},
            user_id="nolan",
        )
        return f"SMS sent successfully to {settings.twilio_to_number}: '{message}'"
    except Exception as e:
        logger.error("SMS failed: %s", e)
        return f"Failed to send SMS: {e}"


# ============================================================================
# Communication Tools
# ============================================================================


@tool
async def send_notification(
    message: str,
    title: str = "Skippy",
    is_critical: bool = False,
) -> str:
    """Send a push notification to the user's phone. Use this when you need to
    alert the user about something important, deliver a reminder, or when they
    explicitly ask you to send them a notification.

    Args:
        message: The notification body text.
        title: The notification title (defaults to "Skippy").
        is_critical: If True, send immediately even during quiet hours (07:00–21:30
            weekdays, 09:00–21:30 weekends). Defaults to False — non-critical
            notifications are queued and delivered at the start of the next active window.
    """
    if not is_critical and is_quiet_time():
        return await queue_notification("ha_push", {"message": message, "title": title})
    return await _deliver_ha_push(message, title)


@tool
async def send_sms(message: str, is_critical: bool = False) -> str:
    """Send an SMS text message to the user's phone via Twilio. Use this for
    important or urgent messages, or when push notifications aren't reliable.
    Prefer send_notification for routine alerts and send_sms for higher-priority items.

    Args:
        message: The text message to send.
        is_critical: If True, send immediately even during quiet hours. Defaults to
            False — non-critical SMS messages are queued and delivered at the start
            of the next active window (07:00 weekdays / 09:00 weekends).
    """
    if not is_critical and is_quiet_time():
        return await queue_notification("sms", {"message": message})
    return await _deliver_sms(message)


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
