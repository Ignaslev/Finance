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
from django.utils import timezone
from finance.models import UserProfile
from django.contrib.auth import get_user_model
from .forms import RegisterForm

User = get_user_model()


def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)

            # Require email verification
            user.is_active = False

            # Normalize email
            user.email = (user.email or "").strip().lower()
            user.save()

            prof, _created = UserProfile.objects.get_or_create(user=user)
            prof.is_beta_tester = True
            prof.beta_joined_at = timezone.now()
            prof.save(update_fields=["is_beta_tester", "beta_joined_at"])

            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            activation_link = request.build_absolute_uri(
                reverse("accounts_activate", kwargs={"uidb64": uid, "token": token})
            )

            subject = "Activate your MoneyCoach account"
            body = (
                f"Hi {user.first_name},\n\n"
                f"Please activate your account by clicking the link below:\n"
                f"{activation_link}\n\n"
                f"If you did not create this account, you can ignore this email."
            )

            send_mail(
                subject=subject,
                message=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[user.email],
                fail_silently=False,
            )

            messages.success(request, "Registration successful. Check your email to activate your account.")
            return redirect("/accounts/login/")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


def activate(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except Exception:
        return HttpResponseBadRequest("Invalid activation link.")

    if default_token_generator.check_token(user, token):
        user.is_active = True
        user.save(update_fields=["is_active"])
        messages.success(request, "Account activated. You can now log in.")
        return redirect("login")

    return HttpResponseBadRequest("Activation link expired or invalid.")
