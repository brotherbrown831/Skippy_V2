"""People tools for Skippy — structured relational data for people/contacts."""

import json
import logging
import math
import re
from datetime import datetime, timezone

import psycopg
from langchain_core.tools import tool
from rapidfuzz import fuzz, process

from skippy.config import settings
from skippy.utils.activity_logger import log_activity

logger = logging.getLogger("skippy")


# ============================================================================
# Helper Functions (Internal, not exposed as tools)
# ============================================================================


def _normalize_phone(phone: str) -> str:
    """Remove non-digit characters from phone number for comparison."""
    return re.sub(r'\D', '', phone) if phone else ""


async def _resolve_person_identity(
    query: str,
    user_id: str = "nolan",
    threshold: int = 85
) -> dict:
    """Resolve person identity using fuzzy matching on canonical_name and aliases.

    Resolution tiers:
    1. Exact match on canonical_name or alias (100% confidence)
    2. Fuzzy match on canonical_name/alias >= 85 (auto-use)
    3. Fuzzy match 70-84 (suggest, requires confirmation)
    4. Phone/email exact match

    Args:
        query: Person name or contact info
        user_id: User ID (default: 'nolan')
        threshold: Minimum fuzzy match score (default: 85)

    Returns:
        {
            "person_id": int,
            "canonical_name": str,
            "confidence": float,
            "matched_field": str,  # "canonical_name", "alias", "phone", "email"
            "suggestion": bool     # True if 70-84 confidence
        }

    Raises:
        ValueError: If no match found or confidence < 70
    """
    # Normalize query
    query_lower = query.strip().lower()

    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url
        ) as conn:
            async with conn.cursor() as cur:
                # Step 1: Exact phone/email match (highest priority)
                if query:
                    normalized_query_phone = _normalize_phone(query)
                    if normalized_query_phone:
                        await cur.execute(
                            """
                            SELECT person_id, canonical_name, phone
                            FROM people
                            WHERE user_id = %s AND phone IS NOT NULL
                              AND REPLACE(REPLACE(REPLACE(phone, '-', ''), ' ', ''), '(', '') = %s
                            LIMIT 1
                            """,
                            (user_id, normalized_query_phone),
                        )
                        row = await cur.fetchone()
                        if row:
                            return {
                                "person_id": row[0],
                                "canonical_name": row[1],
                                "confidence": 100.0,
                                "matched_field": "phone",
                                "suggestion": False,
                            }

                    # Check email
                    if "@" in query_lower:
                        await cur.execute(
                            """
                            SELECT person_id, canonical_name, email
                            FROM people
                            WHERE user_id = %s AND LOWER(email) = %s
                            LIMIT 1
                            """,
                            (user_id, query_lower),
                        )
                        row = await cur.fetchone()
                        if row:
                            return {
                                "person_id": row[0],
                                "canonical_name": row[1],
                                "confidence": 100.0,
                                "matched_field": "email",
                                "suggestion": False,
                            }

                # Step 2: Exact canonical_name match
                await cur.execute(
                    """
                    SELECT person_id, canonical_name
                    FROM people
                    WHERE user_id = %s AND LOWER(canonical_name) = %s
                    LIMIT 1
                    """,
                    (user_id, query_lower),
                )
                row = await cur.fetchone()
                if row:
                    return {
                        "person_id": row[0],
                        "canonical_name": row[1],
                        "confidence": 100.0,
                        "matched_field": "canonical_name",
                        "suggestion": False,
                    }

                # Step 3: Exact alias match
                await cur.execute(
                    """
                    SELECT person_id, canonical_name, aliases
                    FROM people
                    WHERE user_id = %s AND aliases IS NOT NULL
                    ORDER BY person_id
                    """,
                    (user_id,),
                )
                rows = await cur.fetchall()
                for row in rows:
                    aliases = row[2] or []
                    for alias in aliases:
                        if alias.lower() == query_lower:
                            return {
                                "person_id": row[0],
                                "canonical_name": row[1],
                                "confidence": 100.0,
                                "matched_field": "alias",
                                "suggestion": False,
                            }

                # Step 4: Fetch all people for fuzzy matching
                await cur.execute(
                    """
                    SELECT person_id, canonical_name, aliases
                    FROM people
                    WHERE user_id = %s
                    ORDER BY person_id
                    """,
                    (user_id,),
                )
                all_people = await cur.fetchall()

    except Exception as e:
        logger.error("Failed to query people database: %s", e)
        raise ValueError(f"Database error during person lookup: {e}")

    # Step 5: Fuzzy match on canonical_name and aliases
    best_match = None
    best_score = 0
    best_field = None

    for person_id, canonical_name, aliases in all_people:
        # Check canonical_name (use token_set_ratio for better name matching)
        score = fuzz.token_set_ratio(query_lower, canonical_name.lower())
        if score > best_score:
            best_score = score
            best_match = (person_id, canonical_name)
            best_field = "canonical_name"

        # Check aliases
        if aliases:
            for alias in aliases:
                score = fuzz.token_set_ratio(query_lower, alias.lower())
                if score > best_score:
                    best_score = score
                    best_match = (person_id, canonical_name)
                    best_field = "alias"

    # Evaluate result
    if best_score >= threshold:
        # High confidence - auto-use
        return {
            "person_id": best_match[0],
            "canonical_name": best_match[1],
            "confidence": float(best_score),
            "matched_field": best_field,
            "suggestion": False,
        }
    elif best_score >= 70:
        # Medium confidence - suggest
        return {
            "person_id": best_match[0],
            "canonical_name": best_match[1],
            "confidence": float(best_score),
            "matched_field": best_field,
            "suggestion": True,
        }
    else:
        raise ValueError(
            f"No person found matching '{query}' (best match: {best_score}%)"
        )


async def _update_person_importance(person_id: int) -> None:
    """Update importance score when person is mentioned or updated.

    Scoring algorithm:
    - Increment mention_count
    - Update last_mentioned to NOW()
    - Calculate importance_score:
      base_score = min(mention_count * 2, 50)  # Frequency component
      days_since = days between now and last_mentioned
      recency_bonus = 50 * exp(-days_since / 30)  # Decays over 30 days
      importance_score = base_score + recency_bonus
    """
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Get current values
                await cur.execute(
                    """
                    SELECT mention_count, last_mentioned
                    FROM people
                    WHERE person_id = %s
                    """,
                    (person_id,),
                )
                row = await cur.fetchone()

                if not row:
                    logger.warning("Person %d not found for importance update", person_id)
                    return

                mention_count = (row[0] or 0) + 1
                old_last_mentioned = row[1]

                # Calculate base score from frequency
                base_score = min(mention_count * 2, 50)

                # Calculate recency bonus (decays over 30 days)
                now = datetime.now(timezone.utc)
                if old_last_mentioned and isinstance(old_last_mentioned, datetime):
                    # If last_mentioned is timezone-naive, assume UTC
                    if old_last_mentioned.tzinfo is None:
                        old_last_mentioned = old_last_mentioned.replace(tzinfo=timezone.utc)
                    days_since = (now - old_last_mentioned).days
                    recency_bonus = 50 * math.exp(-days_since / 30)
                else:
                    recency_bonus = 50  # First mention gets full bonus

                importance_score = base_score + recency_bonus

                # Update database
                await cur.execute(
                    """
                    UPDATE people
                    SET mention_count = %s,
                        last_mentioned = NOW(),
                        importance_score = %s,
                        updated_at = NOW()
                    WHERE person_id = %s
                    """,
                    (mention_count, importance_score, person_id),
                )
                logger.debug(
                    "Updated person %d importance: score=%.2f, mentions=%d",
                    person_id,
                    importance_score,
                    mention_count,
                )

    except Exception as e:
        logger.error("Failed to update person importance: %s", e)


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
    try:
        # Step 1: Check for existing person using fuzzy matching
        try:
            identity = await _resolve_person_identity(name)
            if identity["suggestion"]:
                # Medium confidence (70-84) - suggest instead of auto-merging
                suggestion = (
                    f"I found a similar person: '{identity['canonical_name']}' "
                    f"({identity['confidence']:.0f}% match). "
                    f"Did you mean them? Or should I create a new entry for '{name}'?"
                )
                return suggestion

            # High confidence (>=85) or exact match - use existing person
            person_id = identity["person_id"]

        except ValueError:
            # No match found - will create new person
            person_id = None

        # Step 2: Upsert person
        if person_id:
            # Update existing person
            updates = []
            params = []

            if relationship:
                updates.append("relationship = %s")
                params.append(relationship)
            if birthday:
                updates.append("birthday = %s")
                params.append(birthday)
            if address:
                updates.append("address = %s")
                params.append(address)
            if phone:
                updates.append("phone = %s")
                params.append(phone)
            if email:
                updates.append("email = %s")
                params.append(email)
            if notes:
                updates.append("notes = %s")
                params.append(notes)

            updates.append("updated_at = NOW()")
            params.append(person_id)

            if len(updates) > 1:  # More than just updated_at
                async with await psycopg.AsyncConnection.connect(
                    settings.database_url, autocommit=True
                ) as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            f"""
                            UPDATE people SET {", ".join(updates)}
                            WHERE person_id = %s
                            RETURNING person_id, canonical_name;
                            """,
                            params,
                        )
                        row = await cur.fetchone()
                        if row:
                            logger.info("Updated existing person: id=%s name='%s'", row[0], row[1])
                            await log_activity(
                                activity_type="person_updated",
                                entity_type="person",
                                entity_id=str(row[0]),
                                description=f"Updated person: {row[1]}",
                                metadata={"relationship": relationship},
                                user_id="nolan",
                            )

        else:
            # Create new person
            async with await psycopg.AsyncConnection.connect(
                settings.database_url, autocommit=True
            ) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO people (
                            user_id, name, canonical_name, relationship, birthday,
                            address, phone, email, notes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING person_id, canonical_name;
                        """,
                        (
                            "nolan", name, name, relationship or None, birthday or None,
                            address or None, phone or None, email or None, notes or None
                        ),
                    )
                    row = await cur.fetchone()
                    if row:
                        person_id = row[0]
                        logger.info("Created new person: id=%s name='%s'", row[0], row[1])
                        await log_activity(
                            activity_type="person_created",
                            entity_type="person",
                            entity_id=str(row[0]),
                            description=f"Added person: {row[1]}",
                            metadata={"relationship": relationship},
                            user_id="nolan",
                        )

        # Step 3: Update importance
        if person_id:
            await _update_person_importance(person_id)

        return f"Got it — {name} saved to people database."

    except Exception as e:
        logger.error("Failed to add person: %s", e)
        return f"Error saving person: {e}"


@tool
async def get_person(name: str) -> str:
    """Look up a person by name in the structured people database. Use this when
    the user asks about someone — their birthday, relationship, contact info, etc.
    Supports fuzzy matching for aliases and variations.

    Args:
        name: The person's name to look up (supports partial matches and aliases).
    """
    try:
        # Step 1: Resolve person identity using fuzzy matching
        try:
            identity = await _resolve_person_identity(name)
            person_id = identity["person_id"]
        except ValueError:
            return f"No one named '{name}' in the people database."

        # Step 2: Fetch person details
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT canonical_name, aliases, relationship, birthday, address,
                           phone, email, notes, importance_score, last_mentioned
                    FROM people
                    WHERE person_id = %s;
                    """,
                    (person_id,),
                )
                row = await cur.fetchone()

                if not row:
                    return f"Person not found in database."

                (canonical_name, aliases, relationship, birthday, address,
                 phone, email, notes, importance_score, last_mentioned) = row

                fields = []
                fields.append(f"Name: {canonical_name}")

                if aliases:
                    aliases_str = ", ".join(aliases)
                    fields.append(f"Aliases: {aliases_str}")

                if relationship:
                    fields.append(f"Relationship: {relationship}")
                if birthday:
                    fields.append(f"Birthday: {birthday}")
                if address:
                    fields.append(f"Address: {address}")
                if phone:
                    fields.append(f"Phone: {phone}")
                if email:
                    fields.append(f"Email: {email}")
                if notes:
                    fields.append(f"Notes: {notes}")

                if importance_score and importance_score > 0:
                    fields.append(f"Importance: {importance_score:.1f}/100")
                if last_mentioned:
                    fields.append(f"Last mentioned: {last_mentioned}")

                if identity["confidence"] < 100:
                    fields.append(f"Matched with {identity['confidence']:.0f}% confidence")

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
    canonical_name: str = "",
) -> str:
    """Update an existing person's information. Only the fields you provide will
    be changed — others stay the same. Use this to correct or add details.

    Supports fuzzy matching for finding the person by name or alias.

    Args:
        name: The person's name to find (supports aliases and fuzzy matching).
        relationship: New relationship value.
        birthday: New birthday (YYYY-MM-DD or MM-DD).
        address: New address.
        phone: New phone number.
        email: New email address.
        notes: New notes (replaces existing notes).
        canonical_name: Update canonical name (official display name).
    """
    try:
        # Step 1: Resolve person identity
        try:
            identity = await _resolve_person_identity(name)
            person_id = identity["person_id"]
        except ValueError:
            return f"No one named '{name}' found to update."

        # Step 2: Build update fields
        sets = []
        params = []

        if canonical_name:
            sets.append("canonical_name = %s")
            params.append(canonical_name)
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
        params.append(person_id)

        # Step 3: Execute update
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE people SET {", ".join(sets)}
                    WHERE person_id = %s
                    RETURNING canonical_name;
                    """,
                    params,
                )
                row = await cur.fetchone()
                if not row:
                    return f"No one named '{name}' found to update."

                # Step 4: Update importance
                await _update_person_importance(person_id)

                await log_activity(
                    activity_type="person_updated",
                    entity_type="person",
                    entity_id=str(person_id),
                    description=f"Updated person: {row[0]}",
                    metadata={"relationship": relationship},
                    user_id="nolan",
                )

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


@tool
async def merge_people(
    primary_person_name: str,
    duplicate_person_name: str,
    keep_aliases: bool = True,
) -> str:
    """Merge a duplicate person into the primary person record.

    Combines all information from both records. The duplicate's name
    will be added as an alias if keep_aliases=True. Importance scores
    are combined (higher + bonus) and mention counts are summed.

    Args:
        primary_person_name: The person to keep (e.g., "Summer Hollars").
        duplicate_person_name: The duplicate to merge (e.g., "Summer").
        keep_aliases: Add duplicate's name as alias (default: True).
    """
    try:
        # Step 1: Resolve both people
        try:
            primary_identity = await _resolve_person_identity(primary_person_name)
            primary_id = primary_identity["person_id"]
        except ValueError:
            return f"Could not find person '{primary_person_name}' to merge into."

        try:
            dup_identity = await _resolve_person_identity(duplicate_person_name)
            dup_id = dup_identity["person_id"]
        except ValueError:
            return f"Could not find duplicate person '{duplicate_person_name}' to merge."

        if primary_id == dup_id:
            return "Cannot merge a person with themselves."

        # Step 2: Fetch both records
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT person_id, canonical_name, aliases, relationship, birthday,
                           address, phone, email, notes, importance_score, mention_count,
                           merged_from
                    FROM people
                    WHERE person_id IN (%s, %s)
                    ORDER BY person_id
                    """,
                    (primary_id, dup_id),
                )
                rows = await cur.fetchall()

                if len(rows) != 2:
                    return "Error: Could not fetch both people records."

                primary_row = next(r for r in rows if r[0] == primary_id)
                dup_row = next(r for r in rows if r[0] == dup_id)

                (_, prim_name, prim_aliases, prim_rel, prim_bday, prim_addr,
                 prim_phone, prim_email, prim_notes, prim_score, prim_mentions,
                 prim_merged_from) = primary_row

                (_, dup_name, dup_aliases, dup_rel, dup_bday, dup_addr,
                 dup_phone, dup_email, dup_notes, dup_score, dup_mentions,
                 dup_merged_from) = dup_row

                # Step 3: Merge data (prefer primary, fill in missing from duplicate)
                merged_aliases = list(prim_aliases or [])
                if keep_aliases:
                    if dup_name not in merged_aliases:
                        merged_aliases.append(dup_name)

                if dup_aliases:
                    for alias in dup_aliases:
                        if alias not in merged_aliases:
                            merged_aliases.append(alias)

                # Combine importance scores and mention counts
                merged_score = max(prim_score or 0, dup_score or 0) + 10
                merged_mentions = (prim_mentions or 0) + (dup_mentions or 0)

                # Track merge
                merged_from = list(prim_merged_from or [])
                merged_from.append(dup_id)

                # Step 4: Update primary record
                await cur.execute(
                    """
                    UPDATE people
                    SET aliases = %s,
                        relationship = COALESCE(NULLIF(%s, ''), relationship),
                        birthday = COALESCE(NULLIF(%s, ''), birthday),
                        address = COALESCE(NULLIF(%s, ''), address),
                        phone = COALESCE(NULLIF(%s, ''), phone),
                        email = COALESCE(NULLIF(%s, ''), email),
                        notes = CASE
                            WHEN notes IS NOT NULL AND %s IS NOT NULL THEN notes || '; ' || %s
                            WHEN %s IS NOT NULL THEN %s
                            ELSE notes
                        END,
                        importance_score = %s,
                        mention_count = %s,
                        merged_from = %s,
                        updated_at = NOW()
                    WHERE person_id = %s
                    RETURNING canonical_name
                    """,
                    (
                        json.dumps(merged_aliases),
                        dup_rel, dup_bday, dup_addr, dup_phone, dup_email,
                        dup_notes, dup_notes, dup_notes, dup_notes,
                        merged_score, merged_mentions, merged_from, primary_id
                    ),
                )
                result = await cur.fetchone()

                # Step 5: Migrate all memories from duplicate to primary person
                await cur.execute(
                    """
                    UPDATE semantic_memories
                    SET person_id = %s
                    WHERE person_id = %s
                    """,
                    (primary_id, dup_id),
                )
                memory_count = cur.rowcount
                if memory_count > 0:
                    logger.info("Migrated %d memories from person %d to %d during merge", memory_count, dup_id, primary_id)

                # Step 6: Delete duplicate record
                await cur.execute(
                    "DELETE FROM people WHERE person_id = %s",
                    (dup_id,),
                )

                logger.info(
                    "Merged person %d (%s) into %d (%s)",
                    dup_id, dup_name, primary_id, prim_name
                )
                await log_activity(
                    activity_type="people_merged",
                    entity_type="person",
                    entity_id=str(primary_id),
                    description=f"Merged '{dup_name}' into '{result[0]}'",
                    metadata={"merged_duplicate_id": dup_id, "aliases": merged_aliases},
                    user_id="nolan",
                )

                return (
                    f"Merged '{dup_name}' into '{result[0]}'. "
                    f"Aliases: {', '.join(merged_aliases)}"
                )

    except Exception as e:
        logger.error("Failed to merge people: %s", e)
        return f"Error merging people: {e}"


@tool
async def add_person_alias(person_name: str, alias: str) -> str:
    """Add an alternative name/nickname for a person.

    Use this when someone goes by multiple names (e.g., "Summer" for "Summer Hollars").

    Args:
        person_name: The person's canonical name or any known name.
        alias: Alternative name to add (e.g., "Summer").
    """
    try:
        # Step 1: Resolve person
        try:
            identity = await _resolve_person_identity(person_name)
            person_id = identity["person_id"]
        except ValueError:
            return f"Could not find person '{person_name}' to add alias for."

        # Step 2: Add alias (if not already present)
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Get current aliases
                await cur.execute(
                    "SELECT aliases FROM people WHERE person_id = %s",
                    (person_id,),
                )
                row = await cur.fetchone()
                aliases = list(row[0] or []) if row else []

                if alias in aliases:
                    return f"'{alias}' is already an alias for this person."

                aliases.append(alias)

                # Update
                await cur.execute(
                    """
                    UPDATE people
                    SET aliases = %s, updated_at = NOW()
                    WHERE person_id = %s
                    RETURNING canonical_name
                    """,
                    (json.dumps(aliases), person_id),
                )
                result = await cur.fetchone()
                logger.info("Added alias '%s' for person %d", alias, person_id)
                await log_activity(
                    activity_type="person_alias_added",
                    entity_type="person",
                    entity_id=str(person_id),
                    description=f"Added alias '{alias}' for {result[0]}",
                    metadata={"alias": alias},
                    user_id="nolan",
                )
                return f"Added alias '{alias}' for {result[0]}. Now aliases: {', '.join(aliases)}"

    except Exception as e:
        logger.error("Failed to add alias: %s", e)
        return f"Error adding alias: {e}"


@tool
async def remove_person_alias(person_name: str, alias: str) -> str:
    """Remove an alias from a person's alternative names.

    Args:
        person_name: The person's canonical name or any known name.
        alias: Alias to remove.
    """
    try:
        # Step 1: Resolve person
        try:
            identity = await _resolve_person_identity(person_name)
            person_id = identity["person_id"]
        except ValueError:
            return f"Could not find person '{person_name}' to remove alias from."

        # Step 2: Remove alias
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Get current aliases
                await cur.execute(
                    "SELECT aliases FROM people WHERE person_id = %s",
                    (person_id,),
                )
                row = await cur.fetchone()
                aliases = list(row[0] or []) if row else []

                if alias not in aliases:
                    return f"'{alias}' is not an alias for this person."

                aliases.remove(alias)

                # Update
                await cur.execute(
                    """
                    UPDATE people
                    SET aliases = %s, updated_at = NOW()
                    WHERE person_id = %s
                    RETURNING canonical_name
                    """,
                    (json.dumps(aliases), person_id),
                )
                result = await cur.fetchone()
                logger.info("Removed alias '%s' from person %d", alias, person_id)
                await log_activity(
                    activity_type="person_alias_removed",
                    entity_type="person",
                    entity_id=str(person_id),
                    description=f"Removed alias '{alias}' from {result[0]}",
                    metadata={"alias": alias},
                    user_id="nolan",
                )
                if aliases:
                    return f"Removed alias '{alias}' from {result[0]}. Remaining aliases: {', '.join(aliases)}"
                else:
                    return f"Removed alias '{alias}' from {result[0]}. No more aliases."

    except Exception as e:
        logger.error("Failed to remove alias: %s", e)
        return f"Error removing alias: {e}"


@tool
async def find_duplicate_people(threshold: int = 70) -> str:
    """Scan all people for potential duplicates using fuzzy matching.

    Returns JSON list of duplicate clusters with confidence scores.
    Helps identify people who should be merged.

    Args:
        threshold: Minimum fuzzy match score (default: 70).
    """
    try:
        # Fetch all people
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT person_id, canonical_name, aliases, phone, email
                    FROM people
                    WHERE user_id = %s
                    ORDER BY person_id
                    """,
                    ("nolan",),
                )
                people = await cur.fetchall()

        # Build search terms for each person
        people_data = {}
        for person_id, canonical_name, aliases, phone, email in people:
            terms = [canonical_name.lower()]
            if aliases:
                terms.extend([a.lower() for a in aliases])
            if phone:
                terms.append(_normalize_phone(phone))
            if email:
                terms.append(email.lower())
            people_data[person_id] = {
                "name": canonical_name,
                "terms": terms,
            }

        # Find duplicates
        clusters = {}
        processed = set()

        for person_id in people_data:
            if person_id in processed:
                continue

            cluster = {
                "canonical_name": people_data[person_id]["name"],
                "members": [
                    {
                        "person_id": person_id,
                        "name": people_data[person_id]["name"],
                        "confidence": 100.0,
                    }
                ],
            }

            # Find similar people
            for other_id in people_data:
                if other_id <= person_id or other_id in processed:
                    continue

                # Check exact phone/email match
                if people_data[person_id]["terms"] and people_data[other_id]["terms"]:
                    for term1 in people_data[person_id]["terms"]:
                        for term2 in people_data[other_id]["terms"]:
                            if term1 and term2 and term1 == term2 and len(term1) > 3:
                                # Exact match on phone/email
                                cluster["members"].append({
                                    "person_id": other_id,
                                    "name": people_data[other_id]["name"],
                                    "confidence": 100.0,
                                })
                                processed.add(other_id)
                                break

            # Fuzzy match on names (use token_set_ratio for better name matching)
            for other_id in people_data:
                if other_id <= person_id or other_id in processed:
                    continue

                score = fuzz.token_set_ratio(
                    people_data[person_id]["name"].lower(),
                    people_data[other_id]["name"].lower()
                )

                if score >= threshold:
                    cluster["members"].append({
                        "person_id": other_id,
                        "name": people_data[other_id]["name"],
                        "confidence": float(score),
                    })
                    processed.add(other_id)

            processed.add(person_id)

            if len(cluster["members"]) > 1:
                clusters[person_id] = cluster

        result = list(clusters.values())
        if result:
            return json.dumps(result, indent=2)
        else:
            return "No duplicate people detected."

    except Exception as e:
        logger.error("Failed to find duplicates: %s", e)
        return f"Error finding duplicates: {e}"


@tool
async def search_people_fuzzy(query: str, limit: int = 10) -> str:
    """Search for people using fuzzy matching on names and aliases.

    Returns ranked results with confidence scores.
    Searches: canonical_name, aliases, phone, email, relationship, notes.

    Args:
        query: Search query (can be name, alias, phone, email, relationship, etc.).
        limit: Maximum results (default: 10).
    """
    try:
        # Fetch all people
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT person_id, canonical_name, aliases, phone, email,
                           relationship, notes
                    FROM people
                    WHERE user_id = %s
                    ORDER BY person_id
                    """,
                    ("nolan",),
                )
                people = await cur.fetchall()

        # Build search corpus
        results = []
        query_lower = query.strip().lower()

        for person_id, canonical_name, aliases, phone, email, relationship, notes in people:
            best_score = 0
            matched_field = ""

            # Check canonical name
            score = fuzz.ratio(query_lower, canonical_name.lower())
            if score > best_score:
                best_score = score
                matched_field = "canonical_name"

            # Check aliases
            if aliases:
                for alias in aliases:
                    score = fuzz.ratio(query_lower, alias.lower())
                    if score > best_score:
                        best_score = score
                        matched_field = "alias"

            # Check phone
            if phone:
                norm_query_phone = _normalize_phone(query)
                norm_phone = _normalize_phone(phone)
                if norm_query_phone and norm_phone:
                    if norm_query_phone == norm_phone:
                        best_score = 100.0
                        matched_field = "phone"
                    else:
                        score = fuzz.ratio(query_lower, phone.lower())
                        if score > best_score:
                            best_score = score
                            matched_field = "phone"

            # Check email
            if email:
                score = fuzz.ratio(query_lower, email.lower())
                if score > best_score:
                    best_score = score
                    matched_field = "email"

            # Check relationship
            if relationship:
                score = fuzz.ratio(query_lower, relationship.lower())
                if score > best_score:
                    best_score = score
                    matched_field = "relationship"

            # Check notes
            if notes:
                score = fuzz.ratio(query_lower, notes.lower())
                if score > best_score:
                    best_score = score
                    matched_field = "notes"

            # Only include if score >= 50
            if best_score >= 50:
                results.append({
                    "person_id": person_id,
                    "name": canonical_name,
                    "confidence": float(best_score),
                    "matched_field": matched_field,
                })

        # Sort by confidence descending
        results.sort(key=lambda x: x["confidence"], reverse=True)
        results = results[:limit]

        if results:
            lines = [f"Found {len(results)} match(es):"]
            for r in results:
                lines.append(
                    f"  - {r['name']} ({r['confidence']:.0f}% via {r['matched_field']})"
                )
            return "\n".join(lines)
        else:
            return f"No matches found for '{query}'."

    except Exception as e:
        logger.error("Failed to search people: %s", e)
        return f"Error searching people: {e}"


@tool
async def get_person_memories(name: str, limit: int = 20) -> str:
    """Get all memories related to a specific person.

    Use this when the user asks "What do I know about [person]?" or
    "Tell me everything about [person]".

    Returns structured list of all facts/memories linked to this person.

    Args:
        name: Person's name (supports fuzzy matching and aliases).
        limit: Maximum number of memories to return (default: 20).
    """
    try:
        # Step 1: Resolve person identity
        try:
            identity = await _resolve_person_identity(name, "nolan")
            person_id = identity["person_id"]
            canonical_name = identity["canonical_name"]
        except ValueError:
            return f"No one named '{name}' found in the people database."

        # Step 2: Fetch all memories for this person
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT memory_id, content, category, confidence_score,
                           reinforcement_count, created_at
                    FROM semantic_memories
                    WHERE person_id = %s
                      AND user_id = %s
                      AND status = 'active'
                    ORDER BY
                        CASE
                            WHEN category = 'person' THEN 1
                            WHEN category = 'family' THEN 2
                            ELSE 3
                        END,
                        confidence_score DESC,
                        created_at DESC
                    LIMIT %s
                    """,
                    (person_id, "nolan", limit),
                )
                rows = await cur.fetchall()

                if not rows:
                    return f"No memories found for {canonical_name}."

                # Format response
                lines = [f"Memories about {canonical_name} ({len(rows)} total):"]
                lines.append("")

                for mem_id, content, category, confidence, reinforcements, created in rows:
                    # Add category emoji
                    emoji = "👤" if category == "person" else "👨‍👩‍👧‍👦" if category == "family" else "📝"

                    # Build memory line
                    parts = [f"{emoji} {content}"]

                    # Add metadata if notable
                    meta = []
                    if reinforcements > 0:
                        meta.append(f"reinforced {reinforcements}x")
                    if confidence >= 0.8:
                        meta.append(f"high confidence")

                    if meta:
                        parts.append(f"({', '.join(meta)})")

                    lines.append(" ".join(parts))

                return "\n".join(lines)

    except Exception as e:
        logger.error("Failed to get person memories: %s", e)
        return f"Error retrieving memories: {e}"


@tool
async def link_memory_to_person(memory_id: int, person_name: str) -> str:
    """Manually link an existing memory to a person.

    Use when a memory should be associated with a person but wasn't
    automatically linked.

    Args:
        memory_id: ID of the memory to link.
        person_name: Name of the person to link to.
    """
    try:
        # Resolve person
        try:
            identity = await _resolve_person_identity(person_name, "nolan")
            person_id = identity["person_id"]
            canonical_name = identity["canonical_name"]
        except ValueError:
            return f"No one named '{person_name}' found."

        # Update memory
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE semantic_memories
                    SET person_id = %s
                    WHERE memory_id = %s AND user_id = %s
                    RETURNING content
                    """,
                    (person_id, memory_id, "nolan"),
                )
                row = await cur.fetchone()

                if not row:
                    return f"Memory {memory_id} not found."

                logger.info("Linked memory %d to person %d (%s)", memory_id, person_id, canonical_name)
                await log_activity(
                    activity_type="memory_linked",
                    entity_type="memory",
                    entity_id=str(memory_id),
                    description=f"Linked memory to {canonical_name}",
                    metadata={"person_id": person_id, "content": row[0][:100]},
                    user_id="nolan",
                )

                return f"Linked memory to {canonical_name}: {row[0]}"

    except Exception as e:
        logger.error("Failed to link memory to person: %s", e)
        return f"Error linking memory: {e}"


@tool
async def unlink_memory_from_person(memory_id: int) -> str:
    """Remove the person association from a memory.

    Args:
        memory_id: ID of the memory to unlink.
    """
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE semantic_memories
                    SET person_id = NULL
                    WHERE memory_id = %s AND user_id = %s
                    RETURNING content
                    """,
                    (memory_id, "nolan"),
                )
                row = await cur.fetchone()

                if not row:
                    return f"Memory {memory_id} not found."

                logger.info("Unlinked memory %d from person", memory_id)
                await log_activity(
                    activity_type="memory_unlinked",
                    entity_type="memory",
                    entity_id=str(memory_id),
                    description="Unlinked memory from person",
                    metadata={"content": row[0][:100]},
                    user_id="nolan",
                )

                return f"Unlinked memory: {row[0]}"

    except Exception as e:
        logger.error("Failed to unlink memory: %s", e)
        return f"Error unlinking memory: {e}"


def get_tools() -> list:
    """Return people tools — always available."""
    return [
        add_person,
        get_person,
        get_person_memories,
        search_people,
        search_people_fuzzy,
        update_person,
        list_people,
        merge_people,
        add_person_alias,
        remove_person_alias,
        find_duplicate_people,
        link_memory_to_person,
        unlink_memory_from_person,
    ]
