"""Tool auto-discovery for Skippy.

Convention: each module in this package exports a get_tools() -> list function.
Tools are only loaded if their prerequisites are met (checked inside get_tools).
"""

import logging

from skippy.tools.home_assistant import get_tools as _ha_tools
from skippy.tools.google_calendar import get_tools as _calendar_tools
from skippy.tools.scheduler import get_tools as _scheduler_tools
from skippy.tools.people import get_tools as _people_tools
from skippy.tools.gmail import get_tools as _gmail_tools
from skippy.tools.google_contacts import get_tools as _contacts_tools
from skippy.tools.contact_sync import get_tools as _contact_sync_tools
from skippy.tools.telegram import get_tools as _telegram_tools
from skippy.tools.testing import get_tools as _testing_tools
from skippy.tools.ha_entity_sync import get_tools as _ha_sync_tools

logger = logging.getLogger("skippy")


def collect_tools() -> list:
    """Gather all tools from all tool modules."""
    sources = [
        ("home_assistant", _ha_tools),
        ("google_calendar", _calendar_tools),
        ("scheduler", _scheduler_tools),
        ("people", _people_tools),
        ("gmail", _gmail_tools),
        ("google_contacts", _contacts_tools),
        ("contact_sync", _contact_sync_tools),
        ("telegram", _telegram_tools),
        ("testing", _testing_tools),
        ("ha_entity_sync", _ha_sync_tools),
    ]

    all_tools = []
    for name, get_tools_fn in sources:
        try:
            module_tools = get_tools_fn()
            all_tools.extend(module_tools)
            logger.info("Tool module '%s': %d tools loaded", name, len(module_tools))
        except Exception:
            logger.exception("Tool module '%s' failed to load, skipping", name)

    logger.info("Total tools collected: %d", len(all_tools))
    return all_tools
