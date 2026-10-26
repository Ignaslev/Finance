"""Upload tracking for the staff funnel, plus consent-gated GA4 events.

Tracking must never break an upload, so every write is best-effort.
"""
import logging

from django.urls import reverse

from .models import ImportBatch, UploadAttempt

logger = logging.getLogger(__name__)

GA_SESSION_KEY = "ga_pending_events"
FAILED_OUTCOMES = {"unrecognised", "wrong_bank", "too_large", "too_many_rows", "daily_limit", "error", "pdf_unavailable"}


def file_type_of(filename):
    ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    return ext if ext in {"pdf", "csv", "xlsx", "xls"} else "other"


def upload_source(next_url):
    return "first_run" if (next_url or "").split("?")[0] == reverse("overview") else "upload_page"


def queue_ga_event(request, name, **params):
    """Queue a GA4 event; it is sent on the next page only if the visitor allowed analytics."""
    try:
        events = request.session.get(GA_SESSION_KEY, [])[-9:]
        events.append({"name": name, "params": params})
        request.session[GA_SESSION_KEY] = events
    except Exception:
        logger.exception("Could not queue analytics event %s", name)


def track_upload(request, outcome, *, filename="", bank="", rows_added=0, detail="", next_url=None):
    try:
        file_type = file_type_of(filename)
        source = upload_source(request.POST.get("next") if next_url is None else next_url)
        UploadAttempt.objects.create(
            user=request.user, source=source, file_type=file_type, bank=(bank or "")[:32],
            outcome=outcome, rows_added=rows_added, detail=str(detail or "")[:200],
        )
        if outcome == "imported":
            # The current import is the user's only live batch -> this was their first statement.
            if ImportBatch.objects.filter(user=request.user, undone_at__isnull=True).count() == 1:
                queue_ga_event(request, "first_statement_imported", file_type=file_type, source=source)
            queue_ga_event(request, "statement_imported", file_type=file_type, source=source, rows=rows_added)
        elif outcome in FAILED_OUTCOMES:
            queue_ga_event(request, "statement_upload_failed", file_type=file_type, source=source, reason=outcome)
        elif outcome == "pdf_started":
            queue_ga_event(request, "pdf_read_started", source=source)
    except Exception:
        logger.exception("Could not track upload outcome %s", outcome)
