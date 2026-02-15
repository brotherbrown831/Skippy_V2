"""Tests for structured people database tools."""

import pytest

from skippy.tools.people import (
    add_person,
    get_person,
    search_people,
    update_person,
    list_people,
)

pytestmark = pytest.mark.asyncio

TEST_NAME = "_Pytest_TestPerson_"


async def test_people_crud_cycle():
    """Full CRUD cycle: add → get → search → update → verify → clean up."""
    # Add
    result = await add_person.ainvoke({
        "name": TEST_NAME,
        "relationship": "test-subject",
        "birthday": "2000-01-01",
        "email": "test@pytest.local",
    })
    assert "added" in result.lower() or "upsert" in result.lower() or TEST_NAME.lower() in result.lower()

    # Get
    result = await get_person.ainvoke({"name": TEST_NAME})
    assert TEST_NAME.lower() in result.lower()
    assert "test-subject" in result.lower()

    # Search
    result = await search_people.ainvoke({"query": "pytest"})
    assert TEST_NAME.lower() in result.lower()

    # Update
    result = await update_person.ainvoke({
        "name": TEST_NAME,
        "phone": "555-0000",
    })
    assert "updated" in result.lower()

    # Verify update
    result = await get_person.ainvoke({"name": TEST_NAME})
    assert "555-0000" in result

    # Clean up — direct DB delete since there's no delete tool
    import psycopg
    from skippy.config import settings
    async with await psycopg.AsyncConnection.connect(
        settings.database_url, autocommit=True
    ) as conn:
        await conn.execute(
            "DELETE FROM people WHERE user_id = 'nolan' AND LOWER(name) = LOWER(%s)",
            (TEST_NAME,),
        )


async def test_list_people():
    """list_people should return a string."""
    result = await list_people.ainvoke({})
    assert isinstance(result, str)
