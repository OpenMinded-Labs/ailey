# -*- coding: utf-8 -*-
"""
Portal API — Flask Blueprint with local endpoints.

In the polling architecture, Ailey Core is the ACTIVE side:
  - It polls allinkl for pending messages
  - It pushes replies back to allinkl
  - No incoming connections needed (no tunnel!)

This Blueprint provides local health/monitoring + invite endpoints:
  GET  /portal/health        — Health check + poller stats
  GET  /portal/queue-info    — Poller statistics
  POST /portal/delete-user   — DSGVO delete (can also be triggered via poller)
  POST /portal/invite        — Send portal invite via Ailey's SMTP
  GET  /portal/invitable     — List people with emails who can be invited
"""

import os
import time
from flask import Blueprint, request, jsonify

portal_bp = Blueprint('portal', __name__, url_prefix='/portal')

PORTAL_KEY = os.environ.get('AILEY_PORTAL_KEY', '')


def _check_portal_key() -> bool:
    if not PORTAL_KEY:
        return True
    return request.headers.get('X-Portal-Key') == PORTAL_KEY


def _auth_error():
    return jsonify({"success": False, "error": "Unauthorized"}), 401


# ---------------------------------------------------------------------------
# /portal/health
# ---------------------------------------------------------------------------
@portal_bp.route('/health', methods=['GET'])
def portal_health():
    """Health check with poller stats."""
    if not _check_portal_key():
        return _auth_error()

    from ailey_system.portal_poller import get_portal_poller
    poller = get_portal_poller()
    return jsonify({
        "status": "ok",
        "architecture": "polling",
        "poller": poller.get_stats(),
        "timestamp": time.time(),
    })


# ---------------------------------------------------------------------------
# /portal/queue-info
# ---------------------------------------------------------------------------
@portal_bp.route('/queue-info', methods=['GET'])
def portal_queue_info():
    """Poller statistics for monitoring."""
    if not _check_portal_key():
        return _auth_error()

    from ailey_system.portal_poller import get_portal_poller
    poller = get_portal_poller()
    return jsonify({"success": True, **poller.get_stats()})


# ---------------------------------------------------------------------------
# /portal/delete-user (kept for direct DSGVO calls)
# ---------------------------------------------------------------------------
@portal_bp.route('/delete-user', methods=['POST'])
def portal_delete_user():
    """DSGVO: Delete/anonymize a user's data on Ailey side."""
    if not _check_portal_key():
        return _auth_error()

    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id", "")
    user_name = data.get("user_name", "")

    if not user_id:
        return jsonify({"success": False, "error": "user_id is required"}), 400

    deleted = []
    if user_name:
        try:
            from ailey_system import people_glossary
            person = people_glossary.get_person(user_name)
            if person and person.get("source") == "portal":
                people_glossary.remove_person(user_name)
                deleted.append("people_glossary")
        except Exception as e:
            print(f"[Portal] glossary cleanup failed: {e}")

    return jsonify({"success": True, "deleted": deleted})


# ---------------------------------------------------------------------------
# /portal/invite — Send a portal invite email
# ---------------------------------------------------------------------------
@portal_bp.route('/invite', methods=['POST'])
def portal_invite():
    """Send a portal invite to someone (via glossary name or email).

    Body JSON:
      - person_name: str (optional) — look up email from glossary
      - email: str (optional) — direct email to invite
      - personal_note: str (optional) — personal message to include
    """
    data = request.get_json(force=True, silent=True) or {}
    person_name = data.get("person_name", "").strip()
    email = data.get("email", "").strip()
    personal_note = data.get("personal_note", "").strip()

    if not person_name and not email:
        return jsonify({"success": False, "error": "person_name oder email erforderlich"}), 400

    from .portal_invite import send_portal_invite
    result = send_portal_invite(
        email=email or None,
        person_name=person_name or None,
        personal_note=personal_note,
    )
    status = 200 if result.get("success") else 400
    return jsonify(result), status


# ---------------------------------------------------------------------------
# /portal/invitable — List people who can be invited
# ---------------------------------------------------------------------------
@portal_bp.route('/invitable', methods=['GET'])
def portal_invitable():
    """List all people in the glossary who have an email and could be invited."""
    from .portal_invite import get_invitable_people
    people = get_invitable_people()
    return jsonify({"success": True, "people": people, "count": len(people)})
