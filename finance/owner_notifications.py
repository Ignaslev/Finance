import logging

from django.core.mail import mail_admins
from django.utils import timezone


logger = logging.getLogger(__name__)


def _send_owner_alert(subject, lines):
    body = "\n".join(str(line) for line in lines if line is not None)
    try:
        mail_admins(
            subject=f"MoneyCompass: {subject}",
            message=body,
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Could not send MoneyCompass owner alert: %s", subject)
        return False


def notify_registration(user, profile):
    return _send_owner_alert(
        "new registration",
        [
            f"User ID: {user.pk}",
            f"Email: {user.email}",
            f"Name: {user.get_full_name() or '-'}",
            f"Language: {profile.preferred_language or '-'}",
            f"Beta user: {'yes' if profile.is_beta_tester else 'no'}",
            f"Registered at: {timezone.now().isoformat()}",
        ],
    )


def notify_activation(user):
    return _send_owner_alert(
        "account activated",
        [
            f"User ID: {user.pk}",
            f"Email: {user.email}",
            f"Name: {user.get_full_name() or '-'}",
            f"Activated at: {timezone.now().isoformat()}",
        ],
    )


def notify_paid_subscription(profile):
    return _send_owner_alert(
        "paid subscription activated",
        [
            f"User ID: {profile.user_id}",
            f"Email: {profile.user.email}",
            f"Name: {profile.user.get_full_name() or '-'}",
            f"Plan: {profile.plan_interval or '-'}",
            f"Status: {profile.subscription_status}",
            f"Activated at: {timezone.now().isoformat()}",
        ],
    )
