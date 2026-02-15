"""Constants for Skippy V2 integration."""

DOMAIN = "skippy_v2"

# Config keys
CONF_WEBHOOK_URL = "webhook_url"
CONF_TIMEOUT = "timeout"

# Defaults
DEFAULT_TIMEOUT = 30
DEFAULT_WEBHOOK_URL = "http://localhost:8000/webhook/skippy"

# Webhook request/response keys
REQUEST_TEXT = "text"
REQUEST_CONVERSATION_ID = "conversation_id"
REQUEST_LANGUAGE = "language"

RESPONSE_TEXT = "response"
RESPONSE_CONTINUE = "continue_conversation"
