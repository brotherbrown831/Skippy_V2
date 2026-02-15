"""Config flow for Skippy V2."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_TIMEOUT,
    CONF_WEBHOOK_URL,
    DEFAULT_TIMEOUT,
    DEFAULT_WEBHOOK_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class SkippyV2ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Skippy V2."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Test the webhook
            webhook_url = user_input[CONF_WEBHOOK_URL]
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        webhook_url,
                        json={"text": "test", "conversation_id": "config-test"},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        if response.status != 200:
                            errors["base"] = "cannot_connect"
                        else:
                            # Success - create entry
                            return self.async_create_entry(
                                title="Skippy V2",
                                data=user_input,
                            )
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_WEBHOOK_URL,
                        default=DEFAULT_WEBHOOK_URL,
                    ): str,
                    vol.Optional(
                        CONF_TIMEOUT,
                        default=DEFAULT_TIMEOUT,
                    ): int,
                }
            ),
            errors=errors,
        )
