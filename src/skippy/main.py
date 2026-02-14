import logging
import math
import time
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from fastapi import FastAPI
from langchain_core.messages import HumanMessage
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from skippy.agent.graph import build_graph
from skippy.config import settings
from skippy.scheduler import start_scheduler, stop_scheduler
from skippy.web.memories import router as memories_router

logger = logging.getLogger("skippy")


# --- Request/Response Models ---


class VoiceContext(BaseModel):
    language: str = "en"
    timestamp: str = ""
    agent_id: str = "skippy"


class VoiceRequest(BaseModel):
    # Support both V1 (input_text) and direct (text) field names
    text: str = ""
    input_text: str = ""
    conversation_id: str = ""
    session_id: str = ""
    source: str = "voice"
    language: str = "en"
    agent_id: str = "skippy"
    context: VoiceContext | None = None


class VoiceResponse(BaseModel):
    response: str
    response_text: str = ""


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "skippy"
    messages: list[ChatMessage] = []
    temperature: float = 0.7
    stream: bool = False


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: ChatUsage = ChatUsage()


# --- App Lifecycle ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create connection pool and build agent graph
    app.state.pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=2,
        max_size=10,
        open=False,
    )
    await app.state.pool.open()
    async with AsyncPostgresSaver.from_conn_string(settings.database_url) as checkpointer:
        await checkpointer.setup()
        app.state.graph = await build_graph(checkpointer)
        logger.info("Skippy agent ready")
        await start_scheduler(app)
        yield
        await stop_scheduler(app)
    # Shutdown
    await app.state.pool.close()


app = FastAPI(title="Skippy", version="2.0.0", lifespan=lifespan)
app.include_router(memories_router)


# --- Endpoints ---


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "skippy"}


@app.post("/webhook/skippy", response_model=VoiceResponse)
async def voice_endpoint(request: VoiceRequest):
    """Voice endpoint — matches Home Assistant custom component webhook format."""
    # Support both field names: input_text (HA component) and text (direct API)
    user_text = request.input_text or request.text
    if not user_text:
        return VoiceResponse(response="No input received.")

    conversation_id = request.conversation_id or request.session_id or f"voice-{int(time.time())}"

    result = await app.state.graph.ainvoke(
        {"messages": [HumanMessage(content=user_text)]},
        config={
            "configurable": {
                "thread_id": conversation_id,
                "source": "voice",
                "user_id": "nolan",
            }
        },
    )

    response_text = result["messages"][-1].content
    return VoiceResponse(response=response_text, response_text=response_text)


@app.post("/webhook/v1/chat/completions", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """OpenAI-compatible chat completions endpoint for OpenWebUI."""
    # Extract last user message
    user_message = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_message = msg.content
            break

    if not user_message:
        return _empty_chat_response(request.model)

    # Generate a stable conversation ID from the first few messages
    conversation_id = _generate_conversation_id(request.messages)

    result = await app.state.graph.ainvoke(
        {"messages": [HumanMessage(content=user_message)]},
        config={
            "configurable": {
                "thread_id": conversation_id,
                "source": "chat",
                "user_id": "nolan",
            }
        },
    )

    response_text = result["messages"][-1].content

    return ChatResponse(
        id=f"chatcmpl-{int(time.time())}",
        created=int(time.time()),
        model=request.model,
        choices=[
            ChatChoice(
                message=ChatMessage(role="assistant", content=response_text),
            )
        ],
    )


# --- Helpers ---


def _generate_conversation_id(messages: list[ChatMessage]) -> str:
    """Generate a stable conversation ID from message content."""
    content = "|".join(m.content for m in messages[:3])[:50]
    h = 0
    for c in content:
        h = ((h << 5) - h) + ord(c)
        h &= 0xFFFFFFFF
    return f"owui-{h}"


def _empty_chat_response(model: str) -> ChatResponse:
    return ChatResponse(
        id=f"chatcmpl-{int(time.time())}",
        created=int(time.time()),
        model=model,
        choices=[
            ChatChoice(
                message=ChatMessage(role="assistant", content="No message received."),
            )
        ],
    )
