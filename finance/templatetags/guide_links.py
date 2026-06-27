from django import template
from django.urls import reverse
from django.utils.html import format_html


register = template.Library()


GUIDE_LINKS = {
    "upload": ("importing-transactions", "operaciju-importavimas", "upload-process"),
    "manual_transaction": ("importing-transactions", "operaciju-importavimas", "manual-transaction"),
    "edit_transaction": ("transactions", "operacijos", "edit-transaction"),
    "refund_detection": ("transactions", "operacijos", "refund-detection"),
    "categories": ("categories", "kategorijos", "creating-categories"),
    "category_caps": ("categories", "kategorijos", "spending-caps"),
    "dashboard_net_worth": ("dashboard", "apzvalga", "total-net-worth"),
    "dashboard_accounts": ("dashboard", "apzvalga", "accounts-assets"),
    "dashboard_history": ("dashboard", "apzvalga", "net-worth-history"),
    "dashboard_goals": ("dashboard", "apzvalga", "savings-goals"),
    "dashboard_income": ("dashboard", "apzvalga", "income-spending"),
    "dashboard_net_month": ("dashboard", "apzvalga", "net-by-month"),
    "dashboard_categories": ("dashboard", "apzvalga", "spending-by-category"),
    "statistics_income": ("statistics", "statistika", "income-sources"),
    "statistics_subscriptions": ("statistics", "statistika", "subscriptions"),
    "statistics_runway": ("statistics", "statistika", "financial-runway"),
    "statistics_categories": ("statistics", "statistika", "category-share"),
    "statistics_weekday": ("statistics", "statistika", "weekday-spending"),
    "reports_balance": ("reports", "ataskaitos", "balance-reconciliation"),
    "portfolio": ("portfolio", "portfelis", "portfolio-overview"),
    "profile_accounts": ("profile-settings", "profilis-nustatymai", "profile-accounts"),
    "profile_goals": ("profile-settings", "profilis-nustatymai", "profile-savings-goals"),
    "profile_preferences": ("profile-settings", "profilis-nustatymai", "profile-preferences"),
    "profile_language": ("profile-settings", "profilis-nustatymai", "profile-language"),
    "profile_deletion": ("profile-settings", "profilis-nustatymai", "profile-deletion"),
}


@register.simple_tag(takes_context=True)
def guide_icon(context, feature):
    link = GUIDE_LINKS.get(feature)
    if not link:
        return ""

    request = context.get("request")
    language = (getattr(request, "LANGUAGE_CODE", "") or "en").lower()
    section = link[1] if language.startswith("lt") else link[0]
    url = f"{reverse('guide')}?section={section}#{link[2]}"
    label = (
        "Atidaryti susijusią gido skiltį"
        if language.startswith("lt")
        else "Open the relevant guide section"
    )

    return format_html(
        '<a class="guide-help-link" href="{}" target="_blank" rel="noopener noreferrer" '
        'aria-label="{}" title="{}"><i class="ph ph-info" aria-hidden="true"></i></a>',
        url,
        label,
        label,
    )
