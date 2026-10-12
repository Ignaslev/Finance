import logging
from datetime import timedelta

from django.db import DatabaseError
from django.db.models import Q
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

from .models import User


logger = logging.getLogger(__name__)


class UserActivityMiddleware(MiddlewareMixin):
    update_interval = timedelta(minutes=1)
    excluded_views = {"ai_run_status", "stripe_webhook"}

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            return None
        if not getattr(view_func, "__module__", "").startswith("finance.views."):
            return None
        if request.resolver_match and request.resolver_match.url_name in self.excluded_views:
            return None
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        now = timezone.now()
        cutoff = now - self.update_interval
        if user.last_active_at is not None and user.last_active_at > cutoff:
            return None

        # The condition also prevents concurrent requests moving the date backwards.
        try:
            updated = User.objects.filter(pk=user.pk).filter(
                Q(last_active_at__isnull=True) | Q(last_active_at__lte=cutoff)
            ).update(last_active_at=now)
        except DatabaseError:
            logger.warning("Could not record MoneyCompass app activity", exc_info=True)
            return None
        if updated:
            user.last_active_at = now
        return None
