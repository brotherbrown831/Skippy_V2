"""Tests for Google Contacts tools."""

import pytest
from tests.conftest import requires_google_oauth

from skippy.tools.google_contacts import search_contacts


@requires_google_oauth
def test_search_contacts():
    """Should return a string with contact results or 'no contacts found'."""
    result = search_contacts.invoke({"query": "Nolan"})
    assert isinstance(result, str)
    assert len(result) > 0
