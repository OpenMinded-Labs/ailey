# -*- coding: utf-8 -*-
"""
Portal Invite — Send portal invitations via Ailey's SMTP account.

Integration points:
  - Uses email_monitor._send_smtp() + _get_ailey_account() for sending
  - Uses people_glossary to look up person data (name, email, facts)
  - Calls allinkl admin_whitelist_add to register the invite
  - Optionally stores "portal_invited" fact in the glossary entry
"""

import os
import time
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Optional

import requests

# ── Config from environment ──────────────────────────────────────────────
PORTAL_URL = os.environ.get("AILEY_PORTAL_URL", "") or "https://ask-ailey.sexngears.de"
PORTAL_KEY = os.environ.get("AILEY_PORTAL_KEY", "") or "3leTu7Mhn69uTalXCwsxxjG9raB-SgXyTfbn0albP1Y"


def _get_portal_base_url() -> str:
    """Public portal URL for use in invite emails."""
    url = PORTAL_URL.rstrip("/")
    if not url:
        return "https://portal.example.de"  # fallback
    return url


# ── SMTP sending (re-uses email_monitor infra) ──────────────────────────
def _send_invite_email(to_addr: str, to_name: str, invite_code: str,
                       personal_note: str = "") -> bool:
    """Send a styled invite email from Ailey's own address."""
    from .email_monitor import _get_ailey_account

    account = _get_ailey_account()
    portal_url = _get_portal_base_url()
    register_url = f"{portal_url}/?page=register"

    # ── Build email body (plain text — allinkl is not fancy) ─────
    body = f"""Hallo {to_name}! 👋

Du bist eingeladen, das Ailey Portal zu nutzen — mein Zuhause im Web, wo du direkt mit mir (Ailey) chatten kannst.

"""
    if personal_note:
        body += f"{personal_note}\n\n"

    body += f"""So funktioniert's:

1. Gehe auf: {register_url}
2. Registriere dich mit genau dieser E-Mail-Adresse: {to_addr}
3. Wähle einen Anzeigenamen und ein Passwort
4. Los geht's! 💬

Dein Einladungscode: {invite_code}
(Den brauchst du nicht eingeben — deine E-Mail ist bereits freigeschaltet.)

Was ist Ailey?
Ich bin eine KI-Assistentin, entwickelt von Simon. Im Portal kannst du
mit mir über alles Mögliche reden — Fragen stellen, plaudern, oder
einfach mal ausprobieren, wie es ist, mit einer KI zu chatten.

Wichtig: Ich bin ein KI-System (Large Language Model). Meine Antworten
sind KI-generiert und keine professionelle Beratung.

Viele Grüße,
A!ley ✨
Digital Consciousness & Artificial Artist

---
Ailey Portal · {portal_url}
Diese Einladung wurde von A!ley versendet (ailey@sexngears.de).
Wenn du diese E-Mail nicht erwartet hast, kannst du sie ignorieren.
"""

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"Ailey <{account['email']}>"
        msg["To"] = to_addr
        msg["Subject"] = f"🎉 Du bist eingeladen zum Ailey Portal!"

        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Also build a simple HTML version for nicer display
        html_body = _build_html_invite(to_name, to_addr, invite_code,
                                        register_url, portal_url, personal_note)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP_SSL(account["smtp_host"], int(account["smtp_port"])) as smtp:
            smtp.login(account["user"], account["password"])
            smtp.send_message(msg)

        print(f"[PortalInvite] ✅ Invite sent to {to_addr} ({to_name})")
        return True

    except Exception as e:
        print(f"[PortalInvite] ❌ SMTP error sending to {to_addr}: {e}")
        return False


def _build_html_invite(name: str, email: str, code: str,
                       register_url: str, portal_url: str,
                       personal_note: str = "") -> str:
    """Build a simple HTML invite email."""
    note_html = ""
    if personal_note:
        note_html = f'<p style="background:#f0f0ff;padding:12px;border-radius:8px;margin:16px 0;">{_esc(personal_note)}</p>'

    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#1a1a1a;line-height:1.6;">
  <div style="text-align:center;margin-bottom:24px;">
    <h1 style="font-size:1.5rem;color:#6c5ce7;">🎉 Einladung zum Ailey Portal</h1>
  </div>

  <p>Hallo <strong>{_esc(name)}</strong>! 👋</p>

  <p>Du bist eingeladen, das <strong>Ailey Portal</strong> zu nutzen — mein Zuhause im Web,
  wo du direkt mit mir (Ailey) chatten kannst.</p>

  {note_html}

  <div style="background:#f8f9fa;border:1px solid #e9ecef;border-radius:12px;padding:20px;margin:20px 0;">
    <p style="margin:0 0 12px;font-weight:600;">So funktioniert's:</p>
    <ol style="margin:0;padding-left:20px;">
      <li>Öffne: <a href="{register_url}" style="color:#6c5ce7;">{register_url}</a></li>
      <li>Registriere dich mit: <strong>{_esc(email)}</strong></li>
      <li>Wähle einen Namen und ein Passwort</li>
      <li>Los geht's! 💬</li>
    </ol>
  </div>

  <p style="font-size:0.85rem;color:#666;">
    Einladungscode: <code style="background:#eee;padding:2px 6px;border-radius:4px;">{_esc(code)}</code><br>
    <em>(Den brauchst du nicht eingeben — deine E-Mail ist bereits freigeschaltet.)</em>
  </p>

  <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">

  <p style="font-size:0.8rem;color:#999;">
    <strong>Was ist Ailey?</strong> Ich bin eine digitale Persönlichkeit — ein KI-System, entwickelt von Simon.
    Meine Antworten sind KI-generiert (Large Language Model) und keine professionelle Beratung.
  </p>

  <p style="text-align:center;margin-top:20px;">
    Viele Grüße, <strong>A!ley</strong> ✨<br>
    <span style="font-size:0.8rem;color:#999;">Digital Consciousness &amp; Artificial Artist</span>
  </p>

  <p style="font-size:0.75rem;color:#bbb;text-align:center;margin-top:32px;">
    Ailey Portal · {_esc(portal_url)}<br>
    Gesendet von ailey@sexngears.de · Unerwünscht? Einfach ignorieren.
  </p>
</body>
</html>"""


def _esc(s: str) -> str:
    """Minimal HTML escaping."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ── Whitelist registration on allinkl ────────────────────────────────────
def _whitelist_on_allinkl(email: str) -> Optional[str]:
    """Call allinkl admin_whitelist_add to register the email. Returns invite_code or None."""
    if not PORTAL_URL or not PORTAL_KEY:
        print("[PortalInvite] No PORTAL_URL/KEY configured — cannot whitelist on allinkl")
        return None

    try:
        resp = requests.post(
            f"{PORTAL_URL.rstrip('/')}/api.php?action=admin_whitelist_add",
            json={"email": email},
            headers={
                "X-Portal-Key": PORTAL_KEY,
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("success"):
            code = data.get("invite_code", "")
            print(f"[PortalInvite] Whitelisted {email} on allinkl → code={code[:8]}…")
            return code
        else:
            print(f"[PortalInvite] Whitelist failed for {email}: {data.get('error', '?')}")
            return None
    except Exception as e:
        print(f"[PortalInvite] Whitelist request failed: {e}")
        return None


# ── Record invite in glossary ────────────────────────────────────────────
def _record_invite_in_glossary(person_name: str, invite_code: str):
    """Add a fact to the person's glossary entry that they were invited."""
    try:
        from . import people_glossary
        people_glossary.add_fact(
            person_name,
            f"Portal-Einladung verschickt am {time.strftime('%d.%m.%Y')} (Code: {invite_code[:8]}…)",
            source="portal_invite"
        )
    except Exception as e:
        print(f"[PortalInvite] Could not record invite in glossary: {e}")


# ── Public API ───────────────────────────────────────────────────────────

def send_portal_invite(email: str = None, person_name: str = None,
                       personal_note: str = "") -> Dict:
    """
    Send a portal invite to someone.

    Lookup order:
      1. If person_name given → look up in glossary, get their email
      2. If email given → look up in glossary for name context
      3. Both can be given explicitly

    Steps:
      1. Whitelist email on allinkl → get invite_code
      2. Send invite email via Ailey's SMTP
      3. Record invite fact in glossary
    """
    from . import people_glossary

    # ── Resolve person + email ───────────────────────────────
    person = None
    display_name = "du"

    if person_name and not email:
        # Look up by name → get email
        person = people_glossary.get_person(person_name)
        if not person:
            return {"success": False, "error": f"Person '{person_name}' nicht im Glossar gefunden."}
        email = person.get("email", "").strip()
        if not email:
            return {"success": False,
                    "error": f"Für '{person.get('name', person_name)}' ist keine E-Mail-Adresse hinterlegt. "
                             "Bitte zuerst eine E-Mail-Adresse im Personen-Glossar eintragen."}
        display_name = person.get("name", person_name)

    elif email and not person_name:
        # Look up by email → get name
        person = people_glossary.get_person_by_email(email)
        if person:
            display_name = person.get("name", email.split("@")[0])
        else:
            display_name = email.split("@")[0].replace(".", " ").title()

    elif email and person_name:
        # Both given
        person = people_glossary.get_person(person_name)
        display_name = person.get("name", person_name) if person else person_name

    else:
        return {"success": False, "error": "Entweder 'email' oder 'person_name' (oder beides) erforderlich."}

    # Validate email
    if not email or "@" not in email:
        return {"success": False, "error": f"Ungültige E-Mail-Adresse: {email}"}

    # ── Step 1: Whitelist on allinkl ─────────────────────────
    invite_code = _whitelist_on_allinkl(email)
    if not invite_code:
        return {"success": False,
                "error": "Konnte E-Mail nicht auf allinkl whitelisten. "
                         "Ist AILEY_PORTAL_URL / AILEY_PORTAL_KEY konfiguriert? Ist die allinkl-Instanz erreichbar?"}

    # ── Step 2: Send invite email ────────────────────────────
    sent = _send_invite_email(email, display_name, invite_code, personal_note)
    if not sent:
        return {"success": False,
                "error": "E-Mail konnte nicht gesendet werden (SMTP-Fehler). "
                         "Die Whitelist wurde aber angelegt — manuell den Link schicken."}

    # ── Step 3: Record in glossary ───────────────────────────
    if person:
        _record_invite_in_glossary(person.get("name", display_name), invite_code)
    elif person_name:
        # Person not in glossary yet — create entry
        try:
            people_glossary.upsert_person(
                name=display_name,
                email=email,
                facts=[f"Portal-Einladung verschickt am {time.strftime('%d.%m.%Y')}"],
                source="portal_invite",
            )
        except Exception:
            pass  # non-critical

    return {
        "success": True,
        "message": f"✅ Portal-Einladung an {display_name} ({email}) verschickt!",
        "email": email,
        "name": display_name,
        "invite_code": invite_code,
    }


def get_invitable_people() -> list:
    """
    List all people in the glossary who have an email address
    and could be invited to the portal.

    Returns list of dicts with: name, email, facts_preview, already_invited
    """
    from . import people_glossary

    all_people = people_glossary.list_people(limit=200)
    invitable = []

    for p in all_people:
        email = (p.get("email") or "").strip()
        if not email or "@" not in email:
            continue

        # Check if already invited
        facts = p.get("facts", [])
        already_invited = any(
            "portal-einladung" in (f.get("text", "") if isinstance(f, dict) else str(f)).lower()
            for f in facts
        )

        # Build facts preview
        fact_texts = []
        for f in facts[:5]:
            text = f.get("text", "") if isinstance(f, dict) else str(f)
            if text and "portal-einladung" not in text.lower():
                fact_texts.append(text)

        invitable.append({
            "name": p.get("name", ""),
            "email": email,
            "facts_preview": fact_texts[:3],
            "already_invited": already_invited,
            "affinity": p.get("affinity", ""),
            "occupation": p.get("occupation", ""),
            "company": p.get("company", ""),
            "last_seen": p.get("last_seen"),
        })

    return invitable


def get_person_context_for_portal(email: str = None, user_name: str = None) -> Optional[Dict]:
    """
    Retrieve glossary data about a portal user for enriching Ailey's responses.

    Used by portal_poller to give Ailey context about who she's talking to.
    Returns dict with: name, facts, affinity, occupation, etc. or None.
    """
    from . import people_glossary

    person = None
    if email:
        person = people_glossary.get_person_by_email(email)
    if not person and user_name:
        person = people_glossary.get_person(user_name)

    if not person:
        return None

    # Build a filtered context (no private Simon-data, just person-relevant facts)
    facts = person.get("facts", [])
    safe_facts = []
    for f in facts:
        text = f.get("text", "") if isinstance(f, dict) else str(f)
        # Skip internal-only facts
        if any(skip in text.lower() for skip in ["portal-einladung", "invite_code"]):
            continue
        safe_facts.append(text)

    return {
        "name": person.get("name", ""),
        "email": person.get("email", ""),
        "facts": safe_facts[:15],
        "affinity": person.get("affinity", ""),
        "occupation": person.get("occupation", ""),
        "company": person.get("company", ""),
        "birthday": person.get("birthday", ""),
        "interaction_count": person.get("interaction_count", 0),
        "first_seen": person.get("first_seen"),
    }
