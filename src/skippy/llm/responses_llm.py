"""Custom LangChain LLM wrapper for OpenAI Responses API."""

import asyncio
from typing import Any, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, SystemMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from openai import AsyncOpenAI
from pydantic import Field


class ResponsesAPILLM(BaseChatModel):
    """LangChain wrapper for OpenAI Responses API.

    This custom LLM uses the newer /v1/responses endpoint instead of
    /v1/chat/completions for better performance and cache utilization.
    """

    client: AsyncOpenAI = Field(default_factory=AsyncOpenAI)
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_output_tokens: Optional[int] = None
    tools: Optional[List[BaseTool]] = None

    class Config:
        """Pydantic configuration."""
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        return "openai-responses"

    def bind_tools(
        self,
        tools: List[BaseTool],
        **kwargs: Any,
    ) -> "ResponsesAPILLM":
        """Bind tools to the LLM."""
        return self.model_copy(update={"tools": tools})

    def _convert_messages(
        self, messages: List[BaseMessage]
    ) -> tuple[str, str | list]:
        """Convert LangChain messages to Responses API format.

        Returns:
            (instructions, input) where instructions is the system message
            and input is either a string (single user message) or message array
        """
        instructions = ""
        input_messages = []

        for msg in messages:
            if isinstance(msg, SystemMessage):
                instructions = msg.content
            elif isinstance(msg, HumanMessage):
                input_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                input_messages.append({"role": "assistant", "content": msg.content})

        # If only one user message, use string input for simplicity
        if (
            len(input_messages) == 1
            and input_messages[0]["role"] == "user"
        ):
            return instructions, input_messages[0]["content"]

        # Multiple messages or conversation history - use array
        return instructions, input_messages

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate response using Responses API."""
        instructions, input_data = self._convert_messages(messages)

        # Build API call kwargs
        api_kwargs = {
            "model": self.model,
            "instructions": instructions if instructions else None,
            "input": input_data,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }

        # Note: Tools are not passed to Responses API in this implementation
        # Tool handling is managed by LangGraph's tool execution layer
        # (similar to how ChatOpenAI works with bind_tools)

        # Merge any additional kwargs
        api_kwargs.update(kwargs)

        response = await self.client.responses.create(**api_kwargs)

        message = AIMessage(content=response.output_text)
        generation = ChatGeneration(message=message)

        return ChatResult(generations=[generation])

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Sync version - wraps async call."""
        try:
            # Try to get the running event loop
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop - we're in a sync context
            return asyncio.run(
                self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            )
        else:
            # We're already in an async context - this shouldn't happen
            # but handle it gracefully by raising a more informative error
            raise RuntimeError(
                "Cannot use sync _generate() from within an async context. "
                "Use await llm.ainvoke() instead."
            )
