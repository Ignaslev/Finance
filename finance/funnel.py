"""Numbers for the staff funnel page: where new users drop off, why uploads fail, how often the AI is corrected."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, F, Q
from django.utils import timezone

from .models import AiRunItem, ImportBatch, PdfImportJob, Transaction, UploadAttempt
from .sample_data import real_transactions
from .tracking import FAILED_OUTCOMES


def signup_funnel(since):
    """Steps for users who registered since `since`, each a subset of the previous one's audience."""
    cohort = get_user_model().objects.filter(date_joined__gte=since)
    ids = cohort.values("id")
    tried = (
        set(UploadAttempt.objects.filter(user__in=ids).values_list("user_id", flat=True))
        | set(ImportBatch.objects.filter(user__in=ids).values_list("user_id", flat=True))
        | set(PdfImportJob.objects.filter(user__in=ids).values_list("user_id", flat=True))
    )
    with_data = set(real_transactions(Transaction.objects.filter(user__in=ids, is_deleted=False)).values_list("user_id", flat=True))
    steps = [
        ("registered", "Užsiregistravo", cohort.count()),
        ("activated", "Aktyvavo paskyrą", cohort.filter(is_active=True).count()),
        ("logged_in", "Prisijungė", cohort.filter(last_login__isnull=False).count()),
        ("tried_upload", "Bandė įkelti išrašą", len(tried)),
        ("has_data", "Turi operacijų", len(with_data)),
        ("returned", "Grįžo kitą dieną", cohort.filter(id__in=with_data, last_active_at__gte=F("date_joined") + timedelta(days=1)).count()),
    ]
    total = steps[0][2] or 0
    rows, previous = [], None
    for key, label, count in steps:
        rows.append({
            "key": key,
            "label": label,
            "count": count,
            "pct_of_registered": round(count / total * 100, 1) if total else 0.0,
            "lost_from_previous": (previous - count) if previous is not None else None,
        })
        previous = count
    return rows


def funnel_by_source(since, limit=8):
    """Registrations and users with data per acquisition source (UTM first touch)."""
    users = get_user_model().objects.filter(date_joined__gte=since)
    with_data = real_transactions(Transaction.objects.filter(is_deleted=False)).values("user_id")
    rows = (
        users.values("profile__acquisition_source")
        .annotate(registered=Count("id"), with_data=Count("id", filter=Q(id__in=with_data)))
    )
    merged = {}  # empty source and "no profile" are the same thing: unknown
    for r in rows:
        source = r["profile__acquisition_source"] or "(tiesiogiai / nežinoma)"
        bucket = merged.setdefault(source, {"source": source, "registered": 0, "with_data": 0})
        bucket["registered"] += r["registered"]
        bucket["with_data"] += r["with_data"]
    return sorted(merged.values(), key=lambda b: -b["registered"])[:limit]


def upload_outcomes(since):
    qs = UploadAttempt.objects.filter(created_at__gte=since)
    total = qs.count()
    failed = qs.filter(outcome__in=FAILED_OUTCOMES).count()
    return {
        "total": total,
        "failed": failed,
        "failure_rate": round(failed / total * 100, 1) if total else 0.0,
        "by_outcome": list(qs.values("outcome").annotate(n=Count("id")).order_by("-n")),
        "by_file_type": list(qs.values("file_type").annotate(
            n=Count("id"), failed=Count("id", filter=Q(outcome__in=FAILED_OUTCOMES))).order_by("-n")),
        "by_source": list(qs.values("source").annotate(n=Count("id")).order_by("-n")),
        "recent_failures": list(
            qs.filter(outcome__in=FAILED_OUTCOMES).select_related("user").order_by("-created_at")[:20]
        ),
        "pdf_jobs": list(PdfImportJob.objects.filter(created_at__gte=since).values("status").annotate(n=Count("id")).order_by("-n")),
        "pdf_balance_mismatch": qs.filter(file_type="pdf", detail__contains="mismatch").count(),
    }


def ai_correction_rate(since):
    """Of the categories the AI applied, how many did users later change? Free, no API calls.

    A row counts as corrected when the user has since set it (category_source == "user")
    to a different category than the one the AI applied.
    """
    items = AiRunItem.objects.filter(action="applied", run__started_at__gte=since, new_category_fk__isnull=False)
    applied = items.count()
    corrected_qs = items.filter(transaction__category_source="user").exclude(transaction__category_fk=F("new_category_fk"))
    corrected = corrected_qs.count()
    top = list(
        corrected_qs.values("new_category_fk__name", "transaction__category_fk__name")
        .annotate(n=Count("id")).order_by("-n")[:10]
    )
    return {
        "applied": applied,
        "corrected": corrected,
        "correction_rate": round(corrected / applied * 100, 1) if applied else 0.0,
        "top_corrections": top,  # AI category -> user's category
    }


def window_start(days):
    return timezone.now() - timedelta(days=days)
