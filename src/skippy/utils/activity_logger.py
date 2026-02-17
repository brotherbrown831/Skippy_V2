"""Activity logging utility for unified event tracking."""
import json
import logging
from skippy.db_utils import get_db_connection

from skippy.config import settings

logger = logging.getLogger("skippy")


async def log_activity(
    activity_type: str,
    entity_type: str,
    description: str,
    entity_id: str | None = None,
    metadata: dict | None = None,
    user_id: str = "nolan",
) -> None:
    """Log an activity to the activity_log table.

    Args:
        activity_type: Type of activity (e.g., 'memory_created', 'person_updated')
        entity_type: Type of entity affected ('memory', 'person', 'entity', 'system')
        description: Human-readable description
        entity_id: ID of the affected entity (optional)
        metadata: Additional context as JSON (optional)
        user_id: User performing the action (default: 'nolan')
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO activity_log
                        (user_id, activity_type, entity_type, entity_id, description, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (user_id, activity_type, entity_type, entity_id, description, json.dumps(metadata or {})),
                )
    except Exception:
        logger.exception("Failed to log activity")
