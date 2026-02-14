"""Google Contacts → People table sync for Skippy."""

import asyncio
import logging

import psycopg
from langchain_core.tools import tool

from skippy.config import settings
from skippy.tools.google_auth import get_google_user_service

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


async def sync_google_contacts_to_people() -> dict:
    """Fetch all Google Contacts and upsert into the people table.

    Returns dict with keys: synced, skipped, errors.
    """
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

    async with await psycopg.AsyncConnection.connect(
        settings.database_url, autocommit=True
    ) as conn:
        async with conn.cursor() as cur:
            for person in contacts:
                names = person.get("names", [])
                if not names:
                    skipped += 1
                    continue

                name = names[0].get("displayName", "").strip()
                if not name:
                    skipped += 1
                    continue

                emails = person.get("emailAddresses", [])
                phones = person.get("phoneNumbers", [])
                addresses = person.get("addresses", [])

                email = emails[0].get("value", "") if emails else ""
                phone = phones[0].get("value", "") if phones else ""
                address = addresses[0].get("formattedValue", "") if addresses else ""
                birthday = _extract_birthday(person.get("birthdays", []))
                notes = _extract_notes(person)

                try:
                    await cur.execute(
                        """
                        INSERT INTO people (user_id, name, relationship, birthday, address, phone, email, notes)
                        VALUES (%s, %s, NULL, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, LOWER(name))
                        DO UPDATE SET
                            birthday = COALESCE(NULLIF(EXCLUDED.birthday, ''), people.birthday),
                            address = COALESCE(NULLIF(EXCLUDED.address, ''), people.address),
                            phone = COALESCE(NULLIF(EXCLUDED.phone, ''), people.phone),
                            email = COALESCE(NULLIF(EXCLUDED.email, ''), people.email),
                            notes = COALESCE(NULLIF(EXCLUDED.notes, ''), people.notes),
                            updated_at = NOW();
                        """,
                        ("nolan", name, birthday or "", address or "",
                         phone or "", email or "", notes or ""),
                    )
                    synced += 1
                except Exception as e:
                    logger.error("Failed to upsert contact '%s': %s", name, e)
                    errors += 1

    stats = {"synced": synced, "skipped": skipped, "errors": errors}
    logger.info("Contact sync complete: %s", stats)
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
