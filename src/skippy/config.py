from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # Database
    database_url: str = "postgresql://skippy:skippy@postgres:5432/skippy"

    # Home Assistant (future tool use)
    ha_url: str = "http://homeassistant.local:8123"
    ha_token: str = ""

    # Response limits
    voice_max_tokens: int = 300
    chat_max_tokens: int = 4096

    # Memory settings
    memory_similarity_threshold: float = 0.15
    memory_retrieval_limit: int = 5
    memory_dedup_threshold: float = 0.8

    model_config = {"env_file": ".env"}


settings = Settings()
