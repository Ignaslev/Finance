"""Reminder emails: a monthly "upload this month's statement" and one nudge after sign-up.

Sent by `manage.py moneycoach_send_reminders` (run daily). Every email is in the user's chosen
language, comes from DEFAULT_FROM_EMAIL and carries a one-click unsubscribe link. The monthly one
opens with a spending recap of the newest fully uploaded month, when there is one.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.utils import timezone

from .insights import MONTHS_EN, MONTHS_LT_GENITIVE, headline, last_complete_month, money, monthly_summary, pct
from .models import ImportBatch, Transaction, UserProfile
from .sample_data import real_transactions

UNSUBSCRIBE_SALT = "moneycompass-reminder-unsubscribe"
MONTHLY_FROM_DAY = 3          # last month's statement is complete by then
ACTIVE_WITHIN_DAYS = 180      # don't wake long-dormant accounts with monthly mail
NUDGE_AFTER_DAYS = 2          # first-upload nudge window after sign-up...
NUDGE_UNTIL_DAYS = 14         # ...so older sign-ups aren't all emailed on deploy


def unsubscribe_token(user):
    return signing.dumps({"u": user.pk}, salt=UNSUBSCRIBE_SALT)


def user_from_token(token):
    try:
        data = signing.loads(token, salt=UNSUBSCRIBE_SALT)
    except signing.BadSignature:
        return None
    return get_user_model().objects.filter(pk=data.get("u")).first()


def _month_start(now):
    local = timezone.localtime(now)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def monthly_due(now=None):
    """Users with data who haven't uploaded since the 1st and weren't reminded this month."""
    now = now or timezone.now()
    if timezone.localtime(now).day < MONTHLY_FROM_DAY:
        return []
    start = _month_start(now)
    with_data = real_transactions(Transaction.objects.filter(is_deleted=False)).values("user_id")
    uploaded_this_month = ImportBatch.objects.filter(created_at__gte=start, undone_at__isnull=True).values("user_id")
    profiles = (
        UserProfile.objects.select_related("user")
        .filter(reminder_emails=True, user__is_active=True, user__id__in=with_data,
                user__last_active_at__gte=now - timedelta(days=ACTIVE_WITHIN_DAYS),
                account_delete_scheduled_for__isnull=True)
        .exclude(user__id__in=uploaded_this_month)
        .exclude(last_monthly_reminder_at__gte=start)
    )
    return [p for p in profiles if p.user.email]


def nudge_due(now=None):
    """Activated sign-ups from the last two weeks who never uploaded anything."""
    now = now or timezone.now()
    with_data = real_transactions(Transaction.objects.filter(is_deleted=False)).values("user_id")
    profiles = (
        UserProfile.objects.select_related("user")
        .filter(reminder_emails=True, user__is_active=True, first_upload_nudge_at__isnull=True,
                user__date_joined__lte=now - timedelta(days=NUDGE_AFTER_DAYS),
                user__date_joined__gte=now - timedelta(days=NUDGE_UNTIL_DAYS),
                account_delete_scheduled_for__isnull=True)
        .exclude(user__id__in=with_data)
    )
    return [p for p in profiles if p.user.email]


def _recap(profile, now, lt):
    """Spending recap for the newest fully uploaded month: (summary, lines, reports_url) or None.

    Only a month the user's data fully covers is used, so a half-uploaded month never reads as
    "you spent 80% less".
    """
    month = last_complete_month(profile.user, now.date())
    if not month:
        return None
    s = monthly_summary(profile.user, month[0], lt=lt)
    if not s["spent"]:
        return None
    lines = [headline(s, lt)]
    move = s["biggest_move"]
    if move:
        sign = "+" if move["change"] > 0 else "−"
        change = f"{sign}{money(abs(move['change']), lt)} ({sign}{pct(abs(move['pct']), lt)})"
        lines.append(f"Labiausiai pasikeitė „{move['name']}“: {change}." if lt
                     else f"Biggest change: “{move['name']}” {change}.")
    top = ", ".join(f"{c['name']} {money(c['total'], lt)}" for c in s["categories"][:3])
    if top:
        lines.append(f"Daugiausia išleista: {top}." if lt else f"Most spent on: {top}.")
    reports_url = f"{settings.SITE_URL}{reverse('reports')}?m={s['start']:%Y-%m}"
    return s, lines, reports_url


def _join(*paragraphs):
    return "\n\n".join(p for p in paragraphs if p) + "\n"


def build_email(profile, kind, now=None):
    """Return (subject, text, unsubscribe_url) in the user's chosen language. kind: 'monthly' | 'nudge'."""
    now = timezone.localtime(now or timezone.now())
    lt = (profile.preferred_language or "lt") != "en"
    site = settings.SITE_URL
    app_link = f"{site}{reverse('overview')}"
    unsubscribe = f"{site}{reverse('reminder_unsubscribe', args=[unsubscribe_token(profile.user)])}"
    previous_month = (now.replace(day=1) - timedelta(days=1)).month - 1
    recap = _recap(profile, now, lt) if kind == "monthly" else None
    up_to_date = bool(recap) and recap[0]["start"].month - 1 == previous_month

    if kind == "monthly" and up_to_date:
        # Last month is already fully uploaded: the email is the overview itself.
        _, lines, reports_url = recap
        subject = lines[0].rstrip(".")
        text = _join(
            "Sveiki!" if lt else "Hi!",
            "\n".join(lines),
            ("Visą apžvalgą ir patarimus rasi čia:\n" if lt else "The full overview and tips are here:\n") + reports_url,
            "MoneyCompass",
            f"Nebenori šių laiškų? Atsisakyk čia: {unsubscribe}" if lt
            else f"Don't want these emails? Unsubscribe here: {unsubscribe}",
        )
    elif kind == "monthly" and lt:
        subject = f"Laikas įkelti {MONTHS_LT_GENITIVE[previous_month]} mėnesio išrašą"
        text = _join(
            "Sveiki!",
            ("\n".join(recap[1]) + f"\nVisa apžvalga: {recap[2]}") if recap else "",
            f"{MONTHS_LT_GENITIVE[previous_month].capitalize()} mėnuo baigėsi. Atsisiųsk banko išrašą (PDF arba CSV) "
            "ir įkelk jį į MoneyCompass – pamatysi, kur keliavo pinigai, o operacijas suskirstysime automatiškai.",
            app_link,
            "Tai užtrunka apie minutę.",
            "MoneyCompass",
            f"Nebenori šių priminimų? Atsisakyk čia: {unsubscribe}",
        )
    elif kind == "monthly":
        subject = f"Time to upload your {MONTHS_EN[previous_month]} statement"
        text = _join(
            "Hi!",
            ("\n".join(recap[1]) + f"\nFull overview: {recap[2]}") if recap else "",
            f"{MONTHS_EN[previous_month]} is over. Download your bank statement (PDF or CSV) and upload it to "
            "MoneyCompass to see where your money went; we categorize the transactions automatically.",
            app_link,
            "It takes about a minute.",
            "MoneyCompass",
            f"Don't want these reminders? Unsubscribe here: {unsubscribe}",
        )
    elif lt:
        subject = "Pažiūrėkime, kur dingsta tavo pinigai"
        text = (
            "Sveiki!\n\n"
            "Užsiregistravai MoneyCompass, bet dar neįkėlei banko išrašo. Tai užtrunka apie minutę: "
            "atsisiųsk išrašą iš savo banko (PDF iš bet kurio banko arba CSV) ir įkelk jį čia:\n\n"
            f"{app_link}\n\n"
            "Operacijas suskirstysime automatiškai – nieko žymėti nereikia.\n\n"
            "MoneyCompass\n\n"
            f"Nebenori laiškų? Atsisakyk čia: {unsubscribe}\n"
        )
    else:
        subject = "Let's see where your money goes"
        text = (
            "Hi!\n\n"
            "You signed up for MoneyCompass but haven't uploaded a statement yet. It takes about a minute: "
            "download a statement from your bank (PDF from any bank, or CSV) and upload it here:\n\n"
            f"{app_link}\n\n"
            "We categorize the transactions automatically – no setup needed.\n\n"
            "MoneyCompass\n\n"
            f"Don't want these emails? Unsubscribe here: {unsubscribe}\n"
        )
    return subject, text, unsubscribe


def send_reminder(profile, kind, now=None, connection=None):
    subject, text, unsubscribe = build_email(profile, kind, now)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[profile.user.email],
        headers={"List-Unsubscribe": f"<{unsubscribe}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
        connection=connection,
    )
    message.send(fail_silently=False)
    field = "last_monthly_reminder_at" if kind == "monthly" else "first_upload_nudge_at"
    UserProfile.objects.filter(pk=profile.pk).update(**{field: now or timezone.now()})
