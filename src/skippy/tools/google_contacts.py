"""Google Contacts tools for Skippy — search, view, create, and update contacts."""

import logging

from langchain_core.tools import tool

from skippy.config import settings
from skippy.tools.google_auth import get_google_user_service

logger = logging.getLogger("skippy")


def _get_people_service():
    return get_google_user_service("people", "v1")


def _format_contact(person: dict) -> str:
    """Format a Google Contact into a readable string."""
    names = person.get("names", [])
    name = names[0].get("displayName", "(no name)") if names else "(no name)"

    emails = person.get("emailAddresses", [])
    phones = person.get("phoneNumbers", [])
    addresses = person.get("addresses", [])
    orgs = person.get("organizations", [])
    bdays = person.get("birthdays", [])
    notes = person.get("biographies", [])

    resource = person.get("resourceName", "")
    lines = [f"**{name}** [resource: {resource}]"]

    for e in emails:
        lines.append(f"  Email: {e.get('value', '?')} ({e.get('type', '')})")
    for p in phones:
        lines.append(f"  Phone: {p.get('value', '?')} ({p.get('type', '')})")
    for a in addresses:
        lines.append(f"  Address: {a.get('formattedValue', '?')}")
    for o in orgs:
        title = o.get("title", "")
        company = o.get("name", "")
        if title and company:
            lines.append(f"  Work: {title} at {company}")
        elif company:
            lines.append(f"  Work: {company}")
    for b in bdays:
        date = b.get("date", {})
        bday_str = f"{date.get('month', '?')}/{date.get('day', '?')}"
        if date.get("year"):
            bday_str = f"{date['year']}-{bday_str}"
        lines.append(f"  Birthday: {bday_str}")
    for n in notes:
        lines.append(f"  Notes: {n.get('value', '')[:200]}")

    return "\n".join(lines)


@tool
def search_contacts(query: str) -> str:
    """Search Google Contacts by name, email, or phone number. Use this when
    the user asks to look up someone in their contacts or find a contact.

    Args:
        query: Search term (name, email, or phone number).
    """
    try:
        service = _get_people_service()

        results = service.people().searchContacts(
            query=query,
            readMask="names,emailAddresses,phoneNumbers,organizations,addresses,birthdays,biographies",
            pageSize=10,
        ).execute()

        contacts = results.get("results", [])
        if not contacts:
            return f'No contacts matching "{query}".'

        lines = []
        for result in contacts:
            person = result.get("person", {})
            lines.append(_format_contact(person))

        return f'Contacts matching "{query}" ({len(contacts)}):\n\n' + "\n\n".join(lines)
    except Exception as e:
        logger.error("Failed to search contacts: %s", e)
        return f"Error searching contacts: {e}"


@tool
def get_contact_details(resource_name: str) -> str:
    """Get full details of a specific Google Contact by resource name.
    Resource names look like 'people/c1234567890'. Use this after searching
    contacts to get complete information.

    Args:
        resource_name: The contact's resource name (e.g., 'people/c1234567890').
    """
    try:
        service = _get_people_service()

        person = service.people().get(
            resourceName=resource_name,
            personFields="names,emailAddresses,phoneNumbers,organizations,addresses,birthdays,biographies,urls",
        ).execute()

        return _format_contact(person)
    except Exception as e:
        logger.error("Failed to get contact %s: %s", resource_name, e)
        return f"Error getting contact: {e}"


@tool
def create_contact(
    name: str,
    email: str = "",
    phone: str = "",
    company: str = "",
    notes: str = "",
) -> str:
    """Create a new Google Contact. Use this when the user asks to add someone
    to their contacts.

    Args:
        name: The contact's full name (required).
        email: Email address.
        phone: Phone number.
        company: Company or organization name.
        notes: Additional notes about the contact.
    """
    try:
        service = _get_people_service()

        body: dict = {
            "names": [{"givenName": name}],
        }
        if email:
            body["emailAddresses"] = [{"value": email}]
        if phone:
            body["phoneNumbers"] = [{"value": phone}]
        if company:
            body["organizations"] = [{"name": company}]
        if notes:
            body["biographies"] = [{"value": notes, "contentType": "TEXT_PLAIN"}]

        result = service.people().createContact(body=body).execute()
        resource = result.get("resourceName", "unknown")
        logger.info("Contact created: %s (%s)", name, resource)
        return f"Contact '{name}' created successfully (resource: {resource})."
    except Exception as e:
        logger.error("Failed to create contact: %s", e)
        return f"Error creating contact: {e}"


@tool
def update_contact(
    resource_name: str,
    name: str = "",
    email: str = "",
    phone: str = "",
    company: str = "",
    notes: str = "",
) -> str:
    """Update an existing Google Contact. Use this when the user wants to
    change or add information to a contact. Only fields you provide will be
    updated — leave others empty to keep current values.

    Args:
        resource_name: The contact's resource name (e.g., 'people/c1234567890').
        name: New name (leave empty to keep current).
        email: New email (leave empty to keep current).
        phone: New phone (leave empty to keep current).
        company: New company (leave empty to keep current).
        notes: New notes (leave empty to keep current).
    """
    try:
        service = _get_people_service()

        # Fetch current contact to get etag and current data
        current = service.people().get(
            resourceName=resource_name,
            personFields="names,emailAddresses,phoneNumbers,organizations,biographies",
        ).execute()

        etag = current.get("etag")
        update_fields = []
        body: dict = {"etag": etag}

        if name:
            body["names"] = [{"givenName": name}]
            update_fields.append("names")
        if email:
            body["emailAddresses"] = [{"value": email}]
            update_fields.append("emailAddresses")
        if phone:
            body["phoneNumbers"] = [{"value": phone}]
            update_fields.append("phoneNumbers")
        if company:
            body["organizations"] = [{"name": company}]
            update_fields.append("organizations")
        if notes:
            body["biographies"] = [{"value": notes, "contentType": "TEXT_PLAIN"}]
            update_fields.append("biographies")

        if not update_fields:
            return "No fields to update — provide at least one field to change."

        result = service.people().updateContact(
            resourceName=resource_name,
            updatePersonFields=",".join(update_fields),
            body=body,
        ).execute()

        updated_name = name or (current.get("names", [{}])[0].get("displayName", resource_name))
        logger.info("Contact updated: %s", resource_name)
        return f"Contact '{updated_name}' updated successfully."
    except Exception as e:
        logger.error("Failed to update contact %s: %s", resource_name, e)
        return f"Error updating contact: {e}"


def get_tools() -> list:
    """Return Google Contacts tools if OAuth2 credentials are configured."""
    if settings.google_oauth_token_json:
        return [search_contacts, get_contact_details, create_contact, update_contact]
    return []
