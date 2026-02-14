"""Telegram notification tool for proactive messaging."""

import logging

import httpx
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


def get_tools() -> list:
    """Return Telegram tools if token is configured."""
    if settings.telegram_bot_token:
        return [send_telegram_message]
    return []
