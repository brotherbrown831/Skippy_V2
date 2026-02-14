"""Custom LangChain LLM wrapper for OpenAI Responses API."""

from typing import Any, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, SystemMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.callbacks import CallbackManagerForLLMRun
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
    max_completion_tokens: Optional[int] = None

    class Config:
        """Pydantic configuration."""
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        return "openai-responses"

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

        response = await self.client.responses.create(
            model=self.model,
            instructions=instructions if instructions else None,
            input=input_data,
            temperature=self.temperature,
            max_completion_tokens=self.max_completion_tokens,
            **kwargs
        )

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
        """Sync version - not implemented as we use async."""
        raise NotImplementedError("Use ainvoke for async operation")
