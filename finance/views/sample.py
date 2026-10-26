from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.utils.translation import get_language
from django.views.decorators.http import require_POST

from finance.models import Transaction
from finance.sample_data import add_sample_data, real_transactions, remove_sample_data
from finance.tracking import queue_ga_event


def _lt():
    return (get_language() or "").startswith("lt")


@login_required
@require_POST
def sample_data_add(request):
    if real_transactions(Transaction.objects.filter(user=request.user, is_deleted=False)).exists():
        messages.info(request, "Tavo paskyroje jau yra tikrų operacijų." if _lt() else "Your account already has real transactions.")
        return redirect("overview")
    if add_sample_data(request.user):
        queue_ga_event(request, "sample_data_added")
    return redirect("overview")


@login_required
@require_POST
def sample_data_remove(request):
    if remove_sample_data(request.user):
        messages.success(request, "Pavyzdiniai duomenys pašalinti." if _lt() else "Sample data removed.")
    return redirect("overview")
