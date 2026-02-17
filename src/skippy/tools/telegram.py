"""Telegram notification tool for proactive messaging."""

import asyncio
import concurrent.futures
import logging
from datetime import datetime

import httpx
from skippy.db_utils import get_db_connection
from langchain_core.tools import tool

from skippy.config import settings

logger = logging.getLogger("skippy")


def _parse_chat_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            logger.warning("Invalid Telegram chat id: %s", part)
    return ids


def _get_default_chat_ids() -> list[int]:
    if settings.telegram_notify_chat_ids:
        return _parse_chat_ids(settings.telegram_notify_chat_ids)
    if settings.telegram_allowed_chat_ids:
        return _parse_chat_ids(settings.telegram_allowed_chat_ids)
    return []


@tool
def send_telegram_message(message: str, chat_id: int | None = None) -> str:
    """Send a Telegram message. Use this for proactive notifications and
    scheduled briefings when Telegram is the primary channel.

    Args:
        message: The message to send.
        chat_id: Optional explicit chat ID. If omitted, uses TELEGRAM_NOTIFY_CHAT_IDS
            or falls back to TELEGRAM_ALLOWED_CHAT_IDS.
    """
    if not settings.telegram_bot_token:
        return "Telegram bot token not configured."

    targets = [chat_id] if chat_id is not None else _get_default_chat_ids()
    if not targets:
        return "No Telegram chat IDs configured for notifications."

    url = f"{settings.telegram_api_base.rstrip('/')}/bot{settings.telegram_bot_token}/sendMessage"
    try:
        for target in targets:
            response = httpx.post(url, json={"chat_id": target, "text": message}, timeout=10)
            response.raise_for_status()
        return f"Telegram message sent to {len(targets)} chat(s)."
    except httpx.HTTPStatusError as e:
        logger.error("Telegram send failed (HTTP %s): %s", e.response.status_code, e)
        return f"Failed to send Telegram message (HTTP {e.response.status_code})."
    except Exception as e:
        logger.error("Telegram send failed: %s", e)
        return f"Failed to send Telegram message: {e}"


@tool
def send_telegram_message_with_reminder_buttons(
    message: str,
    event_id: str,
    event_summary: str,
    event_start: str,
    chat_id: int | None = None
) -> str:
    """Send a Telegram reminder message with acknowledgment buttons and record it in the database.

    Use this for calendar event reminders to enable acknowledgment tracking.

    Args:
        message: The reminder message to send
        event_id: Google Calendar event ID
        event_summary: Event title
        event_start: Event start time (ISO format)
        chat_id: Optional explicit chat ID
    """
    if not settings.telegram_bot_token:
        return "Telegram bot token not configured."

    targets = [chat_id] if chat_id is not None else _get_default_chat_ids()
    if not targets:
        return "No Telegram chat IDs configured for notifications."

    # Parse event_start
    try:
        event_dt = datetime.fromisoformat(event_start.replace('Z', '+00:00'))
    except Exception:
        return f"Invalid event_start format: {event_start}"

    url = f"{settings.telegram_api_base.rstrip('/')}/bot{settings.telegram_bot_token}/sendMessage"

    async def send_and_record():
        # Create reminder record
        reminder_id = None
        try:
            async with get_db_connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO reminder_acknowledgments "
                        "(user_id, event_id, event_summary, event_start, status) "
                        "VALUES (%s, %s, %s, %s, 'pending') RETURNING reminder_id",
                        ("nolan", event_id, event_summary, event_dt)
                    )
                    row = await cur.fetchone()
                    if row:
                        reminder_id = row[0]
        except Exception as e:
            logger.error("Failed to create reminder record: %s", e)
            return f"Failed to create reminder record: {e}"

        if not reminder_id:
            return "Failed to get reminder ID"

        # Send message with inline buttons
        buttons = [
            ("Got it ✓", f"ack:{reminder_id}"),
            ("Snooze 10 min", f"snooze:{reminder_id}"),
            ("Dismiss", f"dismiss:{reminder_id}")
        ]

        keyboard = {
            "inline_keyboard": [
                [{"text": label, "callback_data": data} for label, data in buttons]
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                for target in targets:
                    response = await client.post(url, json={
                        "chat_id": target,
                        "text": message,
                        "reply_markup": keyboard
                    })
                    response.raise_for_status()
            return f"Reminder sent to {len(targets)} chat(s) with acknowledgment buttons."
        except Exception as e:
            logger.error("Telegram send failed: %s", e)
            return f"Failed to send Telegram message: {e}"

    # Run async function in a thread pool to avoid blocking
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, send_and_record())
            return future.result(timeout=15)
    except concurrent.futures.TimeoutError:
        return "Reminder send timed out"
    except Exception as e:
        logger.error("Failed to execute reminder send: %s", e)
        return f"Failed to execute reminder send: {e}"


def get_tools() -> list:
    """Return Telegram tools if token is configured."""
    if settings.telegram_bot_token:
        return [send_telegram_message, send_telegram_message_with_reminder_buttons]
    return []
