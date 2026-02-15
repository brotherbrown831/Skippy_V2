"""Tests for Postgres database connectivity and schema."""

import pytest

pytestmark = pytest.mark.asyncio


async def test_can_connect(db_conn):
    """Should connect to Postgres successfully."""
    cur = await db_conn.execute("SELECT 1")
    row = await cur.fetchone()
    assert row[0] == 1


async def test_pgvector_extension(db_conn):
    """pgvector extension should be enabled."""
    cur = await db_conn.execute(
        "SELECT extname FROM pg_extension WHERE extname = 'vector'"
    )
    row = await cur.fetchone()
    assert row is not None, "pgvector extension not installed"


async def test_tables_exist(db_conn):
    """All 4 application tables should exist."""
    cur = await db_conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )
    rows = await cur.fetchall()
    tables = {row[0] for row in rows}

    expected = {"semantic_memories", "people", "scheduled_tasks", "reminder_acknowledgments"}
    missing = expected - tables
    assert not missing, f"Missing tables: {missing}"


async def test_semantic_memories_roundtrip(db_conn):
    """Insert, query, and delete a test memory row."""
    async with db_conn.cursor() as cur:
        # Insert
        await cur.execute(
            "INSERT INTO semantic_memories (user_id, content, confidence_score, status, category) "
            "VALUES ('_test_', 'pytest test memory', 0.9, 'active', 'test') "
            "RETURNING memory_id"
        )
        row = await cur.fetchone()
        memory_id = row[0]

        # Query
        await cur.execute(
            "SELECT content, category FROM semantic_memories WHERE memory_id = %s",
            (memory_id,),
        )
        row = await cur.fetchone()
        assert row[0] == "pytest test memory"
        assert row[1] == "test"

        # Clean up
        await cur.execute(
            "DELETE FROM semantic_memories WHERE memory_id = %s", (memory_id,)
        )
