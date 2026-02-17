import asyncio
import json
import logging
from datetime import datetime, timedelta

import httpx
from skippy.db_utils import get_db_connection
from langchain_core.messages import HumanMessage

from skippy.config import settings

logger = logging.getLogger("skippy")


def _parse_allowed_chat_ids() -> set[int] | None:
    raw = settings.telegram_allowed_chat_ids.strip()
    if not raw:
        return None
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            logger.warning("Invalid Telegram chat id in allowlist: %s", part)
    return ids or None


async def _send_message(client: httpx.AsyncClient, chat_id: int, text: str) -> None:
    url = f"{settings.telegram_api_base.rstrip('/')}/bot{settings.telegram_bot_token}/sendMessage"
    await client.post(url, json={"chat_id": chat_id, "text": text})


async def _handle_update(app, client: httpx.AsyncClient, update: dict, allowed: set[int] | None):
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return

    text = (msg.get("text") or "").strip()
    if not text:
        return

    chat_id = msg.get("chat", {}).get("id")
    if chat_id is None:
        return

    logger.info("Telegram message received from chat_id=%s, text=%s", chat_id, text[:50])

    if allowed is not None and chat_id not in allowed:
        logger.warning("Ignoring Telegram message from unauthorized chat_id=%s", chat_id)
        return

    try:
        result = await app.state.graph.ainvoke(
            {"messages": [HumanMessage(content=text)]},
            config={
                "configurable": {
                    "thread_id": f"telegram-{chat_id}",
                    "source": "telegram",
                    "user_id": "nolan",
                }
            },
        )
        response_text = result["messages"][-1].content
    except Exception:
        logger.exception("Telegram message handling failed")
        response_text = "Sorry, I hit an error processing that."

    try:
        await _send_message(client, chat_id, response_text)
    except Exception:
        logger.exception("Failed to send Telegram response")


async def _handle_callback_query(app, client: httpx.AsyncClient, callback: dict):
    """Handle inline button presses from Telegram."""
    callback_id = callback.get("id")
    data = callback.get("data", "")
    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id")

    if not data or not chat_id:
        return

    # Parse callback data: format is "action:reminder_id" (e.g., "ack:42", "snooze:42", "dismiss:42")
    try:
        action, reminder_id = data.split(":", 1)
        reminder_id = int(reminder_id)
    except (ValueError, IndexError):
        logger.warning("Invalid callback data: %s", data)
        return

    # Update database based on action
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                if action == "ack":
                    await cur.execute(
                        "UPDATE reminder_acknowledgments SET status = 'acknowledged', "
                        "acknowledged_at = NOW(), updated_at = NOW() WHERE reminder_id = %s",
                        (reminder_id,)
                    )
                    answer_text = "✓ Got it!"
                elif action == "snooze":
                    snooze_until = datetime.now() + timedelta(minutes=10)
                    await cur.execute(
                        "UPDATE reminder_acknowledgments SET status = 'snoozed', "
                        "snoozed_until = %s, updated_at = NOW() WHERE reminder_id = %s",
                        (snooze_until, reminder_id)
                    )
                    answer_text = "Snoozed for 10 minutes"
                elif action == "dismiss":
                    await cur.execute(
                        "UPDATE reminder_acknowledgments SET status = 'dismissed', "
                        "acknowledged_at = NOW(), updated_at = NOW() WHERE reminder_id = %s",
                        (reminder_id,)
                    )
                    answer_text = "Dismissed"
                else:
                    answer_text = "Unknown action"
    except Exception:
        logger.exception("Failed to handle callback query")
        answer_text = "Error processing action"

    # Send acknowledgment back to Telegram (shows brief popup)
    answer_url = f"{settings.telegram_api_base.rstrip('/')}/bot{settings.telegram_bot_token}/answerCallbackQuery"
    try:
        await client.post(answer_url, json={"callback_query_id": callback_id, "text": answer_text})
    except Exception:
        logger.exception("Failed to answer callback query")


async def telegram_polling_loop(app) -> None:
    if not settings.telegram_bot_token:
        logger.info("Telegram disabled (no bot token configured)")
        return

    allowed = _parse_allowed_chat_ids()
    base_url = f"{settings.telegram_api_base.rstrip('/')}/bot{settings.telegram_bot_token}"
    get_updates_url = f"{base_url}/getUpdates"

    offset = 0
    poll_interval = max(1, settings.telegram_poll_interval)
    long_poll_timeout = max(5, settings.telegram_long_poll_timeout)

    timeout = httpx.Timeout(connect=10, read=long_poll_timeout + 10, write=10, pool=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        logger.info("Telegram polling started")
        while True:
            try:
                resp = await client.get(
                    get_updates_url,
                    params={"timeout": long_poll_timeout, "offset": offset},
                )
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    logger.error("Telegram getUpdates error: %s", data)
                    await asyncio.sleep(poll_interval)
                    continue

                for update in data.get("result", []):
                    update_id = update.get("update_id")
                    if update_id is not None:
                        offset = max(offset, update_id + 1)
                    # Handle regular messages
                    await _handle_update(app, client, update, allowed)
                    # Handle callback queries (button presses)
                    if "callback_query" in update:
                        await _handle_callback_query(app, client, update["callback_query"])
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Telegram polling error")
                await asyncio.sleep(poll_interval)


async def start_telegram(app) -> None:
    if not settings.telegram_bot_token:
        logger.info("Telegram disabled (no bot token configured)")
        return

    task = asyncio.create_task(telegram_polling_loop(app))
    app.state.telegram_task = task


async def stop_telegram(app) -> None:
    task = getattr(app.state, "telegram_task", None)
    if not task:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
