import re
from pydantic import model_validator
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
    calendar_check_interval_minutes: int = 30  # 30 minutes
    morning_briefing_time: str = "07:00"
    evening_summary_time: str = "22:00"
    google_contacts_sync_time: str = "02:00"
    people_importance_recalc_time: str = "03:00"

    # Telegram
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: str = ""
    telegram_notify_chat_ids: str = ""
    telegram_poll_interval: int = 2
    telegram_long_poll_timeout: int = 20
    telegram_api_base: str = "https://api.telegram.org"

    # Tavily Web Search
    tavily_api_key: str = ""
    tavily_api_base: str = "https://api.tavily.com"

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
    memory_context_window: int = 6

    @model_validator(mode="before")
    @classmethod
    def validate_schedule_times(cls, values):
        """Validate schedule time format: HH:MM or 'disabled'."""
        time_fields = [
            "morning_briefing_time",
            "evening_summary_time",
            "google_contacts_sync_time",
            "people_importance_recalc_time",
        ]

        time_pattern = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

        for field in time_fields:
            value = values.get(field, "")

            if not value:  # Use default
                continue

            if isinstance(value, str) and value.lower() == "disabled":
                values[field] = "disabled"
                continue

            # Validate HH:MM format
            if isinstance(value, str):
                match = time_pattern.match(value)
                if not match:
                    raise ValueError(
                        f"{field}: must be 'HH:MM' (24-hour), 'disabled', "
                        f"or empty. Got: '{value}'"
                    )

        return values

    model_config = {"env_file": ".env"}


settings = Settings()
