"""Tests for the LangGraph agent graph."""

import pytest
from tests.conftest import requires_openai

from skippy.agent.graph import build_graph
from skippy.main import ChatMessage, _generate_conversation_id

# --- Pure function tests ---


class TestGenerateConversationId:
    def test_deterministic(self):
        msgs = [ChatMessage(role="user", content="hello")]
        id1 = _generate_conversation_id(msgs)
        id2 = _generate_conversation_id(msgs)
        assert id1 == id2

    def test_prefix(self):
        msgs = [ChatMessage(role="user", content="test")]
        result = _generate_conversation_id(msgs)
        assert result.startswith("owui-")

    def test_different_input_different_id(self):
        msgs1 = [ChatMessage(role="user", content="hello")]
        msgs2 = [ChatMessage(role="user", content="goodbye")]
        assert _generate_conversation_id(msgs1) != _generate_conversation_id(msgs2)


# --- Integration tests ---


@requires_openai
@pytest.mark.asyncio
async def test_build_graph():
    """Agent graph should compile with a real checkpointer."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from skippy.config import settings

    async with AsyncPostgresSaver.from_conn_string(settings.database_url) as checkpointer:
        await checkpointer.setup()
        graph = await build_graph(checkpointer)
        assert graph is not None
