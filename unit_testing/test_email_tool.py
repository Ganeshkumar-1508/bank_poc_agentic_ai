#!/usr/bin/env python3
"""
Test script for EmailSenderTool functionality.

This script tests the email sending functionality by:
1. Loading environment variables from .env
2. Verifying SMTP credentials are configured correctly
3. Testing connection to smtp.gmail.com:587
4. Sending a test email with subject "Email Tool Test"
5. Logging all steps and results
"""

import os
import sys
import logging
import smtplib
import time
import base64
from pathlib import Path
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, List

# Add the Test directory to the path so we can import the email_tool
sys.path.insert(0, str(Path(__file__).parent / "tools"))

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path(__file__).parent / "test_email_tool.log"),
    ],
)
logger = logging.getLogger(__name__)


# Inline implementation of EmailSenderTool to avoid crewai dependency
class EmailSenderTool:
    """Sends email with optional file attachments via SMTP."""

    def __init__(self):
        self.name = "Email Sender"
        self._MAX_RETRIES = 3
        self._BASE_BACKOFF_SECONDS = 2

    def _normalise_paths(self, attachment_paths) -> List[str]:
        if isinstance(attachment_paths, str):
            return [attachment_paths] if attachment_paths.strip() else []
        return attachment_paths or []

    def _validate_attachments(self, paths: List[str]) -> Optional[str]:
        missing = [p for p in paths if not Path(p.strip()).exists()]
        if missing:
            return (
                "EMAIL_ERROR: Attachment path(s) not found:\n"
                + "\n".join(f" - {m}" for m in missing)
                + "\nEmail was NOT sent."
            )
        return None

    def run(
        self, to_email: str, subject: str, body: str, attachment_paths: List[str] = None
    ) -> str:
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")

        # Validate credentials before attempting to send
        if not smtp_user:
            error_msg = (
                "EMAIL_ERROR: SMTP_USER not configured. Set SMTP_USER in environment."
            )
            logger.error(error_msg)
            return error_msg
        if not smtp_password:
            error_msg = "EMAIL_ERROR: SMTP_PASSWORD not configured. Set SMTP_PASSWORD in environment."
            logger.error(error_msg)
            return error_msg

        paths = self._normalise_paths(attachment_paths)
        err = self._validate_attachments(paths)
        if err:
            logger.error(f"Attachment validation failed: {err}")
            return err

        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        for path in paths:
            p = Path(path.strip())
            with open(p, "rb") as f:
                part = MIMEApplication(f.read(), Name=p.name)
                part["Content-Disposition"] = f'attachment; filename="{p.name}"'
                msg.attach(part)

        # Retry logic with exponential backoff
        last_error = None
        for attempt in range(self._MAX_RETRIES):
            try:
                logger.info(
                    f"Attempting SMTP send (attempt {attempt + 1}/{self._MAX_RETRIES}) to {to_email}"
                )
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_user, to_email, msg.as_string())
                server.quit()
                names = [Path(p).name for p in paths]
                success_msg = f"EMAIL_SENT: Delivered to {to_email}. Attachments: {', '.join(names) or 'none'}."
                logger.info(success_msg)
                return success_msg
            except smtplib.SMTPAuthenticationError as e:
                last_error = e
                logger.error(
                    f"SMTP Authentication failed (attempt {attempt + 1}/{self._MAX_RETRIES}): {e}"
                )
                # Don't retry on auth errors - they won't succeed
                break
            except smtplib.SMTPRecipientsRefused as e:
                last_error = e
                logger.error(
                    f"Recipient '{to_email}' refused by server (attempt {attempt + 1}/{self._MAX_RETRIES}): {e}"
                )
                if attempt < self._MAX_RETRIES - 1:
                    time.sleep(self._BASE_BACKOFF_SECONDS * (2**attempt))
                    continue
            except smtplib.SMTPException as e:
                last_error = e
                logger.warning(
                    f"SMTP error (attempt {attempt + 1}/{self._MAX_RETRIES}): {e}"
                )
                if attempt < self._MAX_RETRIES - 1:
                    wait_time = self._BASE_BACKOFF_SECONDS * (2**attempt)
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Unexpected error (attempt {attempt + 1}/{self._MAX_RETRIES}): {e}"
                )
                if attempt < self._MAX_RETRIES - 1:
                    wait_time = self._BASE_BACKOFF_SECONDS * (2**attempt)
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue

        # All retries exhausted or non-retryable error
        error_details = str(last_error) if last_error else "Unknown error"
        if isinstance(last_error, smtplib.SMTPAuthenticationError):
            error_msg = f"EMAIL_ERROR: SMTP authentication failed. Check SMTP_USER and SMTP_PASSWORD. Details: {error_details}"
        elif isinstance(last_error, smtplib.SMTPRecipientsRefused):
            error_msg = f"EMAIL_ERROR: Recipient '{to_email}' refused by server. Details: {error_details}"
        else:
            error_msg = f"EMAIL_ERROR: Failed to send email after {self._MAX_RETRIES} attempts. Last error: {error_details}"

        logger.error(error_msg)
        return error_msg


def test_environment_variables():
    """Test that all required environment variables are loaded."""
    logger.info("=" * 60)
    logger.info("STEP 1: Testing Environment Variables")
    logger.info("=" * 60)

    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")

    results = {
        "SMTP_SERVER": smtp_server,
        "SMTP_PORT": smtp_port,
        "SMTP_USER": smtp_user,
        "SMTP_PASSWORD configured": smtp_password is not None
        and len(smtp_password) > 0,
    }

    all_present = all([smtp_server, smtp_port, smtp_user, smtp_password])

    if all_present:
        logger.info("✓ All environment variables loaded successfully")
        logger.info(f"  SMTP_SERVER: {smtp_server}")
        logger.info(f"  SMTP_PORT: {smtp_port}")
        logger.info(f"  SMTP_USER: {smtp_user}")
        logger.info(f"  SMTP_PASSWORD: {'*' * len(smtp_password)}")
    else:
        logger.error("✗ Missing environment variables:")
        for key, value in results.items():
            status = "✓" if value else "✗"
            logger.error(f"  {status} {key}: {value}")

    return all_present


def test_smtp_connection():
    """Test SMTP connection to smtp.gmail.com:587."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("STEP 2: Testing SMTP Connection")
    logger.info("=" * 60)

    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))

    try:
        logger.info(f"Connecting to {smtp_server}:{smtp_port}...")
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        logger.info("✓ Connection successful")

        logger.info("Starting TLS...")
        server.starttls()
        logger.info("✓ TLS started successfully")

        server.quit()
        logger.info("✓ Connection test passed")
        return True

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"✗ SMTP Authentication failed: {e}")
        return False
    except smtplib.SMTPConnectError as e:
        logger.error(f"✗ Failed to connect to SMTP server: {e}")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"✗ SMTP error: {e}")
        return False
    except Exception as e:
        logger.error(f"✗ Unexpected error during connection test: {e}")
        return False


def test_authentication():
    """Test SMTP authentication with configured credentials."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("STEP 3: Testing SMTP Authentication")
    logger.info("=" * 60)

    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")

    if not smtp_user or not smtp_password:
        logger.error("✗ Cannot test authentication: Missing credentials")
        return False

    try:
        logger.info(f"Authenticating as {smtp_user}...")
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.starttls()
        server.login(smtp_user, smtp_password)
        logger.info("✓ Authentication successful")
        server.quit()
        return True

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"✗ Authentication failed: {e}")
        logger.error("  Please check SMTP_USER and SMTP_PASSWORD in .env")
        return False
    except Exception as e:
        logger.error(f"✗ Error during authentication: {e}")
        return False


def test_email_send(recipient_email: str):
    """Test sending an email using the EmailSenderTool."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("STEP 4: Testing Email Send via EmailSenderTool")
    logger.info("=" * 60)

    # Create the EmailSenderTool instance
    email_tool = EmailSenderTool()

    # Prepare test email content
    to_email = recipient_email
    subject = "Email Tool Test"
    body = """This is a test email sent from the EmailSenderTool test script.

If you receive this email, the email functionality is working correctly.

Test Details:
- Timestamp: This email was sent during automated testing
- Tool: EmailSenderTool from bank_poc_agentic_ai project
- Status: SUCCESS

This is an automated test message. Please do not reply.
"""

    logger.info(f"Sending test email to: {to_email}")
    logger.info(f"Subject: {subject}")
    logger.info("Body: (see below)")
    logger.info("-" * 40)
    logger.info(body)
    logger.info("-" * 40)

    try:
        # Send the email using the tool
        result = email_tool.run(
            to_email=to_email, subject=subject, body=body, attachment_paths=[]
        )

        logger.info("")
        logger.info("=" * 60)
        logger.info("STEP 5: Test Results")
        logger.info("=" * 60)

        if result.startswith("EMAIL_SENT"):
            logger.info("✓ Email sent successfully!")
            logger.info(f"  Result: {result}")
            return True
        elif result.startswith("EMAIL_ERROR"):
            logger.error("✗ Failed to send email")
            logger.error(f"  Error: {result}")
            return False
        else:
            logger.warning(f"Unexpected result: {result}")
            return False

    except Exception as e:
        logger.error(f"✗ Exception during email send: {e}")
        logger.error("  Full traceback:")
        import traceback

        logger.error(traceback.format_exc())
        return False


def main():
    """Main test function."""
    logger.info("")
    logger.info("#" * 60)
    logger.info("# EmailSenderTool Test Script")
    logger.info("#" * 60)
    logger.info("")

    # Test 1: Environment variables
    if not test_environment_variables():
        logger.error("")
        logger.error("=" * 60)
        logger.error("TEST FAILED: Environment variables not configured correctly")
        logger.error("=" * 60)
        return False

    # Test 2: SMTP connection
    if not test_smtp_connection():
        logger.error("")
        logger.error("=" * 60)
        logger.error("TEST FAILED: SMTP connection test failed")
        logger.error("=" * 60)
        return False

    # Test 3: Authentication
    if not test_authentication():
        logger.error("")
        logger.error("=" * 60)
        logger.error("TEST FAILED: SMTP authentication test failed")
        logger.error("=" * 60)
        return False

    # Test 4: Send email
    # Use self-send to ashwinpremnath123@gmail.com as the recipient
    recipient = os.getenv("SMTP_USER", "ashwinpremnath123@gmail.com")
    success = test_email_send(recipient)

    # Final summary
    logger.info("")
    logger.info("#" * 60)
    logger.info("# TEST SUMMARY")
    logger.info("#" * 60)

    if success:
        logger.info("✓ ALL TESTS PASSED")
        logger.info("  The EmailSenderTool is working correctly.")
        logger.info(f"  Test email sent to: {recipient}")
    else:
        logger.error("✗ TESTS FAILED")
        logger.error("  Please review the error messages above.")
        logger.error("  Check SMTP configuration in .env file.")

    logger.info("")
    logger.info("Test log saved to: Test/test_email_tool.log")

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
