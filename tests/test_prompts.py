"""Tests for system prompts and templates."""

from skippy.agent.prompts import (
    VOICE_SYSTEM_PROMPT,
    CHAT_SYSTEM_PROMPT,
    MEMORY_CONTEXT_TEMPLATE,
    MEMORY_EVALUATION_PROMPT,
    PERSON_EXTRACTION_PROMPT,
)


def test_voice_prompt_has_personality():
    assert "Skippy" in VOICE_SYSTEM_PROMPT
    assert "sarcastic" in VOICE_SYSTEM_PROMPT.lower()


def test_chat_prompt_has_personality():
    assert "Skippy" in CHAT_SYSTEM_PROMPT
    assert "monkeys" in CHAT_SYSTEM_PROMPT.lower()


def test_voice_prompt_mentions_tools():
    """Voice prompt should instruct the agent to use tools."""
    assert "tool" in VOICE_SYSTEM_PROMPT.lower()
    assert "calendar" in VOICE_SYSTEM_PROMPT.lower()
    assert "Home Assistant" in VOICE_SYSTEM_PROMPT


def test_chat_prompt_mentions_tools():
    assert "tool" in CHAT_SYSTEM_PROMPT.lower()
    assert "Gmail" in CHAT_SYSTEM_PROMPT


def test_memory_context_template_formats():
    result = MEMORY_CONTEXT_TEMPLATE.format(memories="- Nolan likes coffee\n- Nolan has a dog")
    assert "Nolan likes coffee" in result
    assert "KNOWN FACTS" in result


def test_memory_evaluation_prompt_has_json_schema():
    assert "should_store" in MEMORY_EVALUATION_PROMPT
    assert "extracted_fact" in MEMORY_EVALUATION_PROMPT
    assert "category" in MEMORY_EVALUATION_PROMPT


def test_person_extraction_prompt_has_fields():
    assert "name" in PERSON_EXTRACTION_PROMPT
    assert "relationship" in PERSON_EXTRACTION_PROMPT
    assert "birthday" in PERSON_EXTRACTION_PROMPT
    assert "JSON" in PERSON_EXTRACTION_PROMPT
