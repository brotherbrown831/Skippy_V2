"""Shared fixtures for Skippy V2 tests.

Tests hit real services (HA, Google, OpenAI, Postgres) using the live .env config.
"""

import asyncio
import pytest
import psycopg

from skippy.config import settings


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for all async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_conn():
    """Real async Postgres connection for the test session."""
    conn = await psycopg.AsyncConnection.connect(settings.database_url, autocommit=True)
    yield conn
    await conn.close()


# --- Skip markers for optional services ---

requires_ha = pytest.mark.skipif(
    not settings.ha_token,
    reason="HA_TOKEN not configured",
)

requires_google_calendar = pytest.mark.skipif(
    not (settings.google_service_account_json and settings.google_calendar_id),
    reason="Google Calendar credentials not configured",
)

requires_google_oauth = pytest.mark.skipif(
    not settings.google_oauth_token_json,
    reason="Google OAuth token not configured",
)

requires_telegram = pytest.mark.skipif(
    not settings.telegram_bot_token,
    reason="TELEGRAM_BOT_TOKEN not configured",
)

requires_openai = pytest.mark.skipif(
    not settings.openai_api_key,
    reason="OPENAI_API_KEY not configured",
)
