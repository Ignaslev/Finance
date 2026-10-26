"""Invisible bot checks for the registration form: a honeypot field and a minimum fill time.

Real visitors never see the honeypot and take longer than a few seconds to fill in name, email
and two passwords. Simple form-filling bots do both wrong.
"""
import time

from django.conf import settings
from django.core import signing

HONEYPOT_FIELD = "website"
STAMP_FIELD = "form_started"
STAMP_SALT = "moneycompass-register-form"


def stamp():
    """Signed 'form shown at' time for the hidden field, so it can't be faked."""
    return signing.dumps(time.time(), salt=STAMP_SALT)


def check(post):
    """None when the submission looks human, else 'honeypot' or 'too_fast'."""
    if (post.get(HONEYPOT_FIELD) or "").strip():
        return "honeypot"
    min_seconds = getattr(settings, "REGISTRATION_MIN_FILL_SECONDS", 3)
    if min_seconds <= 0:
        return None
    try:
        started = float(signing.loads(post.get(STAMP_FIELD) or "", salt=STAMP_SALT))
    except (signing.BadSignature, TypeError, ValueError):
        return "too_fast"
    return "too_fast" if time.time() - started < min_seconds else None
