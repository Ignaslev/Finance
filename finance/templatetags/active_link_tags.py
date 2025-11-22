from django import template
from django.urls import reverse, NoReverseMatch

register = template.Library()

@register.simple_tag(takes_context=True)
def active_link(context, view_name):
    """
    Checks if the current view matches the given view_name.
    Returns 'active' if it matches, otherwise an empty string.
    """
    try:
        request = context['request']
        current_url_name = request.resolver_match.url_name
    except (KeyError, AttributeError):
        # If request is not found in context or resolver_match fails
        return ''

    if view_name == current_url_name:
        return 'active'

    return ''