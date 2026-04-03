# tools/email_tool.py
import os
import base64
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Type, Optional, List

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

_GMAIL_CREDENTIALS_PATH = os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
_GMAIL_TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH", "token.json")
_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class EmailInput(BaseModel):
    to_email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Plain-text email body")
    attachment_paths: Optional[List[str]] = Field(default=None, description="File paths to attach")


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
    """Sends email with optional file attachments via SMTP."""

    name: str = "Email Sender"
    description: str = (
        "Sends an email with optional file attachments via SMTP. "
        "Input: to_email, subject, body, attachment_paths (list of file paths). "
        "Reads SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD from environment."
    )
    args_schema: Type[BaseModel] = EmailInput

    def _run(self, to_email: str, subject: str, body: str,
             attachment_paths: List[str] = None) -> str:
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")

        if not smtp_user or not smtp_password:
            return "EMAIL_ERROR: SMTP credentials not configured. Set SMTP_USER and SMTP_PASSWORD."

        paths = _normalise_paths(attachment_paths)
        err = _validate_attachments(paths)
        if err:
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

        try:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
            server.quit()
            names = [Path(p).name for p in paths]
            return f"EMAIL_SENT: Delivered to {to_email}. Attachments: {', '.join(names) or 'none'}."
        except smtplib.SMTPAuthenticationError:
            return "EMAIL_ERROR: SMTP authentication failed."
        except smtplib.SMTPRecipientsRefused:
            return f"EMAIL_ERROR: Recipient '{to_email}' refused by server."
        except smtplib.SMTPException as e:
            return f"EMAIL_ERROR: SMTP error — {e}"
        except Exception as e:
            return f"EMAIL_ERROR: {e}"


def _get_gmail_service():
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError(
            f"Google auth packages required: pip install google-auth google-auth-oauthlib "
            f"google-auth-httplib2 google-api-python-client. Original: {e}"
        )

    creds = None
    if Path(_GMAIL_TOKEN_PATH).exists():
        creds = Credentials.from_authorized_user_file(_GMAIL_TOKEN_PATH, _GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        else:
            if not Path(_GMAIL_CREDENTIALS_PATH).exists():
                raise FileNotFoundError(
                    f"Gmail credentials not found at '{_GMAIL_CREDENTIALS_PATH}'. "
                    "Download from Google Cloud Console and set GMAIL_CREDENTIALS_PATH."
                )
            flow = InstalledAppFlow.from_client_secrets_file(_GMAIL_CREDENTIALS_PATH, _GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(_GMAIL_TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

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
    """Sends email via Gmail REST API using OAuth 2.0 (no app password required)."""

    name: str = "Gmail Sender"
    description: str = (
        "Sends an email with optional file attachments via the Gmail REST API using OAuth 2.0. "
        "Preferred over SMTP — no app passwords required. "
        "Input: to_email, subject, body, attachment_paths (list of file paths). "
        "Requires credentials.json on first run (GMAIL_CREDENTIALS_PATH env var)."
    )
    args_schema: Type[BaseModel] = EmailInput

    def _run(self, to_email: str, subject: str, body: str,
             attachment_paths: List[str] = None) -> str:
        paths = _normalise_paths(attachment_paths)
        err = _validate_attachments(paths)
        if err:
            return err

        try:
            service = _get_gmail_service()
            profile = service.users().getProfile(userId="me").execute()
            sender = profile.get("emailAddress", "me")
            raw_msg = _build_raw_gmail_message(sender, to_email, subject, body, paths or None)
            sent = service.users().messages().send(userId="me", body=raw_msg).execute()
            msg_id = sent.get("id", "unknown")
            names = [Path(p).name for p in paths]
            return (
                f"GMAIL_SENT: Delivered to {to_email}. Message ID: {msg_id}. "
                f"Attachments: {', '.join(names) or 'none'}."
            )
        except FileNotFoundError as e:
            return f"GMAIL_ERROR: {e}"
        except RuntimeError as e:
            return f"GMAIL_ERROR: {e}"
        except Exception as e:
            err_str = str(e)
            if "invalid_grant" in err_str:
                return f"GMAIL_ERROR: Token invalid. Delete '{_GMAIL_TOKEN_PATH}' and re-run."
            if "insufficient authentication scopes" in err_str.lower():
                return f"GMAIL_ERROR: Insufficient scopes. Delete '{_GMAIL_TOKEN_PATH}' and re-authenticate."
            return f"GMAIL_ERROR: {err_str}"


gmail_send_tool = GmailSendTool()
