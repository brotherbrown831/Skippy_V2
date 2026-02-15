"""Tests for semantic memory retrieval and evaluation."""

import pytest
from tests.conftest import requires_openai

from skippy.memory.retriever import retrieve_memories

pytestmark = [pytest.mark.asyncio, requires_openai]


async def test_retrieve_memories_returns_list():
    """retrieve_memories should return a list (possibly empty)."""
    results = await retrieve_memories("test query about nothing specific")
    assert isinstance(results, list)


async def test_retrieve_memories_dict_keys():
    """If results are returned, each should have the expected keys."""
    results = await retrieve_memories("family members and relationships")
    if results:
        for mem in results:
            assert "memory_id" in mem
            assert "content" in mem
            assert "category" in mem
            assert "confidence" in mem
            assert "similarity" in mem
            assert isinstance(mem["similarity"], float)
