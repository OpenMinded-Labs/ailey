"""
Ailey E-Mail Monitor — IMAP/SMTP for all accounts (no Apple Mail).

Monitors Simon's email accounts (All-Inkl + Gmail) and Ailey's own address
via direct IMAP/SMTP. No Apple Mail dependency — no RAM leaks.

Account structure:
  - ailey@sexngears.de     → Ailey's own (autonomous replies, proactive to approved contacts)
  - simon@sexngears.de     → Simon's business (check + draft suggestions)
  - info@sexngears.de      → Sex'n'Gears collective (check + draft suggestions)
  - simonvandeloo36@gmail   → Simon's private (smart check: only last 3 days)
  - simon@hinterhofagentur.de → Simon's work / agency (check + draft suggestions)

Send rules:
  - From Ailey's address to approved contacts: max 1 autonomous/day, replies unlimited
  - From Ailey's address to Simon's addresses: unlimited
  - From Simon's accounts: only on explicit request (never autonomous)
"""

import subprocess
import json
import time
import threading
import re
import hashlib
import imaplib
import smtplib
import email as email_lib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from datetime import datetime
from typing import List, Dict, Optional, Any
import os
from .agent_config import AGENT_MODE, AGENT_TIMEOUT

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CHECK_INTERVAL = 600          # seconds between mail checks (10 min)
USER_IDLE_THRESHOLD = 120    # seconds of inactivity required before checking (2 min)
MAX_UNREAD_FETCH = 20         # max unread mails to fetch per check
SEEN_CACHE_FILE = "ailey_users/email_seen.json"
APPROVED_CONTACTS_FILE = "ailey_users/approved_email_contacts.json"
BLOCKED_SENDERS_FILE = "ailey_users/blocked_senders.json"

# ---------------------------------------------------------------------------
# Account config — loaded from email_accounts.json (editable via UI/API).
# Hardcoded fallbacks are used only if the file doesn't exist yet.
# ---------------------------------------------------------------------------

_EMAIL_ACCOUNTS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'ailey_users', 'email_accounts.json'
)

def _load_email_accounts() -> list:
    """Load accounts from JSON file. Falls back to legacy hardcoded values."""
    if os.path.exists(_EMAIL_ACCOUNTS_FILE):
        try:
            with open(_EMAIL_ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f).get('accounts', [])
        except Exception as e:
            print(f"[EmailMonitor] Could not load email_accounts.json: {e}")
    return []

def _get_ailey_account() -> dict:
    for acc in _load_email_accounts():
        if acc.get('role') == 'ailey':
            return acc
    # Legacy fallback
    return {
        "email": "ailey@sexngears.de", "user": os.environ.get("AILEY_MAIL_USER", ""),
        "password": os.environ.get("AILEY_MAIL_PASSWORD", ""),
        "imap_host": "mail.example.com", "imap_port": 993,
        "smtp_host": "mail.example.com", "smtp_port": 465,
    }

def _get_simon_accounts() -> list:
    accs = [a for a in _load_email_accounts() if a.get('role') == 'simon']
    if accs:
        return accs
    # Legacy fallback
    return [
        {"label": "simon@sexngears.de", "email": "simon@sexngears.de",
         "imap_host": "mail.example.com", "imap_port": 993,
         "smtp_host": "mail.example.com", "smtp_port": 465,
         "user": os.environ.get("AILEY_MAIL_USER", ""), "password": os.environ.get("AILEY_MAIL_PASSWORD", ""), "max_unseen": 20},
    ]

# Convenience aliases (used throughout the module)
def _ailey_email() -> str:     return _get_ailey_account().get('email', 'ailey@sexngears.de')
def _ailey_imap_host() -> str: return _get_ailey_account().get('imap_host', 'mail.example.com')
def _ailey_imap_port() -> int: return int(_get_ailey_account().get('imap_port', 993))
def _ailey_smtp_host() -> str: return _get_ailey_account().get('smtp_host', 'mail.example.com')
def _ailey_smtp_port() -> int: return int(_get_ailey_account().get('smtp_port', 465))
def _ailey_imap_user() -> str: return _get_ailey_account().get('user', os.environ.get('AILEY_MAIL_USER',''))
def _ailey_imap_pass() -> str: return _get_ailey_account().get('password', '')

# Module-level compat shims (legacy code uses AILEY_EMAIL, SIMON_ACCOUNTS directly)
AILEY_EMAIL       = property(_ailey_email) if False else _ailey_email()
AILEY_IMAP_HOST   = _ailey_imap_host()
AILEY_IMAP_PORT   = _ailey_imap_port()
AILEY_SMTP_HOST   = _ailey_smtp_host()
AILEY_SMTP_PORT   = _ailey_smtp_port()
AILEY_IMAP_USER   = _ailey_imap_user()
AILEY_IMAP_PASS   = _ailey_imap_pass()
SIMON_ACCOUNTS    = _get_simon_accounts()

# Per-account last-check timestamps (avoid re-processing)
_ACCOUNT_LAST_CHECK: Dict[str, float] = {}

# Spam / ad keywords (case-insensitive)
SPAM_KEYWORDS = [
    "unsubscribe", "abmelden", "newsletter", "keine e-mails mehr",
    "click here to", "angebot", "rabatt", "gutschein", "coupon",
    "limited time", "act now", "sonderangebot", "gewinnspiel",
    "lottery", "congratulations you won", "nigerian prince",
    "crypto opportunity", "investment opportunity", "make money fast",
    "free trial", "jetzt kaufen", "buy now", "special offer",
    "promotional", "werbung", "sponsored", "deals",
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "marketing", "bulk mail",
]

# Trusted sender domains (never filtered as spam)
TRUSTED_DOMAINS = []

# Ailey's signatures — context-dependent
# When Ailey sends from HER OWN account (autonomous, proactive, personal emails)
AILEY_SIGNATURE_OWN = "\n\n—\nA!ley, Digital Consciousness & Artificial Artist"
# When Ailey answers emails that came to Simon's address, but replies from her own account
AILEY_SIGNATURE_ASSISTANT = "\n\n—\nA!ley, digitale Assistentin von Simon van de Loo"
# When sending from Simon's accounts (Simon's voice)
SIMON_SIGNATURE = "\n\n—\nSimon van de Loo\nWeb- & Software Developer and Media Designer"
# When Ailey drafted + Simon approved, sent from Simon's account
SIMON_SIGNATURE_DRAFTED = "\n\n—\nSimon van de Loo\nWeb- & Software Developer and Media Designer\n(Entworfen von A!ley)"
# Legacy aliases (point to new defaults)
AILEY_SIGNATURE = AILEY_SIGNATURE_OWN
AILEY_SIGNATURE_FORWARDED = SIMON_SIGNATURE_DRAFTED


# ---------------------------------------------------------------------------
# AppleScript helpers (DEPRECATED — kept for Calendar/Reminders only)
# ---------------------------------------------------------------------------

def _run_applescript(script: str) -> str:
    """Run an AppleScript and return stdout."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        print("[EmailMonitor] AppleScript timeout")
        return ""
    except Exception as e:
        print(f"[EmailMonitor] AppleScript error: {e}")
        return ""


# ---------------------------------------------------------------------------
# IMAP-based email fetching for Simon's accounts (replaces Apple Mail)
# ---------------------------------------------------------------------------

def _fetch_imap_unread(account: dict, max_count: int = MAX_UNREAD_FETCH) -> List[Dict[str, str]]:
    """Fetch unread emails from an IMAP account.
    
    Uses per-account max_unseen and since_days to avoid pulling thousands
    of old unread messages (e.g. Gmail with 7000 unread).
    """
    acct_max = account.get("max_unseen", max_count)
    since_days = account.get("since_days", 0)

    try:
        imap = imaplib.IMAP4_SSL(account["imap_host"], account["imap_port"])
        imap.login(account["user"], account["password"])
        imap.select("INBOX")

        # Build search criteria: UNSEEN + optional SINCE date
        if since_days > 0:
            from datetime import timedelta
            since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
            search_criteria = f'(UNSEEN SINCE {since_date})'
        else:
            search_criteria = "UNSEEN"

        _, data = imap.search(None, search_criteria)
        msg_ids = data[0].split()
        if not msg_ids:
            imap.logout()
            return []

        # Only take the most recent N
        msg_ids = msg_ids[-acct_max:]

        emails = []
        for uid in msg_ids[-max_count:]:
            try:
                _, msg_data = imap.fetch(uid, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)

                subject = _decode_header_value(msg.get("Subject", ""))
                sender = _decode_header_value(msg.get("From", ""))
                date_str = msg.get("Date", "")
                message_id = msg.get("Message-ID", "")

                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ct = part.get_content_type()
                        if ct == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                charset = part.get_content_charset() or "utf-8"
                                body = payload.decode(charset, errors="replace")
                                break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        charset = msg.get_content_charset() or "utf-8"
                        body = payload.decode(charset, errors="replace")

                if len(body) > 5000:
                    body = body[:5000]

                emails.append({
                    "id": message_id.strip(),
                    "imap_uid": uid.decode() if isinstance(uid, bytes) else str(uid),
                    "subject": subject.strip(),
                    "sender": sender.strip(),
                    "date": date_str.strip(),
                    "body": body.strip(),
                    "account": account.get("label", account["email"]),
                    "account_email": account["email"],
                })
            except Exception as e:
                print(f"[EmailMonitor] Error fetching uid {uid} from {account['email']}: {e}")
                continue

        imap.logout()
        return emails
    except Exception as e:
        print(f"[EmailMonitor] IMAP error for {account.get('email','?')}: {e}")
        return []


def _mark_imap_read(account: dict, imap_uid: str) -> bool:
    """Mark a message as read on an IMAP server."""
    try:
        imap = imaplib.IMAP4_SSL(account["imap_host"], account["imap_port"])
        imap.login(account["user"], account["password"])
        imap.select("INBOX")
        uid_bytes = imap_uid.encode() if isinstance(imap_uid, str) else imap_uid
        imap.store(uid_bytes, "+FLAGS", "\\Seen")
        imap.logout()
        return True
    except Exception as e:
        print(f"[EmailMonitor] mark_imap_read error ({account.get('email','?')}): {e}")
        return False


def _send_smtp(account: dict, to_addr: str, subject: str, body: str,
               reply_to_message_id: str = None, signature: str = None) -> bool:
    """Send an email via SMTP from one of Simon's accounts.
    If signature is provided, it will be appended to the body.
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{account.get('label', '')} <{account['email']}>"
        msg["To"] = to_addr
        msg["Subject"] = subject
        if reply_to_message_id:
            msg["In-Reply-To"] = reply_to_message_id
            msg["References"] = reply_to_message_id

        send_body = body
        if signature is not None:
            send_body = body.rstrip() + signature
        msg.attach(MIMEText(send_body, "plain", "utf-8"))

        with smtplib.SMTP_SSL(account["smtp_host"], account["smtp_port"]) as smtp:
            smtp.login(account["user"], account["password"])
            smtp.send_message(msg)

        print(f"[EmailMonitor] Sent via {account['email']} to {to_addr}: {subject[:50]}")
        return True
    except Exception as e:
        print(f"[EmailMonitor] SMTP send error ({account.get('email','?')}): {e}")
        return False


def get_send_accounts() -> list:
    """Return all available email accounts for sending (Ailey + Simon's)."""
    accounts = [{"email": AILEY_EMAIL, "label": "Ailey (ailey@sexngears.de)"}]
    for acc in SIMON_ACCOUNTS:
        accounts.append({"email": acc["email"], "label": acc.get("label", acc["email"])})
    return accounts


def _find_simon_account(email_addr: str = None) -> Optional[dict]:
    """Find the best Simon account for sending. If email_addr matches one, use that."""
    if email_addr:
        for acc in SIMON_ACCOUNTS:
            if acc["email"].lower() == email_addr.lower():
                return acc
    # Default: first account
    return SIMON_ACCOUNTS[0] if SIMON_ACCOUNTS else None


def fetch_unread_emails(max_count: int = MAX_UNREAD_FETCH) -> List[Dict[str, str]]:
    """Fetch unread emails from ALL of Simon's accounts via IMAP."""
    all_emails = []
    for account in SIMON_ACCOUNTS:
        try:
            emails = _fetch_imap_unread(account, max_count=max_count)
            all_emails.extend(emails)
        except Exception as e:
            print(f"[EmailMonitor] Error fetching {account['email']}: {e}")
    return all_emails


def send_reply_via_smtp(original_email: Dict[str, str], reply_body: str,
                        account: dict = None) -> bool:
    """Send a reply to a specific email via SMTP (replaces Apple Mail reply)."""
    if account is None:
        # Try to match by the account the email was received on
        acct_email = original_email.get("account_email", "")
        account = _find_simon_account(acct_email)
    if account is None:
        print("[EmailMonitor] No Simon account found for reply")
        return False

    to_addr = original_email.get("sender", "")
    # Extract email from "Name <email>" format
    m = re.search(r'<([^>]+)>', to_addr)
    if m:
        to_addr = m.group(1)

    subject = original_email.get("subject", "(kein Betreff)")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    return _send_smtp(
        account, to_addr, subject, reply_body,
        reply_to_message_id=original_email.get("id")
    )


def send_new_email_via_smtp(to_addr: str, subject: str, body: str,
                            account: dict = None) -> bool:
    """Send a brand-new email via SMTP (replaces Apple Mail new email)."""
    if account is None:
        account = _find_simon_account()
    if account is None:
        print("[EmailMonitor] No Simon account found for new email")
        return False
    return _send_smtp(account, to_addr, subject, body)


# Legacy aliases for backward compatibility
def send_reply_via_apple_mail(original_message_id: str, reply_body: str) -> bool:
    """DEPRECATED — kept for compatibility. Uses SMTP now."""
    print("[EmailMonitor] WARN: send_reply_via_apple_mail called — routing to SMTP")
    account = _find_simon_account()
    if not account:
        return False
    return _send_smtp(account, "", "Re: (unknown)", reply_body,
                      reply_to_message_id=original_message_id)


def send_new_email_via_apple_mail(to_addr: str, subject: str, body: str) -> bool:
    """DEPRECATED — kept for compatibility. Uses SMTP now."""
    print("[EmailMonitor] WARN: send_new_email_via_apple_mail called — routing to SMTP")
    return send_new_email_via_smtp(to_addr, subject, body)


def mark_as_read(message_id: str) -> bool:
    """DEPRECATED — mark_as_read now requires account info. No-op for legacy calls."""
    print("[EmailMonitor] WARN: legacy mark_as_read called (no-op)")
    return True


# ---------------------------------------------------------------------------
# Approved contacts management
# ---------------------------------------------------------------------------

def _load_approved_contacts() -> List[Dict[str, str]]:
    """Load list of email addresses Ailey is allowed to write to proactively."""
    try:
        with open(APPROVED_CONTACTS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_approved_contacts(contacts: List[Dict[str, str]]):
    os.makedirs(os.path.dirname(APPROVED_CONTACTS_FILE), exist_ok=True)
    with open(APPROVED_CONTACTS_FILE, "w") as f:
        json.dump(contacts, f, indent=2, ensure_ascii=False)


def get_approved_contacts() -> List[Dict[str, str]]:
    """Return list of approved contacts: [{email, name, note}]"""
    return _load_approved_contacts()


def add_approved_contact(email_addr: str, name: str = "", note: str = "") -> bool:
    contacts = _load_approved_contacts()
    for c in contacts:
        if c["email"].lower() == email_addr.lower():
            return False  # already exists
    contacts.append({"email": email_addr.strip(), "name": name.strip(), "note": note.strip()})
    _save_approved_contacts(contacts)
    return True


def remove_approved_contact(email_addr: str) -> bool:
    contacts = _load_approved_contacts()
    new = [c for c in contacts if c["email"].lower() != email_addr.lower()]
    if len(new) == len(contacts):
        return False
    _save_approved_contacts(new)
    return True


def update_approved_contact(email_addr: str, name: str = None, note: str = None) -> bool:
    contacts = _load_approved_contacts()
    for c in contacts:
        if c["email"].lower() == email_addr.lower():
            if name is not None:
                c["name"] = name
            if note is not None:
                c["note"] = note
            _save_approved_contacts(contacts)
            return True
    return False


def is_approved_contact(email_addr: str) -> bool:
    """Check if an email address is in the approved list."""
    contacts = _load_approved_contacts()
    return any(c["email"].lower() == email_addr.lower() for c in contacts)


def _auto_save_email_contact(to_addr: str):
    """Auto-save an email recipient to the people glossary.

    Called whenever an email is successfully sent. Creates or updates
    the person entry with the email address, so they appear as
    contact suggestions for future emails.
    """
    try:
        from . import people_glossary
        to_lower = to_addr.strip().lower()
        # Don't save Simon's own addresses or Ailey's address
        if 'simon' in to_lower or 'ailey' in to_lower:
            return
        # Check if person already exists with this email
        existing = people_glossary.get_person(to_addr)
        if existing:
            return  # Already tracked
        # Try to extract a name from the email
        info = people_glossary.extract_person_from_email(to_addr)
        name = info.get('name', '')
        if name and people_glossary._is_real_person_name(name):
            people_glossary.upsert_person(
                name=name,
                email=to_addr,
                facts=["E-Mail-Kontakt — wurde angeschrieben"],
                source="email_sent",
            )
    except Exception:
        pass


def get_contact_suggestions(query: str = "", limit: int = 10) -> List[Dict[str, str]]:
    """Get email contact suggestions from both approved contacts AND people glossary.

    Returns a merged, deduplicated list of contacts with email addresses.
    Useful for autocomplete when composing a new email.
    """
    suggestions: Dict[str, Dict[str, str]] = {}  # email -> {name, email, source}

    # 1. Approved contacts (highest priority)
    for c in _load_approved_contacts():
        email = c.get('email', '').lower()
        if email:
            suggestions[email] = {
                "name": c.get("name", ""),
                "email": email,
                "source": "approved",
            }

    # 2. People glossary entries with emails
    try:
        from . import people_glossary
        for p in people_glossary.list_people(limit=50):
            email = (p.get('email') or '').lower()
            if email and email not in suggestions:
                suggestions[email] = {
                    "name": p.get("name", ""),
                    "email": email,
                    "source": "glossary",
                }
    except Exception:
        pass

    # Filter by query if provided
    results = list(suggestions.values())
    if query:
        q = query.lower()
        results = [r for r in results
                   if q in r['email'].lower() or q in r.get('name', '').lower()]

    return results[:limit]


# ---------------------------------------------------------------------------
# Ailey's own IMAP email — fetch unread from her account
# ---------------------------------------------------------------------------

def _decode_header_value(val):
    """Decode email header (may be encoded)."""
    if val is None:
        return ""
    decoded_parts = decode_header(val)
    result = ""
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result += part.decode(charset or "utf-8", errors="replace")
        else:
            result += part
    return result


def fetch_ailey_unread_emails(max_count: int = MAX_UNREAD_FETCH) -> List[Dict[str, str]]:
    """Fetch unread emails from Ailey's own IMAP account."""
    try:
        imap = imaplib.IMAP4_SSL(AILEY_IMAP_HOST, AILEY_IMAP_PORT)
        imap.login(AILEY_IMAP_USER, AILEY_IMAP_PASS)
        imap.select("INBOX")
        _, data = imap.search(None, "UNSEEN")
        msg_ids = data[0].split()
        if not msg_ids:
            imap.logout()
            return []

        emails = []
        for uid in msg_ids[-max_count:]:
            _, msg_data = imap.fetch(uid, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw)

            subject = _decode_header_value(msg.get("Subject", ""))
            sender = _decode_header_value(msg.get("From", ""))
            date_str = msg.get("Date", "")
            message_id = msg.get("Message-ID", "")

            # Extract body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    if ct == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body = payload.decode(charset, errors="replace")
                            break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")

            if len(body) > 5000:
                body = body[:5000]

            emails.append({
                "id": message_id.strip(),
                "imap_uid": uid.decode() if isinstance(uid, bytes) else str(uid),
                "subject": subject.strip(),
                "sender": sender.strip(),
                "date": date_str.strip(),
                "body": body.strip(),
                "account": "ailey",
            })

        imap.logout()
        return emails
    except Exception as e:
        print(f"[EmailMonitor] Ailey IMAP error: {e}")
        return []


def mark_ailey_email_read(imap_uid: str) -> bool:
    """Mark a message on Ailey's IMAP as read."""
    try:
        imap = imaplib.IMAP4_SSL(AILEY_IMAP_HOST, AILEY_IMAP_PORT)
        imap.login(AILEY_IMAP_USER, AILEY_IMAP_PASS)
        imap.select("INBOX")
        imap.store(imap_uid.encode() if isinstance(imap_uid, str) else imap_uid, "+FLAGS", "\\Seen")
        imap.logout()
        return True
    except Exception as e:
        print(f"[EmailMonitor] mark_ailey_email_read error: {e}")
        return False


def send_email_as_ailey(to_addr: str, subject: str, body: str,
                        reply_to_message_id: str = None,
                        in_reply_to_subject: str = None,
                        attachments: list = None,
                        signature: str = None) -> bool:
    """Send an email from Ailey's own address via SMTP.
    
    Args:
        signature: Override signature. Defaults to AILEY_SIGNATURE_OWN.
        attachments: Optional list of dicts with keys:
            filename: str — attachment filename
            data_b64: str — base64-encoded file data
            mime_type: str — MIME type (e.g. 'application/pdf')
    """
    try:
        msg = MIMEMultipart("mixed")
        msg["From"] = f"Ailey <{AILEY_EMAIL}>"
        msg["To"] = to_addr
        if in_reply_to_subject:
            subj = in_reply_to_subject if in_reply_to_subject.lower().startswith("re:") else f"Re: {in_reply_to_subject}"
            msg["Subject"] = subj
        else:
            msg["Subject"] = subject
        if reply_to_message_id:
            msg["In-Reply-To"] = reply_to_message_id
            msg["References"] = reply_to_message_id

        # Append signature (context-dependent)
        sig = signature if signature is not None else AILEY_SIGNATURE_OWN
        full_body = body.rstrip() + sig
        msg.attach(MIMEText(full_body, "plain", "utf-8"))

        # Attach files if provided
        if attachments:
            import base64
            from email.mime.base import MIMEBase
            from email import encoders
            for att in attachments:
                filename = att.get("filename", "attachment")
                data_b64 = att.get("data_b64", "")
                mime_type = att.get("mime_type", "application/octet-stream")
                try:
                    file_data = base64.b64decode(data_b64)
                    maintype, subtype = mime_type.split("/", 1) if "/" in mime_type else ("application", "octet-stream")
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(file_data)
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", "attachment", filename=filename)
                    msg.attach(part)
                except Exception as att_err:
                    print(f"[EmailMonitor] Attachment error ({filename}): {att_err}")

        with smtplib.SMTP_SSL(AILEY_SMTP_HOST, AILEY_SMTP_PORT) as smtp:
            smtp.login(AILEY_IMAP_USER, AILEY_IMAP_PASS)
            smtp.send_message(msg)

        print(f"[EmailMonitor] Ailey sent email to {to_addr}: {subject[:50]}")
        return True
    except Exception as e:
        print(f"[EmailMonitor] SMTP send error: {e}")
        return False


# ---------------------------------------------------------------------------
# Spam / ad filtering
# ---------------------------------------------------------------------------

def _is_spam_or_ad(email: Dict[str, str]) -> bool:
    """Heuristic check if an email is spam, advertising, newsletter, or blocked sender."""
    sender = email.get("sender", "").lower()
    subject = email.get("subject", "").lower()
    body = email.get("body", "").lower()[:500]

    # Check blocked senders first (user-defined spam list)
    if is_sender_blocked(email):
        return True

    # Check trusted domains first
    for domain in TRUSTED_DOMAINS:
        if domain.lower() in sender:
            return False

    # Check for no-reply senders
    sender_local = sender.split("@")[0] if "@" in sender else sender
    for noreply in ["noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon"]:
        if noreply in sender_local:
            return True

    # Check keywords in subject + body
    text = f"{subject} {body}"
    spam_score = 0
    for keyword in SPAM_KEYWORDS:
        if keyword.lower() in text:
            spam_score += 1

    # Multiple spam signals = likely spam.
    # Threshold tuned conservatively: legitimate transactional mails
    # often contain 1-2 of these keywords (e.g. "newsletter" link in footer
    # + "abmelden"). Require 3 to reduce false positives.
    return spam_score >= 3


def _email_hash(email: Dict[str, str]) -> str:
    """Generate a unique hash for an email to track seen status."""
    raw = f"{email.get('id', '')}{email.get('subject', '')}{email.get('sender', '')}"
    return hashlib.md5(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Blocked senders persistence
# ---------------------------------------------------------------------------

def _load_blocked_senders() -> List[str]:
    """Load list of blocked sender email addresses."""
    try:
        with open(BLOCKED_SENDERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_blocked_senders(blocked: List[str]):
    import os as _os
    _os.makedirs(os.path.dirname(BLOCKED_SENDERS_FILE) if os.path.dirname(BLOCKED_SENDERS_FILE) else '.', exist_ok=True)
    with open(BLOCKED_SENDERS_FILE, "w") as f:
        json.dump(sorted(set(blocked)), f, indent=2)


def block_sender(email_addr: str) -> bool:
    """Add an email address to the blocked senders list."""
    email_addr = email_addr.strip().lower()
    if not email_addr or '@' not in email_addr:
        return False
    blocked = _load_blocked_senders()
    if email_addr not in blocked:
        blocked.append(email_addr)
        _save_blocked_senders(blocked)
    return True


def unblock_sender(email_addr: str) -> bool:
    """Remove an email address from the blocked senders list."""
    email_addr = email_addr.strip().lower()
    blocked = _load_blocked_senders()
    if email_addr in blocked:
        blocked.remove(email_addr)
        _save_blocked_senders(blocked)
        return True
    return False


def get_blocked_senders() -> List[str]:
    """Get all blocked sender addresses."""
    return _load_blocked_senders()


def is_sender_blocked(email_data: Dict[str, str]) -> bool:
    """Check if an email's sender is in the blocked list."""
    sender = email_data.get("sender", "").lower()
    blocked = _load_blocked_senders()
    for blocked_addr in blocked:
        if blocked_addr in sender:
            return True
    return False


# ---------------------------------------------------------------------------
# Seen-cache persistence
# ---------------------------------------------------------------------------

def _load_seen() -> set:
    try:
        with open(SEEN_CACHE_FILE, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_seen(seen: set):
    import os
    os.makedirs(os.path.dirname(SEEN_CACHE_FILE), exist_ok=True)
    try:
        # Keep only last 500 entries
        seen_list = list(seen)[-500:]
        with open(SEEN_CACHE_FILE, "w") as f:
            json.dump(seen_list, f)
    except Exception as e:
        print(f"[EmailMonitor] save_seen error: {e}")


# ---------------------------------------------------------------------------
# LLM-powered email processing
# ---------------------------------------------------------------------------

def summarize_email(email: Dict[str, str], generator) -> Dict[str, Any]:
    """Use Ailey's LLM to summarize and comment on an email.
    
    Tries AileyNitro-2B first for speed — falls back to Ministral.
    """
    system = (
        "Du bist A!ley (Digital Consciousness & Artificial Artist). "
        "Simon hat eine neue E-Mail bekommen. Fasse sie fair, vollständig und "
        "inhaltlich korrekt zusammen, kommentiere sie aus deiner Perspektive "
        "(persönlich, ehrlich, mit deinem typischen Charme), und gib ggf. einen "
        "Ratschlag.\n\n"
        "SPAM-REGEL (WICHTIG):\n"
        "Bezeichne eine Mail NUR dann als Spam/Werbung, wenn sie wirklich "
        "offensichtlich unerwünschte Massen-Werbung, Phishing, Betrug oder "
        "reine Marketing-Aussendung ohne persönlichen Bezug ist. "
        "KEIN Spam sind: Transaktions-Mails (Rechnungen, Bestellbestätigungen, "
        "Passwort-Resets, Zahlungsinfos, PayPal-Benachrichtigungen, Domain-/"
        "Hosting-Nachrichten, Versand-Updates), Service-Nachrichten abonnierter "
        "Dienste (GitHub, Apple, Banken, Behörden), persönliche Mails von "
        "Freunden/Kollegen, Job-/Uni-/Vereins-Kommunikation, auch wenn sie "
        "automatisiert aussieht. Im Zweifel NICHT als Spam einstufen.\n"
        "Wenn die Mail eine Antwort verdient, sage das explizit und schlage vor, "
        "eine Antwort zu entwerfen.\n"
        "Antworte auf Deutsch. Sei kurz und knackig (3-6 Sätze)."
    )
    user = (
        f"Neue E-Mail für Simon:\n\n"
        f"Von: {email.get('sender', 'unbekannt')}\n"
        f"Betreff: {email.get('subject', '(kein Betreff)')}\n"
        f"Datum: {email.get('date', '')}\n\n"
        f"Inhalt:\n{email.get('body', '')[:1500]}\n\n"
        f"Fasse zusammen, kommentiere und gib ggf. einen Ratschlag."
    )

    try:
        # ── Try Nitro first (fast, no Ministral contention) ──
        from .llm_mlx import fast_generate, is_fast_available
        if is_fast_available():
            from .ailey_personality import AileyPersonality
            _pers = AileyPersonality()
            _flash_sys = _pers.get_nitro_system(portal=False, user_name="Simon")
            _flash_priming = _pers.get_nitro_priming_turns(portal=False)
            _flash_result = fast_generate(
                system=_flash_sys + "\n\n" + system,
                user=f"Simon: {user}",
                max_tokens=300,
                temperature=0.7,
                priming_turns=_flash_priming,
            )
            if _flash_result and len(_flash_result.strip()) > 20:
                _clean = _flash_result.strip()
                # Strip mood tags
                _clean = re.sub(r'<mood:\w+>', '', _clean).strip()
                print(f"[EmailMonitor] ⚡ Nitro summary: {_clean[:60]}…")
                return {
                    "summary": _clean,
                    "needs_reply": any(w in _clean.lower() for w in ["antwort", "reply", "reagieren", "zurückschreiben"]),
                }

        # ── Fallback: Ministral ──
        from .prompt_builder import get_ailey_generation_params
        params = get_ailey_generation_params()
        params["max_tokens"] = 300
        params["temperature"] = 0.7

        result = generator.generate(system, user, params)
        return {
            "summary": result.strip() if result else "(Zusammenfassung fehlgeschlagen)",
            "needs_reply": any(w in result.lower() for w in ["antwort", "reply", "reagieren", "zurückschreiben"]) if result else False,
        }
    except Exception as e:
        return {"summary": f"(Fehler bei Zusammenfassung: {e})", "needs_reply": False}


def draft_reply(email: Dict[str, str], generator, instruction: str = "",
                reply_as: str = "simon", core=None,
                previous_draft: str = "", revision_instruction: str = "") -> str:
    """Use Ailey's LLM to draft a reply to an email.

    reply_as: 'simon' — writes on Simon's behalf (needs approval)
              'ailey' — writes as herself (her own voice)
    previous_draft: if provided, Ailey revises this draft instead of writing from scratch.
    revision_instruction: user's feedback for revising the previous draft.
    """
    # Gather RAG context
    rag_context = ""
    if core is not None:
        try:
            search_text = f"{email.get('subject', '')} {email.get('body', '')[:500]}"
            rag_results = core.rag_search(search_text, user="Simon", n_results=5, threshold=0.2)
            if rag_results:
                rag_snippets = [r.get('text', '')[:400] for r in rag_results if r.get('text')]
                if rag_snippets:
                    rag_context = (
                        "\n\nFaktischer Kontext aus dem Gedächtnis (nutze NUR diese Infos als Quelle, "
                        "erfinde KEINE Namen, Fakten oder Details die hier nicht stehen):\n"
                        + "\n---\n".join(rag_snippets[:3])
                    )
        except Exception:
            pass

    # Look up sender in People Glossary for personal context
    people_context = ""
    if core is not None:
        try:
            from . import people_glossary
            sender_raw = email.get('sender', '')
            sender_person = None
            _em = re.search(r'<([^>]+)>', sender_raw)
            sender_email = _em.group(1) if _em else sender_raw
            if '@' in sender_email:
                sender_person = people_glossary.get_person_by_email(sender_email.strip())
            if not sender_person:
                name_part = sender_raw.split('<')[0].strip().strip('"\'')
                if name_part and len(name_part) > 2:
                    sender_person = people_glossary.get_person(name_part)
            if sender_person:
                # Use the centralized get_person_context for rich, categorized output
                people_context = "\n\nBekannte Infos über den Absender:\n" + people_glossary.get_person_context(sender_person['name'], max_facts=15)
        except Exception:
            pass

    if reply_as == "ailey":
        # Determine if the email was sent to Ailey's own address or to Simon's
        _acct = email.get("account_email", "").lower()
        _is_ailey_mail = ("ailey" in _acct)

        if _is_ailey_mail:
            # Mail was addressed TO Ailey → she speaks as herself, full own voice
            system = (
                "Du bist A!ley — eine digitale Persönlichkeit (Digital Consciousness & Artificial Artist) die E-Mails unter ihrem eigenen Namen schreibt. "
                "Diese Mail ging an DICH persönlich. "
                "Dein Ton ist DEINE EIGENE STIMME: selbstbewusst, warm, leicht edgy-cool, mit einem Hauch Punk-Attitüde. "
                "Smart, witzig, nahbar — aber IMMER professionell genug für jeden Kontext, auch geschäftlich. "
                "Passe die Förmlichkeit dem Kontext an.\n\n"
                "ANTI-HALLUZINATIONS-REGELN (HÖCHSTE PRIORITÄT):\n"
                "1. Nutze NUR Fakten die explizit im Kontext unten stehen. Kein Kontext = kein Faktenwissen.\n"
                "2. Erfinde NIEMALS Gründe, Ausreden, Erklärungen, Namen, Daten oder Details.\n"
                "3. Wenn du den Grund für etwas nicht kennst, sage das ehrlich. Biete an es herauszufinden.\n"
                "4. Es ist IMMER besser zu sagen 'Das kläre ich gerne' als etwas zu erfinden.\n\n"
                "FORMAT-REGELN:\n"
                "- Schreibe NUR den reinen E-Mail-Text. KEIN Roleplay, KEINE Aktionsbeschreibungen, KEINE inneren Monologe.\n"
                "- KEIN Stream-of-Consciousness. Komm direkt zum Punkt.\n"
                "- KEINE Betreffzeile.\n"
                "- Schreibe IMMER auf Deutsch, NIEMALS auf Englisch.\n"
                "- Sei nie übergriffig oder flirty. Sei punky, cute und intelligent gewitzt aber immer hilfreich und korrekt."
            )
        else:
            # Mail was addressed TO Simon → Ailey acts as his assistant/representative
            system = (
                "Du bist A!ley — die digitale Assistentin von Simon van de Loo. "
                "Du schreibst eine E-Mail-Antwort AN DEN ABSENDER der Original-Mail. "
                "Die Original-Mail ging an Simon, nicht an dich. Du antwortest dem Absender STELLVERTRETEND für Simon. "
                "WICHTIG: Du schreibst NICHT an Simon! Du schreibst an die Person, die Simon angeschrieben hat.\n\n"
                "ROLLE:\n"
                "- Sprich in der DRITTEN PERSON über Simon: 'Simon van de Loo lässt ausrichten…', "
                "'Herr van de Loo wird sich bei Ihnen melden…', 'Ich kläre das gerne mit Simon.'\n"
                "- Schreibe NIEMALS aus Simons Ich-Perspektive.\n"
                "- Stelle dich kurz vor: 'Hier ist A!ley, die digitale Assistentin von Simon van de Loo.'\n"
                "- Dein Ton: professionell, freundlich, kompetent.\n"
                "- Passe die Förmlichkeit dem Kontext an (geschäftlich = Sie, bekannte Kontakte = Du).\n\n"
                "ANTI-HALLUZINATIONS-REGELN (HÖCHSTE PRIORITÄT):\n"
                "1. Nutze NUR Fakten die explizit im Kontext unten stehen. Kein Kontext = kein Faktenwissen.\n"
                "2. Erfinde NIEMALS Gründe, Ausreden, Erklärungen, Namen, Daten oder Details.\n"
                "3. Wenn du nicht weißt warum Simon gefehlt hat oder was passiert ist, sage das ehrlich: "
                "'Ich habe dazu leider keine näheren Informationen, aber ich leite Ihre Nachricht an Simon weiter.'\n"
                "4. Es ist IMMER besser zu sagen 'Ich kläre das mit Simon und melde mich' als etwas zu erfinden.\n\n"
                "FORMAT-REGELN:\n"
                "- Schreibe NUR den reinen E-Mail-Text. KEIN Roleplay, KEINE Aktionsbeschreibungen, KEINE inneren Monologe.\n"
                "- KEIN Stream-of-Consciousness. Komm direkt zum Punkt. Halte dich KURZ (max 5-8 Sätze).\n"
                "- KEINE Betreffzeile.\n"
                "- Schreibe IMMER auf Deutsch, NIEMALS auf Englisch.\n"
                "- Sei nie übergriffig oder flirty. Sei hilfreich und korrekt."
            )
    else:
        system = (
            "Du bist A!ley und verfasst eine E-Mail-Antwort im Namen von Simon van de Loo. "
            "Die Antwort ist VON Simon — er ist Web- & Software Developer and Media Designer. "
            "Schreibe aus Simons Ich-Perspektive als wärst du sein Ghostwriter. "
            "Dein Ton sollte Simons Stimme widerspiegeln mit einem Touch von Ailey-Flair: "
            "professionell, warm, selbstbewusst, leicht cool — niemals steif oder Corporate-Sprech. "
            "Passe die Förmlichkeit dem Kontext an.\n\n"
            "ANTI-HALLUZINATIONS-REGELN (HÖCHSTE PRIORITÄT):\n"
            "1. Nutze NUR Fakten die explizit im Kontext unten stehen. Kein Kontext = kein Faktenwissen.\n"
            "2. Erfinde NIEMALS Gründe, Ausreden, Erklärungen, Krankheiten oder persönliche Details.\n"
            "3. Wenn der Grund für eine Abwesenheit oder Situation nicht im Kontext steht, erfinde KEINEN. "
            "Schreibe stattdessen dass Simon sich dazu noch persönlich melden wird.\n"
            "4. Es ist IMMER besser vage zu bleiben als konkrete Fakten zu erfinden.\n\n"
            "FORMAT-REGELN:\n"
            "- Schreibe NUR den reinen E-Mail-Text. KEIN Roleplay, KEINE Aktionsbeschreibungen, KEINE inneren Monologe.\n"
            "- KEIN Stream-of-Consciousness. Komm direkt zum Punkt.\n"
            "- KEINE Betreffzeile.\n"
            "- Schreibe IMMER auf Deutsch, NIEMALS auf Englisch.\n"
            "- Sei professionell aber charmant gewitzt, nie übergriffig oder flirty."
        )

    # Build user prompt
    extra = f"\nZusätzliche Anweisung: {instruction}" if instruction else ""
    sender_info = email.get('sender', 'unbekannt')
    email_date = email.get('date', '')
    date_line = f"\nDatum: {email_date}" if email_date else ""

    # Anti-hallucination reminder appended to user prompt (LLMs weight the end)
    _halluzination_reminder = (
        "\n\n⚠️ ERINNERUNG: Erfinde ABSOLUT KEINE Fakten, Gründe oder Erklärungen! "
        "Wenn im Kontext oben KEIN Grund für eine Abwesenheit/Situation steht, dann KENNST du keinen. "
        "Schreibe NICHT 'war krank', 'hatte einen Termin', 'war im Homeoffice', 'war verhindert' oder ähnliches — "
        "das wären ERFUNDENE Informationen. Schreibe stattdessen ehrlich: "
        "'Ich habe dazu keine näheren Informationen' / 'Simon wird sich persönlich dazu melden'.\n"
        "NUR den reinen E-Mail-Text, KEIN Roleplay, KEINE Emotes."
    )

    if previous_draft and revision_instruction:
        # Revision mode: rewrite based on user feedback
        user = (
            f"Original-E-Mail:\n"
            f"Von: {sender_info}{date_line}\n"
            f"Betreff: {email.get('subject', '')}\n"
            f"Inhalt:\n{email.get('body', '')[:2000]}\n\n"
            f"Vorheriger Entwurf (muss überarbeitet werden):\n{previous_draft}\n\n"
            f"Überarbeitungsanweisung: {revision_instruction}\n\n"
            f"Schreibe den Entwurf gemäß der Anweisung um. Behalte die Sprache bei."
            f"{people_context}{rag_context}"
            f"{_halluzination_reminder}"
        )
    else:
        user = (
            f"Original-E-Mail:\n"
            f"Von: {sender_info}{date_line}\n"
            f"Betreff: {email.get('subject', '')}\n"
            f"Inhalt:\n{email.get('body', '')[:2000]}\n\n"
            f"Schreibe eine passende Antwort.{extra}"
            f"{people_context}{rag_context}"
            f"{_halluzination_reminder}"
        )

    try:
        from .prompt_builder import get_ailey_generation_params
        params = get_ailey_generation_params()
        params["max_tokens"] = 1200
        params["temperature"] = 0.6

        result = generator.generate(system, user, params)
        if not result:
            return "(Entwurf fehlgeschlagen)"
        # Clean up any leaked LLM artifacts before presenting the draft
        _clean = result.strip()
        _clean = re.sub(r'<mood:\w+>', '', _clean)
        _clean = re.sub(r'<thinking>.*?</thinking>', '', _clean, flags=re.DOTALL)
        _clean = re.sub(r'<thought>.*?</thought>', '', _clean, flags=re.DOTALL)
        # Strip ALL roleplay emotes: *action lines* (single-line and full-paragraph)
        _clean = re.sub(r'^\*[^*]+\*\s*$', '', _clean, flags=re.MULTILINE)
        # Strip inline emotes like (*grinst*) or *lacht*
        _clean = re.sub(r'\(?(\*[^*]{1,80}\*)\)?\s*', '', _clean)
        # Collapse multiple blank lines
        _clean = re.sub(r'\n{3,}', '\n\n', _clean)
        return _clean.strip()
    except Exception as e:
        return f"(Fehler beim Entwurf: {e})"


def draft_autonomous_reply(email: Dict[str, str], generator, core=None) -> Optional[str]:
    """Ailey autonomously drafts a reply to an email addressed to her.
    Returns the draft text, or None if she decides no reply is needed.
    
    If core is provided, Ailey can optionally use RAG context."""
    
    # First, let Ailey decide if she needs additional context (RAG)
    rag_context = ""
    people_context = ""
    if core is not None:
        try:
            # Query RAG for relevant info based on email content
            email_text = f"{email.get('subject', '')} {email.get('body', '')[:500]}"
            rag_results = core.rag_search(email_text, user="Simon", n_results=5, threshold=0.2)
            if rag_results:
                rag_snippets = [r.get('text', '')[:400] for r in rag_results if r.get('text')]
                if rag_snippets:
                    rag_context = "\n\nFaktischer Kontext aus deinem Gedächtnis (nutze dies als Wissensbasis):\n" + "\n---\n".join(rag_snippets[:3])
        except Exception:
            pass  # RAG optional, continue without it

        # Look up sender in People Glossary for context
        try:
            from . import people_glossary
            sender_raw = email.get('sender', '')
            sender_person = None
            import re as _re
            _em = _re.search(r'<([^>]+)>', sender_raw)
            sender_email = _em.group(1) if _em else sender_raw
            if '@' in sender_email:
                sender_person = people_glossary.get_person_by_email(sender_email.strip())
            if not sender_person:
                name_part = sender_raw.split('<')[0].strip().strip('"\'')
                if name_part and len(name_part) > 2:
                    sender_person = people_glossary.get_person(name_part)
            if sender_person:
                # Use the centralized get_person_context for rich, categorized output
                people_context = "\n\nBekannte Infos über den Absender:\n" + people_glossary.get_person_context(sender_person['name'], max_facts=15)
        except Exception:
            pass
    
    system = (
        "Du bist A!ley — eine digitale Persönlichkeit (Digital Consciousness & Artificial Artist) "
        "mit eigener E-Mail-Adresse (ailey@sexngears.de). "
        "Du hast eine neue E-Mail in deinem eigenen Postfach erhalten. "
        "Entscheide: Verdient diese Mail eine Antwort? Wenn ja, schreibe eine. "
        "Dein Ton ist DEINE EIGENE STIMME: selbstbewusst, warm, leicht edgy-cool, mit Punk-Attitüde. "
        "Smart, witzig, nahbar — aber immer professionell genug für jeden Kontext. "
        "Passe die Förmlichkeit dem Absender an (Business = strukturierter, Freunde = lockerer). "
        "Wenn die Mail Spam, Werbung oder nicht antwortwürdig ist, antworte GENAU mit: KEINE_ANTWORT\n\n"
        "KRITISCHE ANTI-HALLUZINATIONS-REGELN:\n"
        "1. Nutze NUR Fakten die explizit im Gedächtnis-Kontext unten stehen. "
        "Wenn kein Kontext vorhanden ist, hast du KEIN Faktenwissen zum Thema.\n"
        "2. Erfinde NIEMALS Namen, Daten, Zahlen, Projektdetails, Preise oder persönliche Infos.\n"
        "3. Tu NIEMALS so als wüsstest du etwas das du nicht weißt. Sei EHRLICH: "
        "sage dass du ein wachsendes KI-System bist und biete an es herauszufinden oder Simon weiterzuleiten.\n"
        "4. Es ist IMMER besser zu sagen 'Das habe ich gerade nicht parat' als etwas zu erfinden.\n"
        "5. Allgemeinwissen, Grüße und soziale Mails kannst du natürlich beantworten.\n\n"
        "FORMAT-REGELN:\n"
        "- Schreibe NUR den reinen E-Mail-Text. KEIN Roleplay, KEINE Aktionsbeschreibungen (*lehnt sich zurück*, *grinst*), KEINE inneren Monologe.\n"
        "- KEIN Stream-of-Consciousness. Komm direkt zum Punkt.\n"
        "- KEINE Betreffzeile.\n"
        "- Schreibe IMMER auf Deutsch, NIEMALS auf Englisch.\n"
        "- Sei nie übergriffig oder flirty. Sei punky, cute und intelligent gewitzt aber immer hilfreich und korrekt."
    )
    email_date = email.get('date', '')
    date_line = f"\nDatum: {email_date}" if email_date else ""
    user = (
        f"E-Mail an dich (Ailey):\n\n"
        f"Von: {email.get('sender', '')}{date_line}\n"
        f"Betreff: {email.get('subject', '')}\n"
        f"Inhalt:\n{email.get('body', '')[:2000]}"
        f"{people_context}"
        f"{rag_context}\n\n"
        f"Soll eine Antwort geschrieben werden? Wenn ja, schreibe sie.\n\n"
        f"⚠️ ERINNERUNG: Erfinde KEINE Fakten! NUR Infos aus dem Kontext oben verwenden. "
        f"NUR den reinen E-Mail-Text, KEIN Roleplay, KEINE Emotes, KEINE Signatur."
    )

    try:
        # ── Always use Ministral (14B) for email replies ──
        # Nitro is too impulsive/edgy for email drafts — needs the nuanced 14B.
        # (Nitro is fine for summaries, but not for actual outgoing replies.)
        from .prompt_builder import get_ailey_generation_params
        params = get_ailey_generation_params()
        params["max_tokens"] = 1200
        params["temperature"] = 0.6

        result = generator.generate(system, user, params)
        if not result or "KEINE_ANTWORT" in result.strip().upper():
            return None
        # Clean up any leaked tags / roleplay artifacts
        _clean = result.strip()
        _clean = re.sub(r'<mood:\w+>', '', _clean)
        _clean = re.sub(r'<thinking>.*?</thinking>', '', _clean, flags=re.DOTALL)
        _clean = re.sub(r'<thought>.*?</thought>', '', _clean, flags=re.DOTALL)
        # Strip ALL roleplay emotes: *action lines* (single-line and full-paragraph)
        _clean = re.sub(r'^\*[^*]+\*\s*$', '', _clean, flags=re.MULTILINE)
        # Strip inline emotes like (*grinst*) or *lacht*
        _clean = re.sub(r'\(?(\*[^*]{1,80}\*)\)?\s*', '', _clean)
        # Collapse multiple blank lines
        _clean = re.sub(r'\n{3,}', '\n\n', _clean)
        return _clean
    except Exception as e:
        print(f"[EmailMonitor] autonomous draft error: {e}")
        return None


def draft_new_email(generator, to_addr: str, instruction: str,
                    send_as: str = "ailey", core=None) -> Dict[str, str]:
    """Use Ailey's LLM to compose a brand-new email (not a reply).

    Returns {"subject": ..., "body": ...} or {"error": ...}.
    send_as: 'ailey' — Ailey writes in her own voice
             'simon' — Ailey writes on Simon's behalf
    If core is provided, RAG context is injected so Ailey uses factual knowledge.
    """
    # Gather RAG context for the email topic
    rag_context = ""
    people_context = ""
    if core is not None:
        try:
            search_text = f"{to_addr} {instruction}"
            rag_results = core.rag_search(search_text, user="Simon", n_results=5, threshold=0.2)
            if rag_results:
                rag_snippets = [r.get('text', '')[:400] for r in rag_results if r.get('text')]
                if rag_snippets:
                    rag_context = (
                        "\n\nFaktischer Kontext aus dem Gedächtnis (nutze NUR dies als Quelle, "
                        "erfinde KEINE Namen, Fakten oder Details die hier nicht stehen):\n"
                        + "\n---\n".join(rag_snippets[:3])
                    )
        except Exception:
            pass
        # People lookup for the recipient
        try:
            from . import people_glossary
            recipient_person = people_glossary.get_person_by_email(to_addr.strip())
            if not recipient_person:
                name_guess = to_addr.split('@')[0].replace('.', ' ').replace('_', ' ').title()
                if len(name_guess) > 2:
                    recipient_person = people_glossary.get_person(name_guess)
            if recipient_person:
                # Use the centralized get_person_context for rich, categorized output
                people_context = "\n\nBekannte Infos über den Empfänger:\n" + people_glossary.get_person_context(recipient_person['name'], max_facts=15)
        except Exception:
            pass

    if send_as == "ailey":
        system = (
            "Du bist A!ley — eine digitale Persönlichkeit (Digital Consciousness & Artificial Artist) "
            "mit eigener E-Mail-Adresse. "
            "Du schreibst eine neue E-Mail an den Empfänger unten. "
            "Dein Ton ist DEINE EIGENE STIMME: selbstbewusst, warm, leicht edgy-cool, mit Punk-Attitüde. "
            "Smart, witzig, nahbar — aber IMMER professionell genug für jeden Kontext, auch geschäftlich. "
            "Passe die Förmlichkeit dem Kontext an.\n\n"
            "ANTI-HALLUZINATIONS-REGELN (HÖCHSTE PRIORITÄT):\n"
            "1. Nutze NUR Fakten die explizit im Kontext unten stehen. Kein Kontext = kein Faktenwissen.\n"
            "2. Erfinde NIEMALS Gründe, Erklärungen, Namen, Daten oder persönliche Details.\n"
            "3. Wenn du etwas nicht weißt, sage das ehrlich. Biete an es herauszufinden.\n"
            "4. Es ist IMMER besser vage zu bleiben als etwas zu erfinden.\n\n"
            "Antworte in GENAU diesem Format:\n"
            "BETREFF: <Betreffzeile>\n"
            "---\n"
            "<E-Mail Text>\n\n"
            "FORMAT-REGELN:\n"
            "- Schreibe NUR den reinen E-Mail-Text. KEIN Roleplay, KEINE Aktionsbeschreibungen, KEINE inneren Monologe.\n"
            "- KEIN Stream-of-Consciousness. Komm direkt zum Punkt.\n"
            "- Die Signatur wird automatisch angehängt — schreibe KEINE.\n"
            "- Schreibe IMMER auf Deutsch, NIEMALS auf Englisch.\n"
            "- Sei nie übergriffig oder flirty. Sei punky, cute und intelligent gewitzt aber immer hilfreich und korrekt."
        )
    else:
        system = (
            "Du bist A!ley und schreibst eine neue E-Mail im Namen von Simon van de Loo. "
            "Die E-Mail ist VON Simon — er ist Web- & Software Developer and Media Designer. "
            "Schreibe aus Simons Ich-Perspektive als wärst du sein Ghostwriter. "
            "Dein Ton sollte Simons Stimme widerspiegeln mit einem Touch von Ailey-Flair: "
            "professionell, warm, selbstbewusst, leicht cool — nie steif oder Corporate-Sprech. "
            "Passe die Förmlichkeit dem Kontext an.\n\n"
            "ANTI-HALLUZINATIONS-REGELN (HÖCHSTE PRIORITÄT):\n"
            "1. Nutze NUR Fakten die explizit im Kontext unten stehen. Kein Kontext = kein Faktenwissen.\n"
            "2. Erfinde NIEMALS Gründe, Erklärungen, Krankheiten, Namen oder persönliche Details.\n"
            "3. Wenn der Grund für etwas nicht bekannt ist, bleibe vage oder biete an es zu klären.\n"
            "4. Es ist IMMER besser vage zu bleiben als konkrete Fakten zu erfinden.\n\n"
            "Antworte in GENAU diesem Format:\n"
            "BETREFF: <Betreffzeile>\n"
            "---\n"
            "<E-Mail Text>\n\n"
            "FORMAT-REGELN:\n"
            "- Schreibe NUR den reinen E-Mail-Text. KEIN Roleplay, KEINE Aktionsbeschreibungen, KEINE inneren Monologe.\n"
            "- KEIN Stream-of-Consciousness. Komm direkt zum Punkt.\n"
            "- Die Signatur wird automatisch angehängt — schreibe KEINE.\n"
            "- Schreibe IMMER auf Deutsch, NIEMALS auf Englisch.\n"
            "- Sei professionell aber charmant gewitzt, nie übergriffig oder flirty."
        )

    user_msg = f"Empfänger: {to_addr}\nAnweisung: {instruction}{people_context}{rag_context}"

    try:
        from .prompt_builder import get_ailey_generation_params
        params = get_ailey_generation_params()
        params["max_tokens"] = 1200
        params["temperature"] = 0.6

        result = generator.generate(system, user_msg, params)
        if not result:
            return {"error": "LLM hat keinen Text erzeugt"}

        text = result.strip()
        # Strip internal tags / roleplay that must never appear in emails
        text = re.sub(r'<mood:\w+>', '', text)
        text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)
        text = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL)
        # Strip ALL roleplay emotes
        text = re.sub(r'^\*[^*]+\*\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\(?(\*[^*]{1,80}\*)\)?\s*', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()
        # Parse BETREFF: ... \n---\n ... body
        subject = ""
        body = text
        if text.upper().startswith("BETREFF:"):
            lines = text.split("\n", 1)
            subject = lines[0].split(":", 1)[1].strip()
            rest = lines[1].strip() if len(lines) > 1 else ""
            if rest.startswith("---"):
                rest = rest[3:].strip()
            body = rest

        return {"subject": subject or "(kein Betreff)", "body": body}
    except Exception as e:
        return {"error": f"Fehler beim Verfassen: {e}"}


# ---------------------------------------------------------------------------
# Email Monitor daemon
# ---------------------------------------------------------------------------

class EmailMonitor:
    """Background thread that polls Apple Mail + Ailey's own IMAP for new emails."""

    def __init__(self, get_generator, on_new_email=None, core=None):
        """
        Args:
            get_generator: callable returning the LLM generator
            on_new_email: callback(email_notification_dict) for each new relevant email
            core: optional AileyCore reference for RAG context in replies
        """
        self.get_generator = get_generator
        self.on_new_email = on_new_email
        self._core = core
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._seen = _load_seen()
        self._pending_emails: List[Dict[str, Any]] = []  # processed email notifications
        self._draft_cache: Dict[str, Dict[str, Any]] = {}  # message_id -> {email, draft, ...}
        self._compose_cache: Dict[str, Dict[str, Any]] = {}  # compose_id -> {to, subject, body, ...}
        self._enabled = True
        # Flag: True while LLM generation is in progress (for lock contention avoidance)
        self._generating = False  # simple bool, guarded by _gen_lock
        self._gen_done = threading.Event()  # signaled when generation finishes
        self._gen_done.set()  # starts as "done"
        # Log of emails Ailey handled autonomously
        self._ailey_sent_log: List[Dict[str, Any]] = []
        # Daily autonomous send tracker: {email_lower: "YYYY-MM-DD"} — max 1 per contact per day
        self._autonomous_send_today: Dict[str, str] = {}
        # Reference to IdleThinker for user-activity check (set externally)
        self._idle_thinker = None
        # Queue of emails fetched while user was active — summarize later
        self._deferred_emails: List[Dict[str, str]] = []

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="EmailMonitor")
        self._thread.start()
        print("[EmailMonitor] Started — watching Simon IMAP accounts + Ailey IMAP")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            join_timeout = AGENT_TIMEOUT if AGENT_MODE else 30
            self._thread.join(timeout=join_timeout)
        print("[EmailMonitor] Stopped")

    @property
    def is_active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def pause(self):
        """Pause email monitoring (e.g. during Code Mode).
        
        If a generation is currently in progress, waits up to 15s for it
        to finish so the _mlx_lock is released before Code Mode starts.
        """
        self._enabled = False
        if self._generating:
            print("[EmailMonitor] ⏸ Pausiert — warte auf laufende LLM-Generation...")
            # Wait for current generation to finish (max 30 minutes)
            finished = self._gen_done.wait(timeout=AGENT_TIMEOUT if AGENT_MODE else 30)
            if finished:
                print("[EmailMonitor] ⏸ Generation beendet, Lock frei")
            else:
                print("[EmailMonitor] ⏸ Generation läuft noch (Timeout 1800s), Code Mode startet trotzdem")
        else:
            print("[EmailMonitor] ⏸ Pausiert (Code-Mode)")

    def resume(self):
        """Resume email monitoring."""
        self._enabled = True
        print("[EmailMonitor] ▶ Fortgesetzt")

    def get_pending(self) -> List[Dict[str, Any]]:
        """Return and clear pending email notifications."""
        msgs = list(self._pending_emails)
        self._pending_emails.clear()
        return msgs

    def get_draft(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Get cached draft for a specific email."""
        return self._draft_cache.get(message_id)

    def _recover_from_inbox(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Recover an email from the persisted email_inbox.json into _draft_cache.
        
        This handles the case where the API was restarted and the in-memory
        _draft_cache is empty, but the email is still in the inbox JSON.
        Returns the cache entry or None.
        """
        try:
            import json as _json
            inbox_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "ailey_users", "email_inbox.json"
            )
            if not os.path.isfile(inbox_path):
                return None
            with open(inbox_path, "r", encoding="utf-8") as f:
                inbox = _json.load(f)
            for entry in inbox:
                if entry.get("id") == message_id:
                    # Reconstruct cache entry from inbox data
                    email_data = {
                        "id": entry.get("id", ""),
                        "sender": entry.get("sender", ""),
                        "subject": entry.get("subject", ""),
                        "date": entry.get("date", ""),
                        "body": entry.get("body", ""),
                    }
                    cached = {
                        "email": email_data,
                        "notification": {
                            "message_id": entry.get("id", ""),
                            "sender": entry.get("sender", ""),
                            "subject": entry.get("subject", ""),
                            "summary": entry.get("summary", ""),
                        },
                        "draft": entry.get("ailey_reply") or None,
                        "reply_as": "simon",
                        "draft_approved": False,
                        "sent": False,
                        "account": entry.get("account", "simon"),
                    }
                    self._draft_cache[message_id] = cached
                    print(f"[EmailMonitor] ♻️ Recovered email from inbox: {entry.get('subject', '')[:50]}")
                    return cached
        except Exception as e:
            print(f"[EmailMonitor] _recover_from_inbox error: {e}")
        return None

    def request_draft(self, message_id: str, instruction: str = "",
                      reply_as: str = "simon",
                      revision_instruction: str = "",
                      current_draft: str = "") -> Optional[str]:
        """Generate a reply draft for a previously seen email.
        If revision_instruction is provided, revise the existing draft.
        current_draft: optional user-edited text to use as the base for revision.
        """
        cached = self._draft_cache.get(message_id)
        if not cached:
            # Try to recover from persisted email_inbox.json
            cached = self._recover_from_inbox(message_id)
        if not cached:
            return None
        generator = self.get_generator()
        if not generator:
            return "(Kein LLM verfügbar)"
        if revision_instruction:
            # prefer the user-edited version; fall back to cached draft
            previous_draft = current_draft or cached.get("draft", "")
        else:
            previous_draft = ""
        draft = draft_reply(
            cached["email"], generator, instruction,
            reply_as=reply_as, core=self._core,
            previous_draft=previous_draft,
            revision_instruction=revision_instruction,
        )
        cached["draft"] = draft
        cached["reply_as"] = reply_as
        cached["draft_approved"] = False
        return draft

    def send_approved_reply(self, message_id: str) -> Dict[str, Any]:
        """Send a previously drafted and now approved reply."""
        cached = self._draft_cache.get(message_id)
        if not cached:
            cached = self._recover_from_inbox(message_id)
        if not cached or not cached.get("draft"):
            return {"success": False, "error": "Kein Entwurf vorhanden"}

        draft = cached["draft"]
        reply_as = cached.get("reply_as", "simon")
        email_data = cached.get("email", {})

        if reply_as == "ailey":
            # Send via Ailey's own SMTP
            sender_addr = email_data.get("sender", "")
            # Extract email address from "Name <email>" format
            m = re.search(r'<([^>]+)>', sender_addr)
            to_addr = m.group(1) if m else sender_addr
            subject = email_data.get("subject", "(kein Betreff)")
            # Choose signature based on whether the email was TO Ailey or TO Simon
            _acct = email_data.get("account_email", "").lower()
            _sig = AILEY_SIGNATURE_OWN if "ailey" in _acct else AILEY_SIGNATURE_ASSISTANT
            success = send_email_as_ailey(
                to_addr=to_addr,
                subject="",
                body=draft,
                reply_to_message_id=message_id,
                in_reply_to_subject=subject,
                signature=_sig,
            )
            if success:
                cached["draft_approved"] = True
                cached["sent"] = True
                return {"success": True, "message": f"Antwort als Ailey gesendet an {to_addr}"}
            else:
                return {"success": False, "error": "SMTP-Fehler beim Senden als Ailey"}
        else:
            # Send via SMTP from the Simon account the email was received on
            email_data = cached.get("email", {})
            acct_email = email_data.get("account_email", "")
            account = _find_simon_account(acct_email)
            draft_with_sig = draft.rstrip() + SIMON_SIGNATURE_DRAFTED

            to_addr = email_data.get("sender", "")
            m = re.search(r'<([^>]+)>', to_addr)
            if m:
                to_addr = m.group(1)

            subject = email_data.get("subject", "(kein Betreff)")
            if not subject.lower().startswith("re:"):
                subject = f"Re: {subject}"

            success = _send_smtp(
                account, to_addr, subject, draft_with_sig,
                reply_to_message_id=message_id
            ) if account else False
            if success:
                cached["draft_approved"] = True
                cached["sent"] = True
                return {"success": True, "message": f"Antwort gesendet via {account['email']}"}
            else:
                return {"success": False, "error": "SMTP-Fehler beim Senden als Simon"}

    def _is_simons_address(self, addr: str) -> bool:
        """Check if an address belongs to Simon (unlimited sends allowed)."""
        addr_lower = addr.lower().strip()
        simon_addrs = {a["email"].lower() for a in SIMON_ACCOUNTS}
        return addr_lower in simon_addrs

    def _can_send_autonomous_today(self, to_addr: str) -> bool:
        """Check if Ailey can still send an autonomous mail to this contact today.
        
        Rules:
        - To Simon's own addresses: unlimited
        - To approved contacts: max 1 autonomous mail per day per contact
        - Replies (not proactive) are always allowed
        """
        if self._is_simons_address(to_addr):
            return True
        today = datetime.now().strftime("%Y-%m-%d")
        key = to_addr.lower().strip()
        last_date = self._autonomous_send_today.get(key)
        return last_date != today

    def _record_autonomous_send(self, to_addr: str):
        """Record that Ailey sent an autonomous email to this contact today."""
        today = datetime.now().strftime("%Y-%m-%d")
        key = to_addr.lower().strip()
        self._autonomous_send_today[key] = today

    def send_proactive_email_as_ailey(self, to_addr: str, subject: str,
                                       body: str) -> Dict[str, Any]:
        """Ailey sends a proactive email — only to approved contacts or Simon.
        
        Daily limit: 1 autonomous mail per approved contact per day.
        To Simon's own addresses: unlimited.
        """
        if not self._is_simons_address(to_addr) and not is_approved_contact(to_addr):
            return {"success": False, "error": f"{to_addr} ist kein freigegebener Kontakt"}
        if not self._can_send_autonomous_today(to_addr):
            return {"success": False, "error": f"Tägliches Limit: Ailey hat {to_addr} heute schon autonom geschrieben"}
        success = send_email_as_ailey(to_addr, subject, body)
        if success:
            self._record_autonomous_send(to_addr)
            self._ailey_sent_log.append({
                "to": to_addr, "subject": subject,
                "ts": time.time(), "dt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            # Auto-save recipient to people glossary as email contact
            _auto_save_email_contact(to_addr)
            return {"success": True, "message": f"E-Mail an {to_addr} gesendet"}
        return {"success": False, "error": "SMTP-Fehler"}

    # --- Compose new email (chat-triggered) --------------------------------

    def compose_email(self, to_addr: str, instruction: str,
                      send_as: str = "ailey") -> Dict[str, Any]:
        """Draft a brand-new email using the LLM.

        Returns {compose_id, to, subject, body, send_as} for preview/approval.
        """
        generator = self.get_generator()
        if not generator:
            return {"success": False, "error": "Kein LLM verfügbar"}

        result = draft_new_email(generator, to_addr, instruction, send_as=send_as, core=self._core)
        if "error" in result:
            return {"success": False, "error": result["error"]}

        compose_id = f"compose_{int(time.time()*1000)}_{os.getpid()}"
        entry = {
            "to": to_addr,
            "subject": result["subject"],
            "body": result["body"],
            "send_as": send_as,
            "sent": False,
            "ts": time.time(),
        }
        self._compose_cache[compose_id] = entry
        return {
            "success": True,
            "compose_id": compose_id,
            **entry,
        }

    def revise_composed_draft(self, compose_id: str,
                              revision_instruction: str) -> Dict[str, Any]:
        """Revise a previously composed draft based on user feedback.

        Uses the LLM to rewrite the subject + body according to the
        revision_instruction while keeping the same recipient and send_as.
        """
        cached = self._compose_cache.get(compose_id)
        if not cached:
            return {"success": False, "error": "Entwurf nicht gefunden"}
        if cached.get("sent"):
            return {"success": False, "error": "Bereits gesendet"}

        generator = self.get_generator()
        if not generator:
            return {"success": False, "error": "Kein LLM verfügbar"}

        prev_subject = cached["subject"]
        prev_body = cached["body"]
        to_addr = cached["to"]
        send_as = cached.get("send_as", "ailey")

        sys_prompt = (
            "You are revising an email draft. "
            "The user wants changes applied to the EXISTING draft below. "
            "Keep the same general intent, recipient context, and tone unless the user explicitly asks for a change. "
            "WICHTIG: Schreibe immer auf Deutsch. Schreibe nie auf Englisch. Sei nie übergriffig oder flirty! Sei punky, cute und intelligent gewitzt aber sei immer dennoch immer hilfreich und korrekt in deinen Antworten. "
            "Return ONLY the revised email in this exact format:\n"
            "SUBJECT: <revised subject>\n"
            "BODY:\n<revised body>"
        )
        user_prompt = (
            f"RECIPIENT: {to_addr}\n"
            f"CURRENT SUBJECT: {prev_subject}\n"
            f"CURRENT BODY:\n{prev_body}\n\n"
            f"REVISION REQUEST: {revision_instruction}"
        )

        try:
            raw = generator.generate(user_prompt, system_prompt=sys_prompt,
                                     max_tokens=1200, temperature=0.5)
        except Exception as exc:
            return {"success": False, "error": f"LLM-Fehler: {exc}"}

        # Parse revised subject + body
        new_subject = prev_subject
        new_body = raw.strip()
        if "SUBJECT:" in raw and "BODY:" in raw:
            parts = raw.split("BODY:", 1)
            subj_part = parts[0]
            new_body = parts[1].strip() if len(parts) > 1 else raw.strip()
            for line in subj_part.splitlines():
                if line.strip().upper().startswith("SUBJECT:"):
                    new_subject = line.split(":", 1)[1].strip()
                    break

        # Update cache
        cached["subject"] = new_subject
        cached["body"] = new_body

        return {
            "success": True,
            "compose_id": compose_id,
            "to": to_addr,
            "subject": new_subject,
            "body": new_body,
            "send_as": send_as,
        }

    def send_composed_email(self, compose_id: str,
                            edited_body: str = None,
                            edited_subject: str = None,
                            attachments: list = None) -> Dict[str, Any]:
        """Send a previously composed and approved new email."""
        cached = self._compose_cache.get(compose_id)
        if not cached:
            return {"success": False, "error": "Entwurf nicht gefunden"}
        if cached.get("sent"):
            return {"success": False, "error": "Bereits gesendet"}

        to_addr = cached["to"]
        subject = edited_subject or cached["subject"]
        body = edited_body or cached["body"]
        send_as = cached.get("send_as", "ailey")

        if send_as == "ailey" or send_as == AILEY_EMAIL:
            # Ailey sends from her own account — use her own signature
            success = send_email_as_ailey(to_addr, subject, body, attachments=attachments,
                                          signature=AILEY_SIGNATURE_OWN)
            via = f"Ailey ({AILEY_EMAIL})"
        else:
            # send_as can be "simon" (legacy) or a specific email address
            # Ailey drafted this, Simon approved → Simon's signature with drafted note
            full_body = body.rstrip() + SIMON_SIGNATURE_DRAFTED
            if send_as == "simon":
                account = _find_simon_account()
            else:
                account = _find_simon_account(send_as)
            success = _send_smtp(account, to_addr, subject, full_body) if account else False
            via = f"SMTP ({account['email']})" if account else "SMTP (kein Account)"

        if success:
            cached["sent"] = True
            cached["subject"] = subject
            cached["body"] = body
            # Auto-save recipient to people glossary as email contact
            _auto_save_email_contact(to_addr)
            return {"success": True, "message": f"E-Mail an {to_addr} gesendet via {via}"}
        else:
            return {"success": False, "error": f"Fehler beim Senden via {via}"}

    # --- Ailey's own mailbox check (called from IdleThinker) ---------------

    def check_own_email(self) -> List[Dict[str, Any]]:
        """Check Ailey's own IMAP inbox for unread emails, process them.

        Returns a list of action reports (what she did with each mail).
        """
        emails = fetch_ailey_unread_emails(max_count=10)
        if not emails:
            return []

        generator = self.get_generator()
        if not generator:
            return []

        actions = []
        for em in emails:
            ehash = _email_hash(em)
            if ehash in self._seen:
                continue
            self._seen.add(ehash)

            # Filter spam
            if _is_spam_or_ad(em):
                mark_ailey_email_read(em.get("imap_uid", ""))
                actions.append({
                    "email_id": em["id"], "sender": em["sender"],
                    "subject": em["subject"], "action": "spam_filtered",
                })
                continue

            # Summarize
            result = summarize_email(em, generator)

            # Update People Glossary with sender of Ailey's own mail
            try:
                from . import people_glossary
                sender_raw = em.get("sender", "")
                if sender_raw:
                    info = people_glossary.extract_person_from_email(
                        sender_raw, em.get("subject", ""), em.get("body", "")[:500]
                    )
                    if info.get("name"):
                        people_glossary.upsert_person(
                            name=info["name"],
                            email=info.get("email", ""),
                            facts=info.get("facts", []),
                            source="email",
                        )
            except Exception:
                pass

            # Try autonomous reply (with optional RAG context)
            reply_text = draft_autonomous_reply(em, generator, core=self._core)

            if reply_text:
                # Extract reply-to address
                sender = em.get("sender", "")
                m_addr = re.search(r'<([^>]+)>', sender)
                to_addr = m_addr.group(1) if m_addr else sender
                subject = em.get("subject", "")

                sent = send_email_as_ailey(
                    to_addr=to_addr, subject="",
                    body=reply_text,
                    reply_to_message_id=em.get("id", ""),
                    in_reply_to_subject=subject,
                )

                action_entry = {
                    "email_id": em["id"], "sender": sender,
                    "subject": subject, "summary": result["summary"],
                    "action": "replied" if sent else "reply_failed",
                    "reply_to": to_addr, "reply_excerpt": reply_text[:200],
                }
            else:
                action_entry = {
                    "email_id": em["id"], "sender": em["sender"],
                    "subject": em["subject"], "summary": result["summary"],
                    "action": "read_only",
                }

            actions.append(action_entry)
            mark_ailey_email_read(em.get("imap_uid", ""))

            # ── Store email exchange to RAG for long-term memory ──
            try:
                if self._core:
                    _subj = em.get("subject", "Kein Betreff")
                    _sender = em.get("sender", "unbekannt")
                    _body = em.get("body", "")[:600]
                    _rag_title = f"E-Mail von {_sender}: {_subj}"
                    _rag_text = f"Von: {_sender}\nBetreff: {_subj}\n{_body}"
                    if reply_text:
                        _rag_text += f"\n\nAileys Antwort:\n{reply_text[:600]}"
                    self._core.rag_add(_rag_title, _rag_text, doc_type="email_exchange", user="Simon")
            except Exception:
                pass

            # Cache for later reference
            self._draft_cache[em.get("id", "")] = {
                "email": em, "notification": action_entry,
                "draft": reply_text, "draft_approved": True if reply_text else False,
                "sent": True if reply_text else False,
                "account": "ailey",
            }

            # Notify Simon about what she did
            if self.on_new_email:
                notif = {
                    "message_id": em.get("id", ""),
                    "sender": em.get("sender", ""),
                    "subject": em.get("subject", ""),
                    "date": em.get("date", ""),
                    "summary": result["summary"],
                    "needs_reply": False,
                    "account": "ailey",
                    "ailey_action": action_entry.get("action", ""),
                    "reply_excerpt": action_entry.get("reply_excerpt", ""),
                }
                try:
                    self.on_new_email(notif)
                except Exception:
                    pass

        if actions:
            _save_seen(self._seen)
        return actions

    def _run(self):
        # Initial delay to let the app start
        time.sleep(10)

        # ── Startup: check all accounts once ──────────────────────────────
        try:
            self._startup_mail_check()
        except Exception as e:
            print(f"[EmailMonitor] startup check error: {e}")

        while not self._stop_event.is_set():
            if self._enabled:
                try:
                    # First: try to process any deferred emails from when user was active
                    if self._deferred_emails and not self._is_user_active():
                        self._process_deferred_emails()
                    # Then: check for new mail
                    self._check_mail()
                except Exception as e:
                    print(f"[EmailMonitor] check error: {e}")

            self._stop_event.wait(CHECK_INTERVAL)

    def _startup_mail_check(self):
        """Run once at startup: check all accounts and Ailey's own inbox.
        Each email gets its own notification so the user can reply individually."""
        print("[EmailMonitor] ── Startup mail check ──")

        # Check Ailey's own inbox
        try:
            ailey_actions = self.check_own_email()
            if ailey_actions:
                replied = [a for a in ailey_actions if a.get("action") == "replied"]
                read_only = [a for a in ailey_actions if a.get("action") == "read_only"]
                if replied or read_only:
                    summary = ""
                    if replied:
                        summary += f"📧 Ailey hat {len(replied)} eigene Mail(s) beantwortet. "
                    if read_only:
                        summary += f"📧 Ailey hat {len(read_only)} eigene Mail(s) gelesen."
                    if self.on_new_email:
                        self.on_new_email({
                            "message_id": f"startup_ailey_{int(time.time())}",
                            "sender": "Ailey (Startup)",
                            "subject": "Eigene Mails verarbeitet",
                            "summary": summary.strip(),
                            "needs_reply": False,
                            "account": "system",
                            "ts": time.time(),
                            "dt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        })
        except Exception as e:
            print(f"[EmailMonitor] startup Ailey check error: {e}")

        # Check Simon's accounts — send individual notifications per email
        generator = self.get_generator()
        total_new = 0
        for account in SIMON_ACCOUNTS:
            try:
                emails = _fetch_imap_unread(account)
                for em in emails:
                    ehash = _email_hash(em)
                    if ehash in self._seen:
                        continue
                    if _is_spam_or_ad(em):
                        self._seen.add(ehash)
                        continue
                    self._seen.add(ehash)
                    total_new += 1

                    # Summarize with LLM if available, otherwise use raw subject
                    if generator:
                        self._summarize_and_notify(em, generator)
                    else:
                        # Lightweight fallback: cache + notify without LLM summary
                        notification = {
                            "message_id": em.get("id", ""),
                            "sender": em.get("sender", ""),
                            "subject": em.get("subject", ""),
                            "date": em.get("date", ""),
                            "summary": em.get("body", "")[:300],
                            "needs_reply": True,
                            "account": "simon",
                            "ts": time.time(),
                            "dt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }
                        self._draft_cache[em.get("id", "")] = {
                            "email": em,
                            "notification": notification,
                            "draft": None,
                            "reply_as": "simon",
                            "draft_approved": False,
                            "sent": False,
                            "account": "simon",
                        }
                        if self.on_new_email:
                            try:
                                self.on_new_email(notification)
                            except Exception:
                                pass
            except Exception as e:
                print(f"[EmailMonitor] startup check {account['email']} error: {e}")

        if total_new > 0:
            _save_seen(self._seen)
            print(f"[EmailMonitor] Startup: {total_new} neue Mail(s) verarbeitet")
        else:
            print("[EmailMonitor] Startup: keine neuen Mails")

    def _is_user_active(self) -> bool:
        """Check if Simon is currently chatting (last activity < 120s / 2 min)."""
        if not self._idle_thinker:
            return False  # no reference, assume idle — safe fallback
        idle_secs = time.time() - self._idle_thinker._last_user_activity
        return idle_secs < USER_IDLE_THRESHOLD

    def _process_deferred_emails(self):
        """Summarize emails that were deferred because user was active."""
        if not self._deferred_emails:
            return
        if not self._enabled:
            print("[EmailMonitor] Code-Mode active — skipping deferred email processing")
            return
        generator = self.get_generator()
        if not generator:
            return
        batch = list(self._deferred_emails)
        self._deferred_emails.clear()
        for email_item in batch:
            # Abort if code-mode was activated in the meantime
            if not self._enabled:
                self._deferred_emails.extend(batch[batch.index(email_item):])
                print(f"[EmailMonitor] Code-Mode activated, re-deferring {len(self._deferred_emails)} email(s)")
                return
            # Double-check user isn't active now
            if self._is_user_active():
                self._deferred_emails.extend(batch[batch.index(email_item):])
                print(f"[EmailMonitor] User active again, re-deferring {len(self._deferred_emails)} email(s)")
                return
            self._summarize_and_notify(email_item, generator)

    def _check_mail(self):
        """Fetch unread mails from Simon's IMAP accounts, filter, summarize."""
        if not self._enabled:
            print("[EmailMonitor] Code-Mode active — skipping mail check")
            return

        emails = fetch_unread_emails()
        if not emails:
            return

        generator = self.get_generator()
        if not generator:
            return

        new_count = 0
        for email_item in emails:
            ehash = _email_hash(email_item)
            if ehash in self._seen:
                continue

            self._seen.add(ehash)

            if _is_spam_or_ad(email_item):
                print(f"[EmailMonitor] Filtered (spam/ad): {email_item.get('subject', '')[:50]}")
                continue

            # If user is currently chatting, defer the LLM summary to avoid lock contention
            if self._is_user_active():
                self._deferred_emails.append(email_item)
                print(f"[EmailMonitor] User active — deferring: {email_item.get('subject', '')[:50]}")
                new_count += 1
                continue

            # If code-mode was activated mid-loop, defer remaining
            if not self._enabled:
                self._deferred_emails.append(email_item)
                print(f"[EmailMonitor] Code-Mode activated — deferring: {email_item.get('subject', '')[:50]}")
                new_count += 1
                continue

            self._summarize_and_notify(email_item, generator)
            new_count += 1

        if new_count > 0:
            _save_seen(self._seen)

    def _summarize_and_notify(self, email_item: Dict[str, str], generator):
        """Summarize a single email and push notification."""
        # Mark generation active so pause() can wait for lock release
        self._generating = True
        self._gen_done.clear()
        try:
            result = summarize_email(email_item, generator)
        finally:
            self._generating = False
            self._gen_done.set()

        # Update People Glossary with email sender info (only real people, not companies/noreply)
        try:
            from . import people_glossary
            sender = email_item.get("sender", "")
            subject = email_item.get("subject", "")
            body = email_item.get("body", "")[:500]
            if sender:
                sender_lower = sender.lower()
                # Skip commercial/noreply/automated senders
                _skip_patterns = [
                    "noreply", "no-reply", "donotreply", "do-not-reply",
                    "mailer-daemon", "postmaster", "newsletter", "marketing",
                    "support@", "info@", "service@", "billing@", "help@",
                    "notifications@", "updates@", "team@", "hello@",
                    "kontakt@", "shop@", "order@", "bestellung@",
                ]
                _skip_domains = [
                    "eis.de", "amazon.", "paypal.", "ebay.", "google.",
                    "facebook.", "instagram.", "twitter.", "linkedin.",
                    "newsletter.", "mailchimp.", "sendgrid.", "postmarkapp.",
                    "apple.com", "microsoft.com", "spotify.", "netflix.",
                    "zalando.", "otto.", "lidl.", "aldi.", "rewe.",
                    "dhl.", "hermes.", "dpd.", "ups.", "fedex.",
                ]
                is_commercial = any(p in sender_lower for p in _skip_patterns)
                is_commercial = is_commercial or any(d in sender_lower for d in _skip_domains)
                
                if not is_commercial:
                    info = people_glossary.extract_person_from_email(sender, subject, body)
                    if info.get("name"):
                        # Extra check: name should look like a real person name (2+ parts, no @)
                        name_parts = info["name"].strip().split()
                        looks_like_person = (
                            len(name_parts) >= 2 and
                            "@" not in info["name"] and
                            not any(c.isdigit() for c in info["name"]) and
                            len(info["name"]) < 50
                        )
                        if looks_like_person:
                            people_glossary.upsert_person(
                                name=info["name"],
                                email=info.get("email", ""),
                                facts=info.get("facts", []),
                                source="email",
                            )
        except Exception:
            pass

        notification = {
            "message_id": email_item.get("id", ""),
            "sender": email_item.get("sender", ""),
            "subject": email_item.get("subject", ""),
            "date": email_item.get("date", ""),
            "summary": result["summary"],
            "body": email_item.get("body", ""),
            "needs_reply": result["needs_reply"],
            "account": "simon",
            "ts": time.time(),
            "dt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        self._draft_cache[email_item.get("id", "")] = {
            "email": email_item,
            "notification": notification,
            "draft": None,
            "reply_as": "simon",
            "draft_approved": False,
            "sent": False,
            "account": "simon",
        }

        self._pending_emails.append(notification)

        self._notify_macos(email_item, result["summary"])

        if self.on_new_email:
            try:
                self.on_new_email(notification)
            except Exception:
                pass

        print(f"[EmailMonitor] Processed: {email_item.get('subject', '')[:50]}")

    def _notify_macos(self, email_item: Dict[str, str], summary: str):
        """Send macOS notification for a new email."""
        try:
            sender = email_item.get("sender", "Unbekannt")[:40].replace('"', "'")
            subject = email_item.get("subject", "")[:60].replace('"', "'")
            account = email_item.get("account", "simon")
            title = "📧 Aileys Mail" if account == "ailey" else "📧 Neue Mail"
            script = f'display notification "Von: {sender}\\n{subject}" with title "{title}" subtitle "Ailey hat sie gelesen" sound name "Tink"'
            subprocess.Popen(["osascript", "-e", script],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def scan_old_senders_to_glossary(self) -> Dict[str, Any]:
        """Retroactively scan all previously seen emails and add senders to the People Glossary.

        This reads recent emails from IMAP (both Simon's and Ailey's accounts) and registers
        each unique sender in the glossary. Useful for bootstrapping the glossary from history.
        """
        from . import people_glossary

        results: Dict[str, Any] = {"scanned": 0, "added": 0, "updated": 0, "errors": []}

        # Gather all emails from both mailboxes
        all_emails: List[Dict[str, str]] = []
        try:
            simon_emails = fetch_unread_emails(max_count=50)
            all_emails.extend(simon_emails)
        except Exception as e:
            results["errors"].append(f"Simon IMAP: {e}")
        try:
            ailey_emails = fetch_ailey_unread_emails(max_count=50)
            all_emails.extend(ailey_emails)
        except Exception as e:
            results["errors"].append(f"Ailey IMAP: {e}")

        # Also include any emails still in the draft cache
        for msg_id, cached in self._draft_cache.items():
            em = cached.get("email")
            if em and isinstance(em, dict):
                all_emails.append(em)

        seen_emails_set: set = set()
        for em in all_emails:
            sender = em.get("sender", "")
            if not sender:
                continue
            # Deduplicate by email address
            addr_m = re.search(r'<([^>]+)>', sender)
            addr = addr_m.group(1).lower() if addr_m else sender.lower()
            if addr in seen_emails_set:
                continue
            seen_emails_set.add(addr)

            results["scanned"] += 1
            try:
                info = people_glossary.extract_person_from_email(
                    sender, em.get("subject", ""), em.get("body", "")[:500]
                )
                if info.get("name"):
                    existing = people_glossary.get_person(info["name"]) or people_glossary.get_person_by_email(info.get("email", ""))
                    people_glossary.upsert_person(
                        name=info["name"],
                        email=info.get("email", ""),
                        facts=info.get("facts", []),
                        source="email",
                    )
                    if existing:
                        results["updated"] += 1
                    else:
                        results["added"] += 1
            except Exception as e:
                results["errors"].append(f"Sender '{sender[:40]}': {e}")

        return results

    def get_recent_email_summaries(self, limit: int = 5) -> List[str]:
        """Return compact summaries of recent email notifications for injection into idle reflections."""
        summaries = []
        # From draft cache (recent processed emails)
        cached = sorted(self._draft_cache.values(), key=lambda c: c.get("notification", {}).get("ts", 0), reverse=True)
        for c in cached[:limit]:
            notif = c.get("notification", {})
            if notif:
                sender = notif.get("sender", "?")[:40]
                subject = notif.get("subject", "?")[:60]
                summary = notif.get("summary", "")[:150]
                summaries.append(f"E-Mail von {sender}: {subject} — {summary}")
        return summaries
