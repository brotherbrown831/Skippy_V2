"""Google Contacts → People table sync for Skippy."""

import json
import logging
import re

import psycopg
from langchain_core.tools import tool

from skippy.config import settings
from skippy.tools.google_auth import get_google_user_service
from skippy.utils.activity_logger import log_activity

logger = logging.getLogger("skippy")

PERSON_FIELDS = (
    "names,emailAddresses,phoneNumbers,addresses,birthdays,biographies,organizations"
)


def _extract_birthday(bdays: list[dict]) -> str:
    """Format a Google birthday dict as YYYY-MM-DD or MM-DD."""
    if not bdays:
        return ""
    date = bdays[0].get("date", {})
    month = date.get("month")
    day = date.get("day")
    if not month or not day:
        return ""
    year = date.get("year")
    if year:
        return f"{year:04d}-{month:02d}-{day:02d}"
    return f"{month:02d}-{day:02d}"


def _extract_notes(person: dict) -> str:
    """Combine biographies and organization info into notes."""
    parts = []
    for bio in person.get("biographies", []):
        val = bio.get("value", "").strip()
        if val:
            parts.append(val)
    for org in person.get("organizations", []):
        title = org.get("title", "")
        company = org.get("name", "")
        if title and company:
            parts.append(f"{title} at {company}")
        elif company:
            parts.append(company)
    return "; ".join(parts) if parts else ""


def _strip_name_suffixes(name: str) -> str:
    """Strip common suffixes from Google Contact display names.

    Examples:
        "Summer Hollars - ICE" -> "Summer Hollars"
        "John Doe 2024" -> "John Doe"
    """
    # Strip trailing ICE labels, years, etc.
    name = re.sub(r'\s*-\s*ICE\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+\d{4}\s*$', '', name)  # Year at end
    name = re.sub(r'\s*\(.*?\)\s*$', '', name)  # Anything in parens at end
    return name.strip()


def _normalize_phone(phone: str) -> str:
    """Remove non-digit characters from phone number for comparison."""
    return re.sub(r'\D', '', phone) if phone else ""


async def _update_person_importance(person_id: int) -> None:
    """Update importance score for a person."""
    from skippy.tools.people import _update_person_importance
    await _update_person_importance(person_id)


async def sync_google_contacts_to_people() -> dict:
    """Fetch all Google Contacts and upsert into the people table.

    Implements smart identity resolution:
    1. Strip suffixes (ICE, years) from display names
    2. Check for exact phone/email match → update existing + add full name as alias
    3. Fuzzy match on base name >=85 → update existing + add full name as alias
    4. Fuzzy match 70-84 → log as suggestion, conservative (don't merge)
    5. Otherwise → create new person

    Returns dict with keys: synced, skipped, errors, auto_merged, suggestions.
    """
    from rapidfuzz import fuzz
    from skippy.tools.people import _resolve_person_identity

    service = get_google_user_service("people", "v1")

    # Paginate through all contacts
    contacts = []
    page_token = None
    while True:
        kwargs = {
            "resourceName": "people/me",
            "personFields": PERSON_FIELDS,
            "pageSize": 200,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        result = service.people().connections().list(**kwargs).execute()
        connections = result.get("connections", [])
        contacts.extend(connections)

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    logger.info("Fetched %d Google Contacts for sync", len(contacts))

    synced = 0
    skipped = 0
    errors = 0
    auto_merged = 0
    suggestions = []

    async with await psycopg.AsyncConnection.connect(
        settings.database_url, autocommit=True
    ) as conn:
        async with conn.cursor() as cur:
            for person in contacts:
                names = person.get("names", [])
                if not names:
                    skipped += 1
                    continue

                full_name = names[0].get("displayName", "").strip()
                if not full_name:
                    skipped += 1
                    continue

                # Step 1: Strip common suffixes
                base_name = _strip_name_suffixes(full_name)

                emails = person.get("emailAddresses", [])
                phones = person.get("phoneNumbers", [])
                addresses = person.get("addresses", [])

                email = emails[0].get("value", "") if emails else ""
                phone = phones[0].get("value", "") if phones else ""
                address = addresses[0].get("formattedValue", "") if addresses else ""
                birthday = _extract_birthday(person.get("birthdays", []))
                notes = _extract_notes(person)

                try:
                    person_id = None
                    merged_into = None

                    # Step 2: Check for exact phone/email match
                    if phone:
                        norm_phone = _normalize_phone(phone)
                        if norm_phone:
                            await cur.execute(
                                """
                                SELECT person_id, canonical_name, aliases
                                FROM people
                                WHERE user_id = %s AND phone IS NOT NULL
                                  AND REPLACE(REPLACE(REPLACE(phone, '-', ''), ' ', ''), '(', '') = %s
                                LIMIT 1
                                """,
                                ("nolan", norm_phone),
                            )
                            row = await cur.fetchone()
                            if row:
                                person_id = row[0]
                                merged_into = row[1]
                                auto_merged += 1
                                logger.info(
                                    "Contact sync: matched '%s' via phone (%s)",
                                    full_name, phone
                                )

                    if not person_id and email:
                        await cur.execute(
                            """
                            SELECT person_id, canonical_name, aliases
                            FROM people
                            WHERE user_id = %s AND LOWER(email) = LOWER(%s)
                            LIMIT 1
                            """,
                            ("nolan", email),
                        )
                        row = await cur.fetchone()
                        if row:
                            person_id = row[0]
                            merged_into = row[1]
                            auto_merged += 1
                            logger.info(
                                "Contact sync: matched '%s' via email (%s)",
                                full_name, email
                            )

                    # Step 3: Fuzzy match on base name
                    if not person_id:
                        try:
                            identity = await _resolve_person_identity(base_name)
                            if identity["suggestion"]:
                                # 70-84 confidence - log as suggestion
                                suggestions.append({
                                    "google_name": full_name,
                                    "base_name": base_name,
                                    "existing_person": identity["canonical_name"],
                                    "confidence": identity["confidence"],
                                })
                                logger.debug(
                                    "Contact sync suggestion: '%s' (~= '%s' at %.0f%%)",
                                    full_name, identity["canonical_name"],
                                    identity["confidence"]
                                )
                            else:
                                # >=85 confidence - auto-merge
                                person_id = identity["person_id"]
                                merged_into = identity["canonical_name"]
                                auto_merged += 1
                                logger.info(
                                    "Contact sync: matched '%s' via fuzzy name (%s, %.0f%%)",
                                    full_name, base_name, identity["confidence"]
                                )
                        except ValueError:
                            # No match - will create new
                            pass

                    # Step 4: Update existing or create new
                    if person_id:
                        # Update existing and add full name as alias if different
                        await cur.execute(
                            """
                            SELECT aliases FROM people WHERE person_id = %s
                            """,
                            (person_id,),
                        )
                        row = await cur.fetchone()
                        aliases = list(row[0] or []) if row else []

                        if full_name != base_name and full_name not in aliases:
                            aliases.append(full_name)
                            aliases_json = json.dumps(aliases)
                        else:
                            aliases_json = json.dumps(aliases)

                        await cur.execute(
                            """
                            UPDATE people
                            SET aliases = %s,
                                birthday = COALESCE(NULLIF(%s, ''), birthday),
                                address = COALESCE(NULLIF(%s, ''), address),
                                phone = COALESCE(NULLIF(%s, ''), phone),
                                email = COALESCE(NULLIF(%s, ''), email),
                                notes = COALESCE(NULLIF(%s, ''), notes),
                                updated_at = NOW()
                            WHERE person_id = %s
                            RETURNING person_id
                            """,
                            (
                                aliases_json,
                                birthday or "", address or "",
                                phone or "", email or "", notes or "",
                                person_id
                            ),
                        )
                        result = await cur.fetchone()
                        if result:
                            await _update_person_importance(person_id)
                    else:
                        # Create new person
                        await cur.execute(
                            """
                            INSERT INTO people (
                                user_id, name, canonical_name, aliases,
                                birthday, address, phone, email, notes
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING person_id
                            """,
                            (
                                "nolan", base_name, base_name,
                                json.dumps([full_name] if full_name != base_name else []),
                                birthday or "", address or "",
                                phone or "", email or "", notes or ""
                            ),
                        )
                        result = await cur.fetchone()
                        if result:
                            person_id = result[0]
                            await _update_person_importance(person_id)

                    synced += 1
                    if merged_into:
                        logger.info(
                            "Contact sync: synced '%s' → merged into '%s'",
                            full_name, merged_into
                        )

                except Exception as e:
                    logger.error("Failed to upsert contact '%s': %s", full_name, e)
                    errors += 1

    stats = {
        "synced": synced,
        "skipped": skipped,
        "errors": errors,
        "auto_merged": auto_merged,
        "suggestions": len(suggestions),
    }
    logger.info("Contact sync complete: %s", stats)
    if suggestions:
        logger.info("Merge suggestions for review: %d", len(suggestions))
        for s in suggestions[:5]:  # Log first 5
            logger.debug(
                "  - '%s' (~= '%s' at %.0f%%)",
                s["google_name"], s["existing_person"], s["confidence"]
            )

    await log_activity(
        activity_type="contacts_synced",
        entity_type="system",
        entity_id="google_contacts",
        description=f"Synced {stats['synced']} contacts from Google",
        metadata={
            "synced": stats['synced'],
            "skipped": stats['skipped'],
            "errors": stats['errors'],
            "auto_merged": stats['auto_merged'],
        },
        user_id="nolan",
    )

    return stats


@tool
async def sync_contacts_now() -> str:
    """Manually sync Google Contacts into the people database. Use this when
    the user asks to sync, import, or refresh their contacts from Google.
    Runs automatically every day at 2 AM, but this triggers it on demand."""
    try:
        stats = await sync_google_contacts_to_people()
        return (
            f"Contact sync complete — {stats['synced']} synced, "
            f"{stats['skipped']} skipped (no name), {stats['errors']} errors."
        )
    except Exception as e:
        logger.error("On-demand contact sync failed: %s", e)
        return f"Contact sync failed: {e}"


def get_tools() -> list:
    """Return contact sync tools if OAuth2 credentials are configured."""
    if settings.google_oauth_token_json:
        return [sync_contacts_now]
    return []
