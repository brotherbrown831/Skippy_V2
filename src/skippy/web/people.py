import logging
from datetime import datetime

import psycopg
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from skippy.config import settings

logger = logging.getLogger("skippy")

router = APIRouter()


@router.get("/api/people")
async def get_people():
    """Return all people as JSON."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT person_id, name, relationship, birthday, address,
                           phone, email, notes, created_at, updated_at
                    FROM people
                    WHERE user_id = %s
                    ORDER BY name;
                    """,
                    ("nolan",),
                )
                rows = await cur.fetchall()
                columns = [desc.name for desc in cur.description]

                return [
                    {
                        col: (
                            val.isoformat()
                            if isinstance(val, datetime)
                            else val
                        )
                        for col, val in zip(columns, row)
                    }
                    for row in rows
                ]
    except Exception:
        logger.exception("Failed to fetch people")
        return []


@router.delete("/api/people/{person_id}")
async def delete_person(person_id: int):
    """Delete a person by ID."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM people WHERE person_id = %s AND user_id = %s",
                    (person_id, "nolan"),
                )
                if cur.rowcount == 0:
                    return {"ok": False, "error": "Person not found"}
                return {"ok": True}
    except Exception:
        logger.exception("Failed to delete person %s", person_id)
        return {"ok": False, "error": "Database error"}


@router.get("/people")
async def people_page():
    """Redirect to the unified memory bank page."""
    return RedirectResponse(url="/memories", status_code=302)
