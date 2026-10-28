from decimal import InvalidOperation

from django import template
from django.utils.translation import get_language

from finance.insights import format_money

register = template.Library()


@register.filter
def money(value, arg=None):
    """{{ x|money }} -> '1 240,50 €' / '€1,240.50'; {{ x|money:0 }} whole euros; {{ x|money:row.currency }}."""
    decimals, currency = 2, "EUR"
    if arg is not None and str(arg).isdigit():
        decimals = int(arg)
    elif arg:
        currency = str(arg)
    lt = (get_language() or "").startswith("lt")
    try:
        return format_money(value, lt, decimals=decimals, currency=currency)
    except (InvalidOperation, TypeError, ValueError):
        return value
