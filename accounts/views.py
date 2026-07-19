from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, PasswordResetView
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.translation import gettext_lazy as _
from django.utils import timezone, translation
from finance.models import UserProfile
from finance.subscriptions import grant_beta_access
from finance.utils import ensure_default_categories
from moneycoach.attribution import SESSION_KEY as ATTRIBUTION_SESSION_KEY
from django.contrib.auth import get_user_model
from .forms import RegisterForm
from .throttling import client_ip, is_limited, record_attempt

User = get_user_model()
PUBLIC_LANGUAGES = {"lt", "en"}


def public_language(request):
    """Return the explicit public-page language without trusting arbitrary values."""
    language = (
        request.GET.get("lang")
        or request.POST.get("lang")
        or translation.get_language()
        or UserProfile.LANG_LT
    ).lower()
    return language if language in PUBLIC_LANGUAGES else UserProfile.LANG_LT


class LocalizedLoginView(LoginView):
    """Render the public login page in the language selected on the landing page."""

    def dispatch(self, request, *args, **kwargs):
        self.public_language = public_language(request)
        with translation.override(self.public_language):
            response = super().dispatch(request, *args, **kwargs)
            # LoginView returns a lazy TemplateResponse for GET/invalid POST.
            # Render it while this explicit language override is still active.
            if hasattr(response, "render"):
                response.render()
            return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["public_language"] = self.public_language
        return context


class ThrottledPasswordResetView(PasswordResetView):
    def post(self, request, *args, **kwargs):
        ip = client_ip(request)
        email = (request.POST.get("email") or "").strip().lower()

        if is_limited("password-reset-ip", ip, limit=10, window_seconds=60 * 60):
            form = self.get_form()
            form.add_error(None, _("Too many password reset requests. Please try again later."))
            response = self.form_invalid(form)
            response.status_code = 429
            return response

        if email and is_limited("password-reset-email", email, limit=5, window_seconds=60 * 60):
            form = self.get_form()
            form.add_error(None, _("Too many password reset requests. Please try again later."))
            response = self.form_invalid(form)
            response.status_code = 429
            return response

        record_attempt("password-reset-ip", ip, window_seconds=60 * 60)
        if email:
            record_attempt("password-reset-email", email, window_seconds=60 * 60)

        return super().post(request, *args, **kwargs)


def register(request):
    language = public_language(request)
    with translation.override(language):
        if request.method == "POST":
            ip = client_ip(request)
            email = (request.POST.get("email") or "").strip().lower()

            if is_limited("register-ip", ip, limit=20, window_seconds=60 * 60):
                form = RegisterForm(request.POST)
                form.add_error(None, _("Too many registration attempts. Please try again later."))
                messages.error(request, _("Too many registration attempts. Please try again later."))
                return render(
                    request,
                    "accounts/register.html",
                    {"form": form, "public_language": language},
                    status=429,
                )

            if email and is_limited("register-email", email, limit=5, window_seconds=60 * 60):
                form = RegisterForm(request.POST)
                form.add_error(None, _("Too many registration attempts for this email. Please try again later."))
                messages.error(request, _("Too many registration attempts. Please try again later."))
                return render(
                    request,
                    "accounts/register.html",
                    {"form": form, "public_language": language},
                    status=429,
                )

            form = RegisterForm(request.POST)
            if form.is_valid():
                user = form.save(commit=False)

                # Require email verification
                user.is_active = False

                # Normalize email
                user.email = (user.email or "").strip().lower()
                user.save()

                prof, _created = UserProfile.objects.get_or_create(user=user)
                prof.preferred_language = form.cleaned_data.get("preferred_language") or UserProfile.LANG_LT
                attribution = request.session.get(ATTRIBUTION_SESSION_KEY, {})
                attribution_fields = []
                for field in (
                    "acquisition_source",
                    "acquisition_medium",
                    "acquisition_campaign",
                    "acquisition_content",
                    "acquisition_term",
                    "acquisition_landing_page",
                    "acquisition_referrer",
                ):
                    value = attribution.get(field, "")
                    if value and not getattr(prof, field):
                        setattr(prof, field, value)
                        attribution_fields.append(field)
                prof.save(update_fields=["preferred_language", *attribution_fields])
                grant_beta_access(prof, joined_at=timezone.now())
                ensure_default_categories(user, language=prof.preferred_language)

                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                activation_link = request.build_absolute_uri(
                    reverse("accounts_activate", kwargs={"uidb64": uid, "token": token})
                )

                subject = _("Activate your MoneyCoach account")
                body = (
                    _("Hi %(name)s,") % {"name": user.first_name}
                    + "\n\n"
                    + _("Please activate your account by clicking the link below:")
                    + "\n"
                    f"{activation_link}\n\n"
                    + _("If you did not create this account, you can ignore this email.")
                )

                send_mail(
                    subject=subject,
                    message=body,
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                    recipient_list=[user.email],
                    fail_silently=False,
                )

                messages.success(request, _("Registration successful. Check your email to activate your account."))
                # A one-time, non-identifying GA4 event is emitted on the next page view.
                request.session["google_analytics_pending_event"] = "sign_up"
                return redirect(f"{reverse('login')}?lang={language}")

            record_attempt("register-ip", ip, window_seconds=60 * 60)
            if email:
                record_attempt("register-email", email, window_seconds=60 * 60)
            messages.error(request, _("Please fix the errors below."))
        else:
            form = RegisterForm(
                initial={
                    "preferred_language": language,
                    "beta_access_code": (request.GET.get("beta_code") or "")[:100],
                }
            )

        return render(request, "accounts/register.html", {"form": form, "public_language": language})


def activate(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except Exception:
        return HttpResponseBadRequest(_("Invalid activation link."))

    if default_token_generator.check_token(user, token):
        user.is_active = True
        user.save(update_fields=["is_active"])
        messages.success(request, _("Account activated. You can now log in."))
        return redirect("login")

    return HttpResponseBadRequest(_("Activation link expired or invalid."))
