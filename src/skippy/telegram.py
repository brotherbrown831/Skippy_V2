import asyncio
import logging

import httpx
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
                    await _handle_update(app, client, update, allowed)
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
