"""Tests for Skippy configuration loading."""

from skippy.config import Settings, settings


def test_settings_loads():
    """Settings should load successfully from .env."""
    assert settings is not None
    assert isinstance(settings, Settings)


def test_required_fields_present():
    """Critical fields must have real values."""
    assert settings.openai_api_key, "OPENAI_API_KEY is required"
    assert settings.database_url, "DATABASE_URL is required"


def test_default_values():
    """Verify sensible defaults for optional settings."""
    assert settings.timezone == "America/Chicago"
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.voice_max_tokens == 300
    assert settings.chat_max_tokens == 4096
    assert settings.memory_similarity_threshold == 0.15
    assert settings.memory_dedup_threshold == 0.8
    assert settings.scheduler_enabled is True
