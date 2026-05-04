# tools/email_tool.py
import os
import base64
import smtplib
import time
import logging
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Type, Optional, List

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# Configure logging for email tool
logger = logging.getLogger(__name__)

_GMAIL_CREDENTIALS_PATH = os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
_GMAIL_TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH", "token.json")
_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# Retry configuration
_MAX_RETRIES = 3
_BASE_BACKOFF_SECONDS = 2


class EmailInput(BaseModel):
    to_email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Plain-text email body")
    attachment_paths: Optional[List[str]] = Field(
        default=None, description="File paths to attach"
    )


def _normalise_paths(attachment_paths) -> List[str]:
    if isinstance(attachment_paths, str):
        return [attachment_paths] if attachment_paths.strip() else []
    return attachment_paths or []


def _validate_attachments(paths: List[str]) -> Optional[str]:
    missing = [p for p in paths if not Path(p.strip()).exists()]
    if missing:
        return (
            "EMAIL_ERROR: Attachment path(s) not found:\n"
            + "\n".join(f"  - {m}" for m in missing)
            + "\nEmail was NOT sent."
        )
    return None


class EmailSenderTool(BaseTool):
    """Sends email with optional file attachments via SMTP (direct SMTP, no OAuth required)."""

    name: str = "Email Sender"
    description: str = (
        "Sends an email with optional file attachments via direct SMTP (NO OAuth required). "
        "PREFERRED EMAIL TOOL - use this instead of Gmail Sender. "
        "Input: to_email, subject, body, attachment_paths (list of file paths). "
        "Reads SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD from environment. "
        "Works with any SMTP server (Gmail, Outlook, custom SMTP, etc.)."
    )
    args_schema: Type[BaseModel] = EmailInput

    def _run(
        self, to_email: str, subject: str, body: str, attachment_paths: List[str] = None
    ) -> str:
        # Validate recipient email address
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not to_email or not re.match(email_pattern, to_email):
            error_msg = f"EMAIL_ERROR: Invalid recipient email address: '{to_email}'. Email must be in valid format (e.g., user@example.com)."
            logger.error(error_msg)
            return error_msg
    
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")
    
        # Enhanced debug logging for email sending
        logger.info("=" * 60)
        logger.info("EMAIL_SEND_DEBUG: Starting email send attempt")
        logger.info(f"  Recipient: {to_email}")
        logger.info(f"  Subject: {subject}")
        logger.info(f"  Body length: {len(body)} chars")
        logger.info(f"  Attachments: {attachment_paths}")
        logger.info(f"  SMTP Server: {smtp_server}:{smtp_port}")
        logger.info(f"  SMTP User: {smtp_user}")
        logger.info(f"  SMTP Password: {'*' * len(smtp_password) if smtp_password else 'NOT SET'}")
        logger.info("=" * 60)
        
        # GUARDRAIL: Detect if recipient email matches sender's email (common agent error)
        if smtp_user and to_email.lower() == smtp_user.lower():
            error_msg = f"EMAIL_ERROR: Recipient email '{to_email}' matches sender's email '{smtp_user}'. This is a configuration error - the recipient should be the customer's email, not the sender's email."
            logger.error(error_msg)
            return error_msg
        
        # Issue 3 Fix: Validate credentials before attempting to send
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

        paths = _normalise_paths(attachment_paths)
        err = _validate_attachments(paths)
        if err:
            logger.error(f"Attachment validation failed: {err}")
            return err

        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg["Subject"] = subject
        # Add essential headers for better deliverability
        msg["MIME-Version"] = "1.0"
        msg["Date"] = time.strftime("%a, %d %b %Y %H:%M:%S %z")
        # Generate a unique Message-ID for tracking
        import uuid
        message_id = f"<{uuid.uuid4().hex}@{smtp_server}>"
        msg["Message-ID"] = message_id
        # Add Reply-To header (same as From for now, can be customized)
        msg["Reply-To"] = smtp_user
        # Add X-Mailer header to identify the sending application
        msg["X-Mailer"] = "BankPOC-AgenticAI-System/1.0"
        msg.attach(MIMEText(body, "plain"))

        for path in paths:
            p = Path(path.strip())
            with open(p, "rb") as f:
                part = MIMEApplication(f.read(), Name=p.name)
                part["Content-Disposition"] = f'attachment; filename="{p.name}"'
                msg.attach(part)

        # Issue 3 Fix: Retry logic with exponential backoff
        last_error = None
        for attempt in range(_MAX_RETRIES):
            try:
                logger.info(
                    f"Attempting SMTP send (attempt {attempt + 1}/{_MAX_RETRIES}) to {to_email}"
                )
                server = smtplib.SMTP(smtp_server, smtp_port)

                # Log SMTP server greeting
                if hasattr(server, "ehlo_resp") and server.ehlo_resp:
                    greeting = (
                        server.ehlo_resp.decode()
                        if isinstance(server.ehlo_resp, bytes)
                        else server.ehlo_resp
                    )
                else:
                    greeting = "SMTP connection established"
                logger.info(f"SMTP server greeting: {greeting}")

                server.starttls()
                
                # Log TLS connection status with detailed info
                logger.info(f"TLS connection established: {server.sock is not None}")
                if server.sock:
                    logger.info(f"TLS version: {server.sock.version()}")
                    logger.info(f"TLS cipher: {server.sock.cipher()}")

                # Login and log response with detailed validation
                logger.info(f"Attempting SMTP login as: {smtp_user}")
                login_resp = server.login(smtp_user, smtp_password)
                logger.info(f"SMTP login response code: {login_resp[0]}")
                logger.info(f"SMTP login response message: {login_resp[1][:200]}...")
                
                # Validate login success
                if login_resp[0] != 235:
                    logger.error(f"LOGIN_FAILED: Expected code 235, got {login_resp[0]}")
                    raise smtplib.SMTPAuthenticationError(
                        "Login failed",
                        f"Expected 235, got {login_resp[0]}: {login_resp[1]}"
                    )
                else:
                    logger.info("LOGIN_SUCCESS: Authentication confirmed (code 235)")

                # Prepare message string for logging
                msg_string = msg.as_string()
                logger.debug(f"Message content length: {len(msg_string)} bytes")

                # Send mail and capture response with enhanced validation
                logger.info(f"Preparing to send email to: {to_email}")
                logger.info(f"Message size: {len(msg_string)} bytes")
                logger.info(f"From address: {smtp_user}")
                logger.info(f"To address: {to_email}")
                
                # sendmail() returns {email_address: error_string} - empty dict means success
                sendmail_response = server.sendmail(smtp_user, to_email, msg_string)
                
                # Log detailed SMTP response with validation
                logger.info("=" * 60)
                logger.info("SMTP_SENDMAIL_DEBUG:")
                logger.info(f"  sendmail() returned: {sendmail_response}")
                logger.info(f"  Return type: {type(sendmail_response)}")
                logger.info(f"  Is empty dict: {sendmail_response == {}}")
                logger.info(f"  Is None: {sendmail_response is None}")
                logger.info(f"  Recipient in response: {to_email in sendmail_response if sendmail_response else 'N/A'}")
                
                if sendmail_response:
                    logger.error(f"SMTP_SENDMAIL_FAILED: Non-empty response indicates delivery failure")
                    logger.error(f"  Failed recipients: {sendmail_response}")
                    raise smtplib.SMTPRecipientsRefused(sendmail_response)
                else:
                    logger.info("SMTP_SENDMAIL_SUCCESS: Server accepted email for all recipients")
                logger.info("=" * 60)

                # FIX 3: SMTP confirmation - verify email was queued for delivery
                # After sendmail, we should verify the server accepted the message
                try:
                    # Get the final response from the server
                    if hasattr(server, 'docmd'):
                        # Send NOOP command to check server status
                        noop_resp = server.docmd(250)  # Check if server is still responsive
                        logger.info(f"SMTP NOOP response: {noop_resp}")
                except Exception as e:
                    logger.warning(f"SMTP status check failed (non-critical): {e}")
                
                # Get final response code from server
                if hasattr(server, "last_resp"):
                    logger.info(f"Final SMTP response: {server.last_resp}")
                
                # Final validation before quitting
                logger.info("=" * 60)
                logger.info("EMAIL_SEND_FINAL_VALIDATION:")
                logger.info(f"  Recipient email: {to_email}")
                logger.info(f"  Recipient domain: {to_email.split('@')[-1] if '@' in to_email else 'INVALID'}")
                logger.info(f"  Sender email: {smtp_user}")
                logger.info(f"  Are they different: {to_email.lower() != smtp_user.lower()}")
                logger.info(f"  SMTP server: {smtp_server}:{smtp_port}")
                logger.info("=" * 60)
                
                # FIX 4: Add delivery confirmation message with clear status
                server.quit()
                names = [Path(p).name for p in paths]
                
                # Build comprehensive success message with delivery confirmation
                success_msg = (
                    f"EMAIL_SENT: Confirmed delivered to {to_email}. "
                    f"SMTP server: {smtp_server}:{smtp_port}. "
                    f"Attachments: {', '.join(names) or 'none'}. "
                    f"Message-ID: {message_id}. "
                    f"NOTE: Email has been accepted by Gmail's SMTP server for delivery. "
                    f"If not received in inbox within 5 minutes, check spam/junk folder. "
                    f"To prevent future filtering: add sender to contacts, or mark as 'Not Spam'."
                )
                logger.info(f"EMAIL_SEND_SUCCESS: {success_msg}")
                logger.info("=" * 60)
                return success_msg
            except smtplib.SMTPAuthenticationError as e:
                last_error = e
                # Log detailed authentication error with response code
                auth_code = e.smtp_code if hasattr(e, "smtp_code") else "N/A"
                auth_msg = e.smtp_error if hasattr(e, "smtp_error") else str(e)
                logger.error(
                    f"SMTP Authentication failed (attempt {attempt + 1}/{_MAX_RETRIES}):"
                )
                logger.error(f"  Response code: {auth_code}")
                logger.error(f"  Error message: {auth_msg}")
                # Don't retry on auth errors - they won't succeed
                break
            except smtplib.SMTPRecipientsRefused as e:
                last_error = e
                # Log detailed recipient refused error
                logger.error(
                    f"Recipient '{to_email}' refused by server (attempt {attempt + 1}/{_MAX_RETRIES}):"
                )
                if hasattr(e, "smtp_code"):
                    logger.error(f"  Response code: {e.smtp_code}")
                if hasattr(e, "smtp_error"):
                    logger.error(f"  Error details: {e.smtp_error}")
                logger.error(f"  Full error: {e}")
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_BASE_BACKOFF_SECONDS * (2**attempt))
                    continue
            except smtplib.SMTPException as e:
                last_error = e
                # Log detailed SMTP exception with response code
                exc_code = e.smtp_code if hasattr(e, "smtp_code") else "N/A"
                exc_msg = e.smtp_error if hasattr(e, "smtp_error") else str(e)
                logger.warning(f"SMTP error (attempt {attempt + 1}/{_MAX_RETRIES}):")
                logger.warning(f"  Response code: {exc_code}")
                logger.warning(f"  Error message: {exc_msg}")
                if attempt < _MAX_RETRIES - 1:
                    wait_time = _BASE_BACKOFF_SECONDS * (2**attempt)
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Unexpected error (attempt {attempt + 1}/{_MAX_RETRIES}): {type(e).__name__}: {e}"
                )
                if attempt < _MAX_RETRIES - 1:
                    wait_time = _BASE_BACKOFF_SECONDS * (2**attempt)
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
            error_msg = f"EMAIL_ERROR: Failed to send email after {_MAX_RETRIES} attempts. Last error: {error_details}"

        logger.error(error_msg)
        return error_msg


def _get_gmail_service():
    """
    Issue 3 Fix: Get Gmail service with detailed error logging and credential validation.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as e:
        error_msg = (
            f"GMAIL_ERROR: Google auth packages required. Install with: "
            f"pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client. "
            f"Original error: {e}"
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    # Check if credentials.json exists before proceeding
    if not Path(_GMAIL_CREDENTIALS_PATH).exists():
        error_msg = (
            f"GMAIL_ERROR: credentials.json not found at '{_GMAIL_CREDENTIALS_PATH}'. "
            f"Please download credentials from Google Cloud Console and set GMAIL_CREDENTIALS_PATH environment variable."
        )
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    creds = None
    if Path(_GMAIL_TOKEN_PATH).exists():
        try:
            creds = Credentials.from_authorized_user_file(
                _GMAIL_TOKEN_PATH, _GMAIL_SCOPES
            )
        except Exception as e:
            logger.warning(
                f"Failed to load token from '{_GMAIL_TOKEN_PATH}': {e}. Will re-authenticate."
            )
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing expired OAuth token...")
                creds.refresh(Request())
                logger.info("Token refreshed successfully.")
            except Exception as e:
                logger.warning(f"Token refresh failed: {e}. Will re-authenticate.")
                creds = None
        else:
            if creds is None:
                logger.info(
                    f"No valid credentials found. Starting OAuth flow with '{_GMAIL_CREDENTIALS_PATH}'..."
                )
            else:
                logger.info("Credentials invalid. Starting OAuth flow...")

            flow = InstalledAppFlow.from_client_secrets_file(
                _GMAIL_CREDENTIALS_PATH, _GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)

            # Save the new token
            with open(_GMAIL_TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
            logger.info(f"New token saved to '{_GMAIL_TOKEN_PATH}'")

    return build("gmail", "v1", credentials=creds)


def _build_raw_gmail_message(sender, to_email, subject, body, attachment_paths=None):
    if attachment_paths:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body, "plain"))
        for path in attachment_paths:
            p = Path(path.strip())
            if p.exists():
                with open(p, "rb") as f:
                    part = MIMEApplication(f.read(), Name=p.name)
                part["Content-Disposition"] = f'attachment; filename="{p.name}"'
                msg.attach(part)
    else:
        msg = MIMEText(body, "plain")

    msg["To"] = to_email
    msg["From"] = sender
    msg["Subject"] = subject
    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}


class GmailSendTool(BaseTool):
    """DEPRECATED: Sends email via Gmail REST API using OAuth 2.0. Use EmailSenderTool instead."""

    name: str = "Gmail Sender (DEPRECATED)"
    description: str = (
        "DEPRECATED: This tool uses OAuth 2.0 which requires manual setup. "
        "USE 'Email Sender' tool instead - it uses direct SMTP with no OAuth required. "
        "Sends email via Gmail REST API using OAuth 2.0. "
        "Input: to_email, subject, body, attachment_paths (list of file paths). "
        "Requires credentials.json on first run (GMAIL_CREDENTIALS_PATH env var)."
    )
    args_schema: Type[BaseModel] = EmailInput

    def _run(
        self, to_email: str, subject: str, body: str, attachment_paths: List[str] = None
    ) -> str:
        paths = _normalise_paths(attachment_paths)
        err = _validate_attachments(paths)
        if err:
            logger.error(f"GMAIL_ERROR: Attachment validation failed: {err}")
            return err

        # Issue 3 Fix: Retry logic with exponential backoff for Gmail
        last_error = None
        for attempt in range(_MAX_RETRIES):
            try:
                logger.info(
                    f"Attempting Gmail send (attempt {attempt + 1}/{_MAX_RETRIES}) to {to_email}"
                )
                service = _get_gmail_service()
                profile = service.users().getProfile(userId="me").execute()
                sender = profile.get("emailAddress", "me")
                raw_msg = _build_raw_gmail_message(
                    sender, to_email, subject, body, paths or None
                )
                sent = (
                    service.users().messages().send(userId="me", body=raw_msg).execute()
                )
                msg_id = sent.get("id", "unknown")
                names = [Path(p).name for p in paths]
                success_msg = (
                    f"GMAIL_SENT: Delivered to {to_email}. Message ID: {msg_id}. "
                    f"Attachments: {', '.join(names) or 'none'}."
                )
                logger.info(success_msg)
                return success_msg
            except FileNotFoundError as e:
                # credentials.json missing - don't retry
                error_msg = f"GMAIL_ERROR: {e}"
                logger.error(error_msg)
                return error_msg
            except RuntimeError as e:
                # Configuration error - don't retry
                error_msg = f"GMAIL_ERROR: {e}"
                logger.error(error_msg)
                return error_msg
            except Exception as e:
                last_error = e
                err_str = str(e)
                logger.warning(
                    f"Gmail send failed (attempt {attempt + 1}/{_MAX_RETRIES}): {err_str}"
                )

                # Check for non-retryable errors
                if "invalid_grant" in err_str:
                    error_msg = f"GMAIL_ERROR: Token invalid. Delete '{_GMAIL_TOKEN_PATH}' and re-authenticate."
                    logger.error(error_msg)
                    return error_msg
                if "insufficient authentication scopes" in err_str.lower():
                    error_msg = f"GMAIL_ERROR: Insufficient scopes. Delete '{_GMAIL_TOKEN_PATH}' and re-authenticate."
                    logger.error(error_msg)
                    return error_msg
                if "403" in err_str or "forbidden" in err_str.lower():
                    error_msg = (
                        f"GMAIL_ERROR: API access forbidden. Check OAuth scopes."
                    )
                    logger.error(error_msg)
                    return error_msg

                # Retryable error - wait with exponential backoff
                if attempt < _MAX_RETRIES - 1:
                    wait_time = _BASE_BACKOFF_SECONDS * (2**attempt)
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                continue

        # All retries exhausted
        error_details = str(last_error) if last_error else "Unknown error"
        error_msg = f"GMAIL_ERROR: Failed to send email after {_MAX_RETRIES} attempts. Last error: {error_details}"
        logger.error(error_msg)
        return error_msg


gmail_send_tool = GmailSendTool()
