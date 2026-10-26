import hashlib
import logging
import os
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import get_language
from django.views.decorators.http import require_POST
from openai import APIError

from finance.models import PdfImportJob
from finance.pdf_import import build_preview, cancel_job, refresh_job, start_pdf_read
from finance.tracking import queue_ga_event, track_upload

logger = logging.getLogger(__name__)

PREVIEW_ROWS = 15


def _lt():
    return (get_language() or "").startswith("lt")


def start_pdf_import(request, *, raw, filename, import_src, next_url, fail_url):
    """Called by the upload view for .pdf files: start the background read and show the wait page."""
    if not os.getenv("OPENAI_API_KEY"):
        messages.error(request, "PDF skaitymas šiuo metu neprieinamas. Įkelk CSV failą." if _lt()
                       else "PDF reading is not available right now. Please upload a CSV file.")
        track_upload(request, "pdf_unavailable", filename=filename, bank="pdf")
        return redirect(fail_url)

    limit = getattr(settings, "PDF_READS_PER_DAY", 10)
    started_today = PdfImportJob.objects.filter(
        user=request.user, created_at__gte=timezone.now() - timedelta(days=1),
    ).count()
    if started_today >= limit:
        messages.error(request, f"Šiandien jau įkėlei {limit} PDF išrašų. Pabandyk rytoj arba įkelk CSV." if _lt()
                       else f"You've uploaded {limit} PDF statements today. Try again tomorrow or upload a CSV.")
        track_upload(request, "daily_limit", filename=filename, bank="pdf")
        return redirect(fail_url)

    # The exact same file again (people re-upload whole years): never pay to read it twice.
    file_hash = hashlib.sha256(raw).hexdigest()
    earlier = (PdfImportJob.objects
               .filter(user=request.user, file_sha256=file_hash,
                       status__in=[PdfImportJob.STATUS_READING, PdfImportJob.STATUS_READY, PdfImportJob.STATUS_IMPORTED])
               .order_by("-created_at").first())
    if earlier and earlier.status == PdfImportJob.STATUS_READING:
        return redirect("pdf_import_status", job_id=earlier.pk)
    if earlier and earlier.status == PdfImportJob.STATUS_READY:
        return redirect("pdf_import_preview", job_id=earlier.pk)
    if earlier:
        messages.info(request, "Šis išrašas jau įkeltas – naujų operacijų jame nėra." if _lt()
                      else "This statement is already imported – there's nothing new in it.")
        track_upload(request, "nothing_new", filename=filename, bank="pdf", detail="same pdf as before")
        return redirect(next_url or fail_url)

    try:
        response_id, model = start_pdf_read(raw, filename)
    except APIError:
        logger.exception("Could not start PDF statement read")
        messages.error(request, "Nepavyko pradėti skaityti PDF. Pabandyk dar kartą po minutės." if _lt()
                       else "We couldn't start reading the PDF. Please try again in a minute.")
        track_upload(request, "error", filename=filename, bank="pdf", detail="could not start read")
        return redirect(fail_url)

    job = PdfImportJob.objects.create(
        user=request.user, money_source=import_src, filename=filename[:255], file_sha256=file_hash,
        next_url=(next_url or "")[:255], model_name=model, response_id=response_id,
    )
    track_upload(request, "pdf_started", filename=filename, bank="pdf")
    return redirect("pdf_import_status", job_id=job.pk)


@login_required
def pdf_import_status(request, job_id):
    job = get_object_or_404(PdfImportJob, pk=job_id, user=request.user)

    if request.GET.get("format") == "json":
        try:
            job = refresh_job(job)
        except APIError:
            logger.warning("PDF status check failed for job %s; will retry", job.pk)
        return JsonResponse({
            "status": job.status,
            "preview_url": reverse("pdf_import_preview", args=[job.pk]),
        })

    if job.status == PdfImportJob.STATUS_READY:
        return redirect("pdf_import_preview", job_id=job.pk)
    return render(request, "pdf_import_status.html", {
        "job": job,
        "is_lt": _lt(),
        "back_url": job.next_url or reverse("upload"),
    })


@login_required
def pdf_import_preview(request, job_id):
    job = get_object_or_404(PdfImportJob, pk=job_id, user=request.user)
    back_url = job.next_url or reverse("upload")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "cancel" and job.status in (PdfImportJob.STATUS_READING, PdfImportJob.STATUS_READY,
                                                 PdfImportJob.STATUS_FAILED):
            cancel_job(job)
            messages.info(request, "Importavimas atšauktas." if _lt() else "Import cancelled.")
            return redirect(back_url)
        if action == "import" and job.status == PdfImportJob.STATUS_READY:
            return _confirm_import(request, job, back_url)
        return redirect("pdf_import_status", job_id=job.pk)

    if job.status == PdfImportJob.STATUS_READING:
        return redirect("pdf_import_status", job_id=job.pk)
    if job.status != PdfImportJob.STATUS_READY:
        return redirect(back_url)

    preview = build_preview(job)
    return render(request, "pdf_import_preview.html", {
        "job": job,
        "p": preview,
        "sample_rows": preview["rows"][:PREVIEW_ROWS],
        "more_rows": max(0, preview["row_count"] - PREVIEW_ROWS),
        "is_lt": _lt(),
        "back_url": back_url,
    })


def _confirm_import(request, job, back_url):
    # Imported here to avoid a circular import with the upload view module.
    from finance.views.transactions import _save_import_rows

    preview = build_preview(job)
    added = 0
    if preview["new_count"]:
        added = _save_import_rows(
            request, rows=preview["fresh_rows"], import_src=job.money_source, filename=job.filename,
            bank_key="pdf", skipped_count=preview["unreadable_count"],
        )
    track_upload(request, "imported" if added else "nothing_new", filename=job.filename, bank="pdf",
                 rows_added=added, detail=f"balance check: {preview['balance_check']}", next_url=job.next_url)
    if not preview["new_count"]:
        messages.info(request, "Naujų operacijų nėra: visos jau buvo įkeltos anksčiau." if _lt()
                      else "Nothing new: all of these transactions were already imported.")
    job.status = PdfImportJob.STATUS_IMPORTED
    job.result = None  # the transactions are stored now; drop the raw statement data
    job.save(update_fields=["status", "result", "updated_at"])
    return redirect(back_url)


@login_required
@require_POST
def email_upload_link(request):
    """Phone visitors: email them a link so they can upload the statement from a computer."""
    from django.core.cache import cache
    from django.core.mail import send_mail

    back = reverse("overview")
    if not cache.add(f"upload-link-email:{request.user.pk}", 1, timeout=12 * 60 * 60):
        messages.info(request, "Nuorodą jau išsiuntėme – patikrink el. paštą." if _lt()
                      else "We've already sent the link – check your email.")
        return redirect(back)

    link = f"{settings.SITE_URL}{reverse('overview')}"
    if _lt():
        subject = "Tavo MoneyCompass nuoroda išrašui įkelti"
        body = (
            "Sveiki!\n\nAtsidaryk šią nuorodą kompiuteryje, prisijunk ir įkelk banko išrašą (PDF arba CSV):\n"
            f"{link}\n\nIšrašą rasi savo interneto banke, skiltyje „Sąskaitos išrašas“.\n\nMoneyCompass"
        )
    else:
        subject = "Your MoneyCompass link to upload a statement"
        body = (
            "Hi!\n\nOpen this link on a computer, log in and upload your bank statement (PDF or CSV):\n"
            f"{link}\n\nYou'll find the statement in your internet bank under 'Account statement'.\n\nMoneyCompass"
        )
    try:
        send_mail(subject, body, getattr(settings, "DEFAULT_FROM_EMAIL", None), [request.user.email], fail_silently=False)
    except Exception:
        logger.exception("Could not send upload link email")
        cache.delete(f"upload-link-email:{request.user.pk}")
        messages.error(request, "Nepavyko išsiųsti laiško. Pabandyk vėliau." if _lt()
                       else "We couldn't send the email. Please try again later.")
        return redirect(back)

    queue_ga_event(request, "upload_link_emailed")
    messages.success(request, f"Išsiuntėme nuorodą į {request.user.email}." if _lt()
                     else f"We sent the link to {request.user.email}.")
    return redirect(back)
