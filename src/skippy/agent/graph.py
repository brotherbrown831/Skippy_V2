import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from langchain_openai import ChatOpenAI

from skippy.agent.prompts import (
    CHAT_SYSTEM_PROMPT,
    MEMORY_CONTEXT_TEMPLATE,
    VOICE_SYSTEM_PROMPT,
)
from skippy.agent.state import AgentState
from skippy.config import settings
from skippy.memory.evaluator import evaluate_and_store
from skippy.memory.retriever import retrieve_memories
from skippy.tools import collect_tools

logger = logging.getLogger("skippy")

tools: list = collect_tools()


async def retrieve_memories_node(state: AgentState, config: RunnableConfig) -> dict:
    """Retrieve relevant semantic memories based on the user's message."""
    # Get the last user message
    last_message = state["messages"][-1]
    query = last_message.content

    user_id = config.get("configurable", {}).get("user_id", "nolan")

    memories = await retrieve_memories(
        query=query,
        user_id=user_id,
        limit=settings.memory_retrieval_limit,
        threshold=settings.memory_similarity_threshold,
    )

    logger.info("Retrieved %d memories for query: '%s'", len(memories), query[:50])

    return {"memories": memories}


async def agent_node(state: AgentState, config: RunnableConfig) -> dict:
    """Call the LLM with personality prompt, memories, and conversation history."""
    source = config.get("configurable", {}).get("source", "voice")

    # Pick prompt and token limit based on source
    if source == "voice":
        system_prompt = VOICE_SYSTEM_PROMPT
        max_tokens = settings.voice_max_tokens
    else:
        system_prompt = CHAT_SYSTEM_PROMPT
        max_tokens = settings.chat_max_tokens

    # Inject current date/time so the LLM knows when "today" and "tonight" are
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz).strftime("%A, %B %d, %Y at %I:%M %p %Z")
    system_prompt += f"\n\nCurrent date and time: {now}"

    # Inject memories into system prompt if we have any
    memories = state.get("memories", [])
    if memories:
        memory_text = "\n".join(f"- {m['content']}" for m in memories)
        system_prompt += MEMORY_CONTEXT_TEMPLATE.format(memories=memory_text)

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        max_tokens=max_tokens,
        temperature=0.7,
    )

    # Bind tools if we have any
    if tools:
        llm = llm.bind_tools(tools)

    # Build message list: system prompt + conversation history
    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    response = await llm.ainvoke(messages)
    return {"messages": [response]}


async def evaluate_memory_node(state: AgentState, config: RunnableConfig) -> dict:
    """Evaluate the conversation for facts worth storing. Runs as fire-and-forget."""
    messages = state["messages"]
    if len(messages) < 2:
        return {}

    # Get the last user message and assistant response
    assistant_message = messages[-1].content
    user_message = None
    for msg in reversed(messages[:-1]):
        if not isinstance(msg, AIMessage):
            user_message = msg.content
            break

    if not user_message:
        return {}

    conversation_id = config.get("configurable", {}).get("thread_id", "unknown")

    # Build conversation history for context (sliding window)
    history = []
    context_messages = messages[:-2]  # Exclude the current exchange
    # Only include last N messages to prevent re-evaluating old facts
    recent_context = (
        context_messages[-settings.memory_context_window:]
        if len(context_messages) > settings.memory_context_window
        else context_messages
    )
    for msg in recent_context:
        role = "assistant" if isinstance(msg, AIMessage) else "user"
        history.append({"role": role, "content": msg.content})

    # Fire and forget — don't block the response
    asyncio.create_task(
        evaluate_and_store(
            conversation_history=history,
            user_message=user_message,
            assistant_message=assistant_message,
            conversation_id=conversation_id,
        )
    )

    return {}


def should_use_tools(state: AgentState) -> str:
    """Route to tools node if the LLM requested tool calls, otherwise to memory evaluation."""
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "evaluate_memory"


async def build_graph(checkpointer):
    """Build and compile the LangGraph agent graph."""

    # Build the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("retrieve_memories", retrieve_memories_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("evaluate_memory", evaluate_memory_node)

    # Add tools node if we have tools
    if tools:
        workflow.add_node("tools", ToolNode(tools))

    # Define edges
    workflow.set_entry_point("retrieve_memories")
    workflow.add_edge("retrieve_memories", "agent")

    if tools:
        workflow.add_conditional_edges(
            "agent",
            should_use_tools,
            {"tools": "tools", "evaluate_memory": "evaluate_memory"},
        )
        workflow.add_edge("tools", "agent")
    else:
        workflow.add_edge("agent", "evaluate_memory")

    workflow.add_edge("evaluate_memory", END)

    return workflow.compile(checkpointer=checkpointer)
