from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # General
    timezone: str = "America/Chicago"

    # OpenAI
    openai_api_key: str
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # Database
    database_url: str = "postgresql://skippy:skippy@postgres:5432/skippy"

    # Home Assistant
    ha_url: str = "http://homeassistant.local:8123"
    ha_token: str = ""
    ha_notify_service: str = ""

    # Twilio SMS
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_to_number: str = ""

    # Scheduler
    scheduler_enabled: bool = True

    # Telegram
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: str = ""
    telegram_notify_chat_ids: str = ""
    telegram_poll_interval: int = 2
    telegram_long_poll_timeout: int = 20
    telegram_api_base: str = "https://api.telegram.org"

    # Google Calendar
    google_calendar_id: str = ""
    google_service_account_json: str = ""

    # Google OAuth2 (Gmail + Contacts)
    google_oauth_client_json: str = ""
    google_oauth_token_json: str = ""

    # Response limits
    voice_max_tokens: int = 300
    chat_max_tokens: int = 4096

    # Memory settings
    memory_similarity_threshold: float = 0.15
    memory_retrieval_limit: int = 5
    memory_dedup_threshold: float = 0.8

    model_config = {"env_file": ".env"}


settings = Settings()
