from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from finance.models import UserProfile
from finance.subscriptions import grant_beta_access
from finance.utils import ensure_default_categories
from django.contrib.auth import get_user_model
from .forms import RegisterForm
from .throttling import client_ip, is_limited, record_attempt

User = get_user_model()


def register(request):
    if request.method == "POST":
        ip = client_ip(request)
        email = (request.POST.get("email") or "").strip().lower()

        if is_limited("register-ip", ip, limit=20, window_seconds=60 * 60):
            form = RegisterForm(request.POST)
            form.add_error(None, _("Too many registration attempts. Please try again later."))
            messages.error(request, _("Too many registration attempts. Please try again later."))
            return render(request, "accounts/register.html", {"form": form}, status=429)

        if email and is_limited("register-email", email, limit=5, window_seconds=60 * 60):
            form = RegisterForm(request.POST)
            form.add_error(None, _("Too many registration attempts for this email. Please try again later."))
            messages.error(request, _("Too many registration attempts. Please try again later."))
            return render(request, "accounts/register.html", {"form": form}, status=429)

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
            prof.save(update_fields=["preferred_language"])
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
            return redirect("/accounts/login/")
        else:
            record_attempt("register-ip", ip, window_seconds=60 * 60)
            if email:
                record_attempt("register-email", email, window_seconds=60 * 60)
            messages.error(request, _("Please fix the errors below."))
    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


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
