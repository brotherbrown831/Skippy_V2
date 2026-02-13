from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """State that flows through the LangGraph agent."""

    # Conversation messages — LangGraph manages accumulation via add_messages
    messages: Annotated[list[BaseMessage], add_messages]

    # Semantic memories retrieved for the current query
    memories: list[dict]

    # Input source: "voice" or "chat"
    source: str

    # Conversation identifier for persistence
    conversation_id: str
