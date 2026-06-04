"""
Email Skill for Shweta AI Desktop Assistant.
Sends professional emails via Gmail API on user's behalf.

Features:
- AI drafts professional email based on user's reason
- Sends via Gmail API (OAuth, free)
- Supports contacts: HR, Manager, Team, custom email
- First run: browser login for Google OAuth (one-time)

Setup:
- pip install google-auth google-auth-oauthlib google-api-python-client
- Place credentials.json in project root (from Google Cloud Console)
- Add EMAIL_CONTACTS in .env or contacts below
"""

import base64
import logging
import os
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, Optional

from config import PROJECT_ROOT, GROQ_API_KEY, GEMINI_API_KEY

logger = logging.getLogger(__name__)

# --- Credentials & Token paths ---
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / ".gmail_token.json"

# --- Email contacts (add your contacts here) ---
EMAIL_CONTACTS = {
    "hr": os.environ.get("EMAIL_HR", ""),
    "manager": os.environ.get("EMAIL_MANAGER", ""),
    "team": os.environ.get("EMAIL_TEAM", ""),
    "boss": os.environ.get("EMAIL_MANAGER", ""),
}

# --- User info for email signature ---
USER_NAME = os.environ.get("USER_FULL_NAME", "")
USER_DESIGNATION = os.environ.get("USER_DESIGNATION", "")

# --- Gmail API scopes ---
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# --- Gmail service (lazy init) ---
_gmail_service = None


def _get_gmail_service():
    """Get authenticated Gmail API service (lazy, one-time OAuth)."""
    global _gmail_service

    if _gmail_service is not None:
        return _gmail_service

    if not CREDENTIALS_FILE.exists():
        logger.error("credentials.json not found! Gmail API won't work.")
        return None

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None

        # Load saved token
        if TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

        # If no valid creds, do OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE), SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save token for next time
            TOKEN_FILE.write_text(creds.to_json())

        _gmail_service = build("gmail", "v1", credentials=creds)
        logger.info("[Email] Gmail API connected!")
        return _gmail_service

    except Exception as e:
        logger.error(f"[Email] Gmail init failed: {e}")
        return None


def _draft_email(to_name: str, reason: str, email_type: str = "leave") -> Dict[str, str]:
    """
    Use AI to draft a professional email.
    Returns: {"subject": "...", "body": "..."}
    """
    prompt = f"""Write a short professional email in English.
To: {to_name}
From: {USER_NAME or 'Employee'}
Reason: {reason}
Type: {email_type}

Rules:
- Subject line (short, professional)
- Body: 3-4 lines max, polite, formal
- Sign off with name: {USER_NAME or 'Employee'}
- If designation available: {USER_DESIGNATION or ''}

Output format (JSON only):
{{"subject": "...", "body": "..."}}"""

    # Try Groq
    try:
        if GROQ_API_KEY:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY, max_retries=0)
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
            )
            text = response.choices[0].message.content.strip()
            import json
            if text.startswith("```"):
                text = "\n".join(text.split("\n")[1:-1])
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                return json.loads(text[start:end+1])
    except Exception as e:
        logger.warning(f"Groq draft failed: {e}")

    # Try Gemini
    try:
        if GEMINI_API_KEY:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=200)
            )
            text = response.text.strip()
            import json
            if text.startswith("```"):
                text = "\n".join(text.split("\n")[1:-1])
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                return json.loads(text[start:end+1])
    except Exception as e:
        logger.warning(f"Gemini draft failed: {e}")

    # Fallback: simple template
    return {
        "subject": f"Leave Request - {reason[:30]}",
        "body": f"Dear {to_name},\n\nI am writing to inform you that I will not be able to come to work today due to {reason}. I request you to kindly grant me leave for today.\n\nThank you for your understanding.\n\nBest regards,\n{USER_NAME or 'Employee'}"
    }


def send_email(to_email: str, reason: str, to_name: str = "HR") -> Dict[str, str]:
    """
    Draft and send a professional email.
    Supports multiple recipients (comma-separated).

    Args:
        to_email: Recipient email(s) — comma separated for multiple.
        reason: Reason/context for the email (AI will draft professional content).
        to_name: Recipient name (for greeting).
    """
    try:
        # Resolve contact name to email
        if not to_email or "@" not in to_email:
            # Check contacts
            contact_email = EMAIL_CONTACTS.get(to_email.lower().strip(), "")
            if contact_email and "@" in contact_email:
                to_name = to_email.strip().title()
                to_email = contact_email
            else:
                return {"status": "error", "message": f"Email address nahi mila '{to_email}' ke liye. .env mein EMAIL_HR/EMAIL_MANAGER set karo."}

        # Draft email using AI
        draft = _draft_email(to_name, reason)
        subject = draft.get("subject", "Request")
        body = draft.get("body", reason)

        # Get Gmail service
        service = _get_gmail_service()
        if not service:
            return {"status": "error", "message": "Gmail API connect nahi ho paya. credentials.json check karo."}

        # Handle multiple recipients (comma-separated)
        recipients = [e.strip() for e in to_email.split(",") if e.strip() and "@" in e.strip()]
        if not recipients:
            return {"status": "error", "message": "Koi valid email address nahi mila."}

        # Create email message with all recipients
        message = MIMEText(body)
        message["to"] = ", ".join(recipients)
        message["subject"] = subject

        # Encode and send
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_result = service.users().messages().send(
            userId="me",
            body={"raw": raw}
        ).execute()

        count = len(recipients)
        logger.info(f"[Email] Sent to {count} recipients: {subject}")
        return {
            "status": "success",
            "message": f"Email bhej diya {count} logon ko ({to_name})! Subject: {subject}"
        }

    except Exception as e:
        logger.error(f"[Email] Send failed: {e}")
        return {"status": "error", "message": f"Email send nahi ho paya: {str(e)}"}


def send_email_to_contact(contact: str, reason: str) -> Dict[str, str]:
    """
    Send email to a named contact (hr, manager, team, boss).
    AI drafts professional email based on reason.
    """
    contact_lower = contact.lower().strip()
    email = EMAIL_CONTACTS.get(contact_lower, "")

    if not email:
        return {"status": "error", "message": f"'{contact}' ka email set nahi hai. .env mein EMAIL_HR, EMAIL_MANAGER add karo."}

    return send_email(to_email=email, reason=reason, to_name=contact.title())
