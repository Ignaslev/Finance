"""Readable LT/EN names for AI run kinds, statuses and modes (stored as short English codes)."""
from django import template
from django.utils.translation import get_language

register = template.Library()

LABELS = {
    # kinds
    "autocategorize": ("Automatinis kategorizavimas", "Auto-categorize"),
    "recheck": ("Patikrinimas iš naujo", "Recheck"),
    # statuses
    "queued": ("Laukia eilėje", "Queued"),
    "running": ("Vykdoma", "Running"),
    "done": ("Baigta", "Done"),
    "failed": ("Nepavyko", "Failed"),
    # modes
    "uncat": ("Nekategorizuotos", "Uncategorized only"),
    "ai": ("AI priskirtos", "AI-labeled"),
    "all": ("Visos (be tavo pačių)", "All (except yours)"),
    "new": ("Naujos operacijos", "New transactions"),
}


@register.filter
def ai_label(code):
    lt, en = LABELS.get(code, (code, code))
    return lt if (get_language() or "").startswith("lt") else en
