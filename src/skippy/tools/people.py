"""People tools for Skippy — structured relational data for people/contacts."""

import logging

import psycopg
from langchain_core.tools import tool

from skippy.config import settings

logger = logging.getLogger("skippy")


@tool
async def add_person(
    name: str,
    relationship: str = "",
    birthday: str = "",
    address: str = "",
    phone: str = "",
    email: str = "",
    notes: str = "",
) -> str:
    """Add a person to the structured people database. Use this when the user tells
    you about someone — their name, relationship, birthday, address, phone, or email.
    If the person already exists, their info will be updated with the new values.

    Args:
        name: The person's name (e.g., "Mike", "Mom", "Dr. Smith").
        relationship: How they relate to the user (e.g., "wife", "friend", "coworker", "dad").
        birthday: Birthday as YYYY-MM-DD or MM-DD if year unknown.
        address: Mailing or home address.
        phone: Phone number.
        email: Email address.
        notes: Any other relevant info about this person.
    """
    # Build SET clause for upsert — only update non-empty fields
    updates = []
    if relationship:
        updates.append("relationship = EXCLUDED.relationship")
    if birthday:
        updates.append("birthday = EXCLUDED.birthday")
    if address:
        updates.append("address = EXCLUDED.address")
    if phone:
        updates.append("phone = EXCLUDED.phone")
    if email:
        updates.append("email = EXCLUDED.email")
    if notes:
        updates.append("notes = EXCLUDED.notes")
    updates.append("updated_at = NOW()")

    set_clause = ", ".join(updates)

    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    INSERT INTO people (user_id, name, relationship, birthday, address, phone, email, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, LOWER(name))
                    DO UPDATE SET {set_clause}
                    RETURNING person_id, name;
                    """,
                    ("nolan", name, relationship or None, birthday or None,
                     address or None, phone or None, email or None, notes or None),
                )
                row = await cur.fetchone()
                logger.info("Upserted person: id=%s name='%s'", row[0], row[1])
                return f"Got it — {name} saved to people database."
    except Exception as e:
        logger.error("Failed to add person: %s", e)
        return f"Error saving person: {e}"


@tool
async def get_person(name: str) -> str:
    """Look up a person by name in the structured people database. Use this when
    the user asks about someone — their birthday, relationship, contact info, etc.

    Args:
        name: The person's name to look up (case-insensitive).
    """
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT name, relationship, birthday, address, phone, email, notes
                    FROM people
                    WHERE user_id = %s AND LOWER(name) = LOWER(%s);
                    """,
                    ("nolan", name),
                )
                row = await cur.fetchone()

                if not row:
                    return f"No one named '{name}' in the people database."

                fields = []
                labels = ["Name", "Relationship", "Birthday", "Address", "Phone", "Email", "Notes"]
                for label, val in zip(labels, row):
                    if val:
                        fields.append(f"{label}: {val}")
                return "\n".join(fields)
    except Exception as e:
        logger.error("Failed to get person: %s", e)
        return f"Error looking up person: {e}"


@tool
async def search_people(query: str) -> str:
    """Search the people database by keyword. Searches across name, relationship,
    and notes fields. Use when the user asks something like "who do I know in Dallas?"
    or "which friends have birthdays in March?"

    Args:
        query: The search term (e.g., "Dallas", "coworker", "March").
    """
    pattern = f"%{query}%"
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT name, relationship, birthday, notes
                    FROM people
                    WHERE user_id = %s AND (
                        name ILIKE %s OR relationship ILIKE %s
                        OR notes ILIKE %s OR address ILIKE %s
                        OR birthday ILIKE %s
                    )
                    ORDER BY name
                    LIMIT 20;
                    """,
                    ("nolan", pattern, pattern, pattern, pattern, pattern),
                )
                rows = await cur.fetchall()

                if not rows:
                    return f"No matches for '{query}' in the people database."

                lines = []
                for name, rel, bday, notes in rows:
                    parts = [name]
                    if rel:
                        parts.append(f"({rel})")
                    if bday:
                        parts.append(f"— birthday: {bday}")
                    if notes:
                        parts.append(f"— {notes[:80]}")
                    lines.append(" ".join(parts))
                return f"Found {len(rows)} match(es):\n" + "\n".join(lines)
    except Exception as e:
        logger.error("Failed to search people: %s", e)
        return f"Error searching people: {e}"


@tool
async def update_person(
    name: str,
    relationship: str = "",
    birthday: str = "",
    address: str = "",
    phone: str = "",
    email: str = "",
    notes: str = "",
) -> str:
    """Update an existing person's information. Only the fields you provide will
    be changed — others stay the same. Use this to correct or add details.

    Args:
        name: The person's name (must match an existing entry).
        relationship: New relationship value.
        birthday: New birthday (YYYY-MM-DD or MM-DD).
        address: New address.
        phone: New phone number.
        email: New email address.
        notes: New notes (replaces existing notes).
    """
    sets = []
    params = []
    if relationship:
        sets.append("relationship = %s")
        params.append(relationship)
    if birthday:
        sets.append("birthday = %s")
        params.append(birthday)
    if address:
        sets.append("address = %s")
        params.append(address)
    if phone:
        sets.append("phone = %s")
        params.append(phone)
    if email:
        sets.append("email = %s")
        params.append(email)
    if notes:
        sets.append("notes = %s")
        params.append(notes)

    if not sets:
        return "No fields provided to update."

    sets.append("updated_at = NOW()")
    params.extend(["nolan", name])

    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE people SET {", ".join(sets)}
                    WHERE user_id = %s AND LOWER(name) = LOWER(%s)
                    RETURNING name;
                    """,
                    params,
                )
                row = await cur.fetchone()
                if not row:
                    return f"No one named '{name}' found to update."
                return f"Updated {row[0]}'s info."
    except Exception as e:
        logger.error("Failed to update person: %s", e)
        return f"Error updating person: {e}"


@tool
async def list_people() -> str:
    """List all people in the structured database. Use when the user asks
    "who do you know about?" or wants to see all stored contacts."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT name, relationship, birthday
                    FROM people
                    WHERE user_id = %s
                    ORDER BY name;
                    """,
                    ("nolan",),
                )
                rows = await cur.fetchall()

                if not rows:
                    return "No people stored yet."

                lines = []
                for name, rel, bday in rows:
                    parts = [f"- {name}"]
                    if rel:
                        parts.append(f"({rel})")
                    if bday:
                        parts.append(f"— birthday: {bday}")
                    lines.append(" ".join(parts))
                return f"People ({len(rows)}):\n" + "\n".join(lines)
    except Exception as e:
        logger.error("Failed to list people: %s", e)
        return f"Error listing people: {e}"


def get_tools() -> list:
    """Return people tools — always available."""
    return [add_person, get_person, search_people, update_person, list_people]
