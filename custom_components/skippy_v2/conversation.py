"""Conversation agent for Skippy V2."""
from __future__ import annotations

import logging
from typing import Literal

import aiohttp
from homeassistant.components import conversation
from homeassistant.components.conversation import ConversationInput, ConversationResult
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.util import ulid

from .const import (
    CONF_TIMEOUT,
    CONF_WEBHOOK_URL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    REQUEST_CONVERSATION_ID,
    REQUEST_LANGUAGE,
    REQUEST_TEXT,
    RESPONSE_CONTINUE,
    RESPONSE_TEXT,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Skippy V2 conversation agent from config entry."""
    agent = SkippyV2ConversationAgent(hass, entry)
    conversation.async_set_agent(hass, entry, agent)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Skippy V2 conversation agent."""
    conversation.async_unset_agent(hass, entry)
    return True


class SkippyV2ConversationAgent(conversation.AbstractConversationAgent):
    """Skippy V2 conversation agent."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the agent."""
        self.hass = hass
        self.entry = entry
        self._webhook_url = entry.data[CONF_WEBHOOK_URL]
        self._timeout = entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return supported languages."""
        return "*"

    async def async_process(
        self, user_input: ConversationInput
    ) -> ConversationResult:
        """Process a sentence and return a response."""
        conversation_id = user_input.conversation_id or ulid.ulid_now()

        payload = {
            REQUEST_TEXT: user_input.text,
            REQUEST_CONVERSATION_ID: conversation_id,
            REQUEST_LANGUAGE: user_input.language,
        }

        _LOGGER.debug("Sending to Skippy V2: %s", payload)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self._timeout),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error(
                            "Skippy V2 returned status %s: %s",
                            response.status,
                            error_text,
                        )
                        return self._error_response(
                            f"Skippy returned error {response.status}",
                            conversation_id,
                        )

                    data = await response.json()
                    _LOGGER.debug("Skippy V2 response: %s", data)

        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to connect to Skippy V2: %s", err)
            return self._error_response(
                "Cannot connect to Skippy. Check webhook URL.",
                conversation_id,
            )
        except TimeoutError:
            _LOGGER.error("Skippy V2 timed out after %s seconds", self._timeout)
            return self._error_response(
                "Skippy took too long to respond.",
                conversation_id,
            )

        # Extract response
        response_text = data.get(RESPONSE_TEXT, "")
        if not response_text:
            _LOGGER.warning("Empty response from Skippy V2: %s", data)
            response_text = "No response from Skippy."

        # Extract continue_conversation flag
        continue_conversation = data.get(RESPONSE_CONTINUE, False)

        _LOGGER.debug(
            "Response: %s... | Continue: %s",
            response_text[:50],
            continue_conversation,
        )

        # Build response
        intent_response = intent.IntentResponse(language=user_input.language)
        intent_response.async_set_speech(response_text)

        return ConversationResult(
            response=intent_response,
            conversation_id=conversation_id,
            continue_conversation=continue_conversation,
        )

    def _error_response(
        self, error_message: str, conversation_id: str
    ) -> ConversationResult:
        """Build an error response."""
        intent_response = intent.IntentResponse(language="en")
        intent_response.async_set_error(
            intent.IntentResponseErrorCode.UNKNOWN,
            error_message,
        )
        return ConversationResult(
            response=intent_response,
            conversation_id=conversation_id,
        )
