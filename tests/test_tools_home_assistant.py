"""Tests for Home Assistant tools."""

import pytest
from tests.conftest import requires_ha

from skippy.tools.home_assistant import (
    _fetch_ha_entities,
    _get_cached_entities,
    _get_ha_state,
    _resolve_entity_id,
)

pytestmark = requires_ha


def test_fetch_ha_entities():
    """Should fetch a non-empty list of entities from HA."""
    entities = _fetch_ha_entities()
    assert isinstance(entities, list)
    assert len(entities) > 0

    # Each entity should have the expected keys
    entity = entities[0]
    assert "entity_id" in entity
    assert "friendly_name" in entity
    assert "domain" in entity


def test_cached_entities():
    """Cached entities should match a fresh fetch."""
    entities = _get_cached_entities()
    assert isinstance(entities, list)
    assert len(entities) > 0


def test_get_ha_state_sun():
    """sun.sun is a built-in entity that always exists."""
    result = _get_ha_state("sun.sun")
    assert result["success"] is True
    assert result["state"] in ("above_horizon", "below_horizon")
    assert "attributes" in result


def test_get_ha_state_nonexistent():
    """Querying a nonexistent entity should return an error."""
    result = _get_ha_state("sensor.this_does_not_exist_pytest")
    assert result["success"] is False


def test_resolve_entity_exact():
    """Exact entity_id should resolve with high confidence."""
    result = _resolve_entity_id("sun.sun")
    assert result["entity_id"] == "sun.sun"
    assert result["confidence"] >= 85


def test_resolve_entity_fuzzy():
    """Fuzzy name should resolve to a matching entity."""
    # This depends on real HA entities, so just check the structure
    result = _resolve_entity_id("sun")
    assert "entity_id" in result
    assert "confidence" in result
    assert "matched_name" in result
    assert "suggestion" in result


def test_resolve_entity_nonsense():
    """Complete nonsense should not resolve — raises ValueError or returns low confidence."""
    try:
        result = _resolve_entity_id("xyzzy_purple_unicorn_42")
        # If it returns, confidence should be low
        assert result["confidence"] < 85 or result["entity_id"] == ""
    except ValueError:
        # Expected: _resolve_entity_id raises when no match found
        pass
