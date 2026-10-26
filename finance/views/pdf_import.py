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
from openai import APIError

from finance.models import PdfImportJob
from finance.pdf_import import build_preview, cancel_job, refresh_job, start_pdf_read

logger = logging.getLogger(__name__)

PREVIEW_ROWS = 15


def _lt():
    return (get_language() or "").startswith("lt")


def start_pdf_import(request, *, raw, filename, import_src, next_url, fail_url):
    """Called by the upload view for .pdf files: start the background read and show the wait page."""
    if not os.getenv("OPENAI_API_KEY"):
        messages.error(request, "PDF skaitymas šiuo metu neprieinamas. Įkelk CSV failą." if _lt()
                       else "PDF reading is not available right now. Please upload a CSV file.")
        return redirect(fail_url)

    limit = getattr(settings, "PDF_READS_PER_DAY", 10)
    started_today = PdfImportJob.objects.filter(
        user=request.user, created_at__gte=timezone.now() - timedelta(days=1),
    ).count()
    if started_today >= limit:
        messages.error(request, f"Šiandien jau įkėlei {limit} PDF išrašų. Pabandyk rytoj arba įkelk CSV." if _lt()
                       else f"You've uploaded {limit} PDF statements today. Try again tomorrow or upload a CSV.")
        return redirect(fail_url)

    try:
        response_id, model = start_pdf_read(raw, filename)
    except APIError:
        logger.exception("Could not start PDF statement read")
        messages.error(request, "Nepavyko pradėti skaityti PDF. Pabandyk dar kartą po minutės." if _lt()
                       else "We couldn't start reading the PDF. Please try again in a minute.")
        return redirect(fail_url)

    job = PdfImportJob.objects.create(
        user=request.user, money_source=import_src, filename=filename[:255],
        next_url=(next_url or "")[:255], model_name=model, response_id=response_id,
    )
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
    if preview["new_count"]:
        _save_import_rows(
            request, rows=preview["fresh_rows"], import_src=job.money_source, filename=job.filename,
            bank_key="pdf", skipped_count=preview["unreadable_count"],
        )
    else:
        messages.info(request, "Naujų operacijų nėra: visos jau buvo įkeltos anksčiau." if _lt()
                      else "Nothing new: all of these transactions were already imported.")
    job.status = PdfImportJob.STATUS_IMPORTED
    job.result = None  # the transactions are stored now; drop the raw statement data
    job.save(update_fields=["status", "result", "updated_at"])
    return redirect(back_url)
