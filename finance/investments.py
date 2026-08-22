from decimal import Decimal

from django.utils import timezone


def linked_holdings_total(source):
    """Return the live value of holdings assigned to an investment source."""
    holdings = list(source.holdings.select_related("asset").all())
    total = sum((holding.value_eur for holding in holdings), Decimal("0"))
    return holdings, total


def current_investment_balance(source):
    """Prefer live holding values, while preserving manual-only investments."""
    holdings, total = linked_holdings_total(source)
    if holdings:
        return total
    return source.manual_balance if source.manual_balance is not None else Decimal("0")


def sync_investment_source_balance(source, *, empty_value=None):
    """Persist the live holding total without relying on a source's display name."""
    holdings, total = linked_holdings_total(source)
    if not holdings:
        if empty_value is None:
            return current_investment_balance(source)
        total = Decimal(empty_value)

    source.manual_balance = total
    source.balance_updated_at = timezone.now()
    source.save(update_fields=["manual_balance", "balance_updated_at"])
    return total
