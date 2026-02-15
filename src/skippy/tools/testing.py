"""Testing tools for Skippy — run the project test suite and email results."""

import logging
import subprocess
from email.mime.text import MIMEText
import base64

from langchain_core.tools import tool

from skippy.tools.google_auth import get_google_user_service

logger = logging.getLogger("skippy")

RECIPIENT = "brown.nolan@gmail.com"


@tool
def run_test_suite() -> str:
    """Run the Skippy project test suite and email the results to Nolan.

    Executes pytest against the full test suite, then sends the output
    as an email. Use this when Nolan asks to run the tests.
    """
    # Run pytest and capture output
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "/app/tests/", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd="/app",
        )
        output = result.stdout + result.stderr
        passed = result.returncode == 0
    except subprocess.TimeoutExpired:
        output = "Test suite timed out after 120 seconds."
        passed = False
    except Exception as e:
        output = f"Failed to run tests: {e}"
        passed = False

    status = "PASSED" if passed else "FAILED"

    # Email the results
    try:
        service = get_google_user_service("gmail", "v1")
        subject = f"Skippy Test Suite — {status}"
        body = f"Test suite result: {status}\n\n{output}"

        message = MIMEText(body)
        message["to"] = RECIPIENT
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

        logger.info("Test results emailed to %s — %s", RECIPIENT, status)
    except Exception as e:
        logger.error("Failed to email test results: %s", e)
        return f"Tests ran ({status}) but failed to email results: {e}\n\n{output}"

    return f"Test suite {status}. Results emailed to {RECIPIENT}.\n\n{output}"


def get_tools() -> list:
    """Return testing tools — always available."""
    return [run_test_suite]
