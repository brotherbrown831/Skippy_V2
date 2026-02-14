"""Gmail tools for Skippy — read inbox, search, send, and reply to emails."""

import base64
import logging
from email.mime.text import MIMEText

from langchain_core.tools import tool

from skippy.config import settings
from skippy.tools.google_auth import get_google_user_service

logger = logging.getLogger("skippy")


def _get_gmail_service():
    return get_google_user_service("gmail", "v1")


def _parse_headers(headers: list[dict], *names: str) -> dict[str, str]:
    """Extract specific headers from a Gmail message header list."""
    result = {}
    lookup = {n.lower(): n for n in names}
    for h in headers:
        key = h["name"].lower()
        if key in lookup:
            result[lookup[key]] = h["value"]
    return result


def _decode_body(payload: dict) -> str:
    """Extract plain text body from a Gmail message payload."""
    # Simple single-part message
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    # Multipart — look for text/plain part
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        # Nested multipart
        if part.get("parts"):
            result = _decode_body(part)
            if result:
                return result

    return "(Could not extract text body)"


@tool
def check_inbox(max_results: int = 5) -> str:
    """Check for recent unread emails in the user's Gmail inbox. Use this when
    the user asks about new emails, unread messages, or what's in their inbox.

    Args:
        max_results: Maximum number of emails to return (default 5, max 20).
    """
    try:
        service = _get_gmail_service()
        max_results = min(max_results, 20)

        results = service.users().messages().list(
            userId="me",
            q="is:unread",
            maxResults=max_results,
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            return "No unread emails in your inbox."

        lines = []
        for msg_meta in messages:
            msg = service.users().messages().get(
                userId="me", id=msg_meta["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = _parse_headers(msg.get("payload", {}).get("headers", []),
                                     "From", "Subject", "Date")
            snippet = msg.get("snippet", "")
            lines.append(
                f"- From: {headers.get('From', '?')} | "
                f"Subject: {headers.get('Subject', '(no subject)')} | "
                f"Date: {headers.get('Date', '?')}\n"
                f"  Preview: {snippet}\n"
                f"  [ID: {msg_meta['id']}]"
            )

        return f"Unread emails ({len(messages)}):\n\n" + "\n\n".join(lines)
    except Exception as e:
        logger.error("Failed to check inbox: %s", e)
        return f"Error checking inbox: {e}"


@tool
def search_emails(query: str, max_results: int = 5) -> str:
    """Search Gmail using Gmail query syntax. Use this when the user asks to
    find a specific email, emails from someone, or about a topic.

    Examples of query syntax:
    - from:john@example.com
    - subject:meeting
    - has:attachment
    - after:2024/01/01 before:2024/12/31
    - label:important

    Args:
        query: Gmail search query string.
        max_results: Maximum number of results (default 5, max 20).
    """
    try:
        service = _get_gmail_service()
        max_results = min(max_results, 20)

        results = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results,
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            return f'No emails matching "{query}".'

        lines = []
        for msg_meta in messages:
            msg = service.users().messages().get(
                userId="me", id=msg_meta["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = _parse_headers(msg.get("payload", {}).get("headers", []),
                                     "From", "Subject", "Date")
            snippet = msg.get("snippet", "")
            lines.append(
                f"- From: {headers.get('From', '?')} | "
                f"Subject: {headers.get('Subject', '(no subject)')} | "
                f"Date: {headers.get('Date', '?')}\n"
                f"  Preview: {snippet}\n"
                f"  [ID: {msg_meta['id']}]"
            )

        return f'Emails matching "{query}" ({len(messages)}):\n\n' + "\n\n".join(lines)
    except Exception as e:
        logger.error("Failed to search emails: %s", e)
        return f"Error searching emails: {e}"


@tool
def read_email(email_id: str) -> str:
    """Read the full content of a specific email by its ID. Use this after
    check_inbox or search_emails to get the full text of an email the user
    wants to read.

    Args:
        email_id: The Gmail message ID (from inbox check or search results).
    """
    try:
        service = _get_gmail_service()

        msg = service.users().messages().get(
            userId="me", id=email_id, format="full",
        ).execute()

        payload = msg.get("payload", {})
        headers = _parse_headers(payload.get("headers", []),
                                 "From", "To", "Subject", "Date")
        body = _decode_body(payload)

        # Truncate very long emails
        if len(body) > 3000:
            body = body[:3000] + "\n\n... (truncated, email is very long)"

        return (
            f"From: {headers.get('From', '?')}\n"
            f"To: {headers.get('To', '?')}\n"
            f"Subject: {headers.get('Subject', '(no subject)')}\n"
            f"Date: {headers.get('Date', '?')}\n"
            f"\n{body}"
        )
    except Exception as e:
        logger.error("Failed to read email %s: %s", email_id, e)
        return f"Error reading email: {e}"


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send a new email from the user's Gmail account. Use this when the user
    asks you to send, compose, or write an email to someone.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body text (plain text).
    """
    try:
        service = _get_gmail_service()

        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        sent = service.users().messages().send(
            userId="me",
            body={"raw": raw},
        ).execute()

        logger.info("Email sent: id=%s, to=%s, subject='%s'", sent["id"], to, subject)
        return f"Email sent to {to} with subject '{subject}'."
    except Exception as e:
        logger.error("Failed to send email: %s", e)
        return f"Error sending email: {e}"


@tool
def reply_to_email(email_id: str, body: str) -> str:
    """Reply to an existing email thread. Use this when the user wants to
    respond to an email they've read.

    Args:
        email_id: The Gmail message ID to reply to.
        body: The reply text (plain text).
    """
    try:
        service = _get_gmail_service()

        # Get the original message for headers
        original = service.users().messages().get(
            userId="me", id=email_id, format="metadata",
            metadataHeaders=["From", "Subject", "Message-ID"],
        ).execute()

        orig_headers = _parse_headers(
            original.get("payload", {}).get("headers", []),
            "From", "Subject", "Message-ID",
        )
        thread_id = original.get("threadId")
        reply_to = orig_headers.get("From", "")
        subject = orig_headers.get("Subject", "")
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        message = MIMEText(body)
        message["to"] = reply_to
        message["subject"] = subject
        message["In-Reply-To"] = orig_headers.get("Message-ID", "")
        message["References"] = orig_headers.get("Message-ID", "")
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        sent = service.users().messages().send(
            userId="me",
            body={"raw": raw, "threadId": thread_id},
        ).execute()

        logger.info("Reply sent: id=%s, to=%s, thread=%s", sent["id"], reply_to, thread_id)
        return f"Reply sent to {reply_to} in thread '{subject}'."
    except Exception as e:
        logger.error("Failed to reply to email %s: %s", email_id, e)
        return f"Error replying to email: {e}"


def get_tools() -> list:
    """Return Gmail tools if OAuth2 credentials are configured."""
    if settings.google_oauth_token_json:
        return [check_inbox, search_emails, read_email, send_email, reply_to_email]
    return []
